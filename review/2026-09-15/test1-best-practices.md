# Test 1 — Best-practices review of the Uthana MCP server

Reviewed at PR #2 head `45c5b61`. Sources compared against: the MCP specification
(modelcontextprotocol.io, 2025-06-18 — tools, error handling, security considerations,
progress/pagination utilities), Anthropic's "Writing tools for agents" engineering
guidance, GitHub's official MCP server, and Anthropic's reference servers repo
(`modelcontextprotocol/servers`). Live evidence gathered via a real stdio handshake
(`initialize`, `tools/list`, `resources/list`, `prompts/list`), the `uthana://workflow`
resource, and free read calls (`list_motions`, `get_usage`, `estimate_model_cost`, plus a
deliberate bad-ID `get_motion`). No paid or mutating calls were made.

## Verdict

**Within community norms for a partner-facing open-source MCP server, and above the norm
in several areas — with no blockers in the protocol surface itself.** Its
idempotency/replay machinery, spending honesty, input validation, and upload path
confinement exceed what GitHub's server or the Anthropic reference servers ship. The gaps
are concentrated in discoverability polish (no per-parameter schema descriptions,
confusing v2/v3 naming), long-running-call ergonomics (no progress notifications), one
error-reporting hole (not-found reads look like outages), and release hygiene (no
LICENSE, git-commit dependency pin, wrong advertised server version). All are fixable
without redesign; the LICENSE/packaging items become release blockers the moment this is
actually handed to partners.

## Where it follows best practice (briefly)

- **Correct, complete protocol surface.** stdio transport; `instructions` at initialize;
  a resource (`uthana://workflow`), a prompt (`review_motion`), and 22 tools with
  accurate `ToolAnnotations` on every tool — read tools carry
  `readOnlyHint/idempotentHint: true`, mutating tools `readOnlyHint: false` (verified on
  the wire). Constraints (`pattern`, `min/max`, `enum` via `Literal`, `multipleOf`,
  `additionalProperties: false` on nested models) are expressed in the JSON Schema, not
  just prose (`server.py:20-33`, `stitching.py`).
- **Idempotency and retries far above norms.** Durable client `request_id`, atomic SQLite
  claim before any upstream mutation, canonical fingerprint matching, replay of completed
  results, hard blocks on pending/unknown, explicit retry-after-rejection, and a
  progress checkpoint for the two-stage image-character flow (`store.py:137-206`,
  `operations.py`). The spec/Anthropic guidance ask for far less; this is exemplary for a
  server where calls cost real money.
- **Security posture.** Upload path confinement to `UTHANA_MCP_INPUT_DIR` with
  `resolve(strict=True)`, `is_relative_to`, `O_NOFOLLOW`, regular-file and size checks
  (`operations.py:217-232`); content validation (Pillow verify + decompression-bomb
  guard, APNG/WebM magic bytes, GLTF external-URI rejection); 0700/0600 private state;
  domain pinned to staging with no production fallback (`api.py:19-20`); API key via env
  (never argv), telemetry disabled, response-size caps, no auto-retries; upstream errors
  redacted into safe categories with conservative `rejected` vs `unknown` outcomes
  (`errors.py`); untrusted backend text capped and labeled
  (`compatibility_warning`, "data, not instructions" in instructions/WORKFLOW). This
  matches or exceeds the spec's security-considerations list except rate limiting (below).
- **Long generations use the job pattern** (`generate_motion`,
  `generate_motion_from_video` return `job_id`; `get_job` normalizes state and returns
  `poll_after_seconds: 15`, and explicitly distinguishes "finished without motion ID" as
  unresolved, not success — `validation.py:41-73`).
- **Pagination and honest scope.** `list_characters`/`list_motions` use bounded
  offset/limit with `next_offset`, and `list_motions` returns `scanned_count`,
  truncation flags, and a `scope_note` (verified live) — exactly the "helpful truncation
  messages" Anthropic recommends.
- **Cost transparency.** `get_usage` + `estimate_model_cost` with explicit units, decimal
  USD strings, "missing rates are not free," and free-by-policy receipts.
- **Docs and tests.** README documents env config, timeouts, boundaries; WORKFLOW.md is a
  genuinely good agent-facing playbook; tests include real stdio protocol sessions
  (`tests/test_protocol.py`, `stdio_fixture.py`); deps locked (`uv.lock`).

## Gaps

### 1. No per-parameter descriptions in any input schema — MAJOR
**Evidence (live `tools/list`):** every property carries only an auto-generated title,
e.g. `"request_id": {"pattern": "^[A-Za-z0-9_-]{1,128}$", "title": "Request Id",
"type": "string"}`. Nothing on the wire tells an agent that `request_id` is a
*client-generated durable idempotency key* or how to construct one; nothing on
`trim_start_pct` says "fraction 0–1, not seconds" (that lives only in the tool docstring
body); `strides`, `move_speed`, `travel_angle`, `zone_duration`, `fps` etc. are all
title-only. The spec's own tool example gives every property a `description`, and
Anthropic's guidance says to make implicit context explicit and name parameters
unambiguously. Hosts that render schemas per-field (or agents that skim only the
schema) lose the semantics entirely; today all semantics are packed into the
description prose.
**Fix:** `Annotated[str, Field(description="Client-chosen durable idempotency key; reuse
the exact same value to retry this same operation", pattern=...)]` on every parameter in
`server.py`; move per-parameter facts (units, fraction vs seconds, radians, defaults'
meaning) out of docstring prose into the fields.

### 2. Multi-minute synchronous tools send no progress notifications — MAJOR
**Evidence:** `upload_character` ("Allow more than 360 seconds", `server.py:219`),
`create_character_from_image` ("Allow at least 1080 seconds overall", `server.py:231`),
`create_looped_motion`/`create_stitched_motion` ("Allow at least 420 seconds"). The MCP
spec provides progress notifications precisely so long calls stay alive and observable;
spec client guidance says clients SHOULD implement timeouts, and many hosts default well
below 360 s — the README itself concedes the companion agent's "current 210-second MCP
timeout and 600-second overall default are too short" (README.md:196-197). The server's
elaborate unknown-outcome recovery machinery is partly compensation for calls that
predictably outlive host timeouts.
**Fix:** accept a FastMCP `Context` in the long tools and call
`ctx.report_progress()` between phases (upload transferred → prepared → generating), or
better, convert character creation to the same job-ID + poll pattern already used for
`generate_motion`. Backend permitting, the job pattern is the community-standard answer.

### 3. Release hygiene: no LICENSE, sparse metadata, git-commit dependency — MAJOR (blocker at partner release)
**Evidence:** repo root has no LICENSE/NOTICE file; `pyproject.toml` has no `license`,
`authors`, or `project.urls`; the runtime dependency is
`uthana @ git+https://github.com/Uthana/uthana-python-client.git@5c934a18...`
(`pyproject.toml:13`), which requires Git, blocks PyPI publication, and pins an
*unreviewed PR head*. Anthropic reference servers publish to npm/PyPI under clear
licenses; GitHub's server ships Docker images and binaries. Without a license, partners
legally cannot use the code at all. (README honestly frames all this as a pilot awaiting
the client release — good — but the review request is partner-facing quality.)
**Fix:** add a LICENSE (and `license` field), `authors`, `project.urls`; replace the VCS
pin with the released client before showing partners; state the supported-platform matrix
(POSIX-only today, `os.O_NOFOLLOW`/`chmod` in `operations.py:224`/`store.py:23` are
POSIX; README does disclose Linux-only).

### 4. Not-found reads are indistinguishable from outages — MAJOR
**Evidence (live call):** `get_motion {"motion_id": "does-not-exist-123"}` returns
`isError: true` with *"Uthana GraphQL request failed while reading data. No complete
result was returned."* — the generic `graphql_error` bucket (`errors.py:39`). An agent
holding a typo'd or stale ID is told, in effect, "the service failed; retry later,"
instead of "this ID is wrong." The `"Motion not found or inaccessible"` branch in
`api.py:141` never fires because the backend surfaces unknown IDs as GraphQL errors.
Anthropic guidance: clear, actionable error messages, not opaque failures. Same path
affects `get_job` and any read with a bad ID.
**Fix:** in `errors.py`, recognize the upstream not-found/invalid-ID GraphQL error type
(as `REJECTIONS` already does for auth/permission/region/balance) and map it to a
distinct category with message "Motion/job not found or not accessible to this account;
verify the ID" — for reads, `outcome="not_applicable"` and no retry suggestion.

### 5. Advertised server version is the SDK's, not the server's — MINOR
**Evidence (live `initialize`):** `"serverInfo": {"name": "Uthana staging", "version":
"1.30.0"}` — that is `mcp==1.30.0`, while the package is `0.1.0`. Partners and support
will misidentify deployments.
**Fix:** pass the package version through to the underlying server (e.g.
`FastMCP(...)` low-level server `version=importlib.metadata.version("uthana-mcp")`), and
consider naming it `uthana-staging`/`uthana` rather than the display string
"Uthana staging" (server names conventionally look like identifiers).

### 6. Vacuous auto-generated outputSchema on 21 tools — MINOR
**Evidence (live):** every `dict[str, Any]` tool emits `"outputSchema": {"type":
"object", "additionalProperties": true}`. The spec's purpose for `outputSchema` is
client-side validation and typing; an any-object schema adds bytes without information,
and FastMCP will also wrap results as `structuredContent`.
**Fix:** define result models (TypedDict/BaseModel) for at least the stable, high-traffic
results (`get_job`, `get_motion`, `list_motions`, receipts), or set
`structured_output=False` as `get_preview_frame` already does.

### 7. Tool naming: the flagship tool hides its version, and versions are handled inconsistently — MINOR
**Evidence:** `generate_motion` is TTM **V3** and `generate_motion_v2` is TTM V2 — an
unsuffixed name secretly being the *newer* model inverts the convention its own sibling
sets; meanwhile video versions are one tool with a `model` enum parameter
(`generate_motion_from_video`, `server.py:205`). Anthropic guidance favors consolidation
with parameters and unambiguous names.
**Fix:** either one `generate_motion(model="text-to-motion-3.0"|"2.0", ...)` (mirroring
the video tool), or rename to `generate_motion_v3`/`generate_motion_v2`. Also consider a
`uthana_` prefix if partners will run this beside other servers — generic names like
`get_usage`/`get_job` are collision-prone in multi-server hosts (GitHub-style
namespacing guidance); a dedicated single-vendor server can defensibly skip this.

### 8. Constraints stated in prose but absent from schema — MINOR
**Evidence:** V2's 0.4-second increment is enforced only at runtime
(`operations.py:47-49`); the schema allows any 4–10 number, so an agent learns the rule
by failing. `zone_end_position` being valid only with `loop_mode="open"` is likewise
runtime-only (`operations.py:309-314`).
**Fix:** `multipleOf: 0.4` (or an enum of the 16 valid values, sidestepping float
`multipleOf` pitfalls) for V2 duration; describe the open-loop-only constraint in the
`zone_end_position` field description (JSON Schema conditionals are poorly supported by
hosts, so a field description is the pragmatic fix).

### 9. Description style: policy-dense, buries what the tool does, leaks indentation — MINOR
**Evidence (live):** wire descriptions preserve 8-space docstring indentation
(`"\n\n        Prompt maximum is 1000 characters..."`) — ragged rendering and wasted
tokens on every `tools/list`. Content-wise, descriptions lead with policy and negations
("Preserve the user's prompt", "no silent rounding", "A file path alone is not visual
evidence") before, or instead of, plain what-it-does/what-you-get sentences; Anthropic's
bar is "as you would explain to a new team member." The behavioral warnings are genuinely
valuable — the issue is ordering and density, not existence.
**Fix:** `textwrap.dedent` the docstrings (or reformat flush-left); restructure each as:
sentence 1 = what it does and returns, sentence 2 = cost, then constraints/caveats.

### 10. Resource metadata is bare — MINOR
**Evidence (live `resources/list`):** `{"name": "workflow", "uri": "uthana://workflow",
"description": "", "mimeType": "text/plain"}` — empty description, and Markdown served
as `text/plain`. Hosts pick resources by these fields.
**Fix:** `@server.resource("uthana://workflow", title="Uthana motion workflow",
description="Agent playbook: model selection, review, recovery, pricing",
mime_type="text/markdown")`.

### 11. Artifacts are returned as server-local file paths only — MINOR
**Evidence:** `get_preview` and `download_motion` results carry `local_path` under the
server's private state dir (`store.py:220`); README: "Export files still require shared
filesystem access." In remote/sandboxed host setups (exactly how this review ran) the
path is unusable; only APNG frames are retrievable in-band via `get_preview_frame`. The
spec provides `resource_link` content and resources for precisely this.
**Fix:** also expose cached artifacts as MCP resources (`uthana://artifact/{id}`) or
return a `resource_link` alongside `local_path`, so image/file-capable hosts can fetch
export bytes without shell access. (Bytes are already hash-verified in the store.)

### 12. No logging at all — NIT
**Evidence:** zero `logging` usage in `src/`; README claims "diagnostics go to stderr"
but nothing is ever emitted. For partner debugging (which request was claimed, which
upstream call failed), silent servers are hard to support. Correctly, nothing writes to
stdout.
**Fix:** minimal `logging` to stderr (request_id, operation, state transitions, redacted
error category), default WARN, env-tunable. Optionally the MCP `logging` capability.

### 13. No rate limiting — NIT
The spec says servers "MUST rate limit tool invocations." For a local single-user stdio
server the risk is low and community practice (reference servers) matches, and the
request_id discipline already prevents duplicate paid submissions — but a cheap
per-process cap on paid mutations per minute would close the letter-of-the-spec gap.

## Live-call notes (free reads)

- Handshake clean on protocol 2025-06-18; capabilities honest (`listChanged: false` everywhere).
- `list_motions` (hit and miss cases) returned exemplary scope honesty; `get_usage` and
  `estimate_model_cost` returned units, decimal strings, and clear estimate-not-debit
  framing exactly as documented. Output values matched docs (V3 4 s → $0.4000).
- The one live wart found is the not-found error shape (gap 4).
