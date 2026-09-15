# Uthana MCP staging pilot

This package lets a local coding-agent host generate and inspect Uthana motions,
trim them into saved native revisions, upload videos and rigged characters, and
find recent saved motions, inspect usage, and export retargeted animation. It is a draft for engineering review, not a released
or production-validated integration.

The host chooses the reasoning model. No model name, subscription, or model
provider is hardcoded. First acceptance targets a local coding assistant; any
compatible stdio MCP host can attempt the same tools. Host-specific acceptance in
Codex and Claude Code remains to be recorded. A browser-hosted ChatGPT connector
needs a separate authenticated remote transport; this package does not supply one.

## Install and connect

From this standalone repository, with Python 3.11 or later, Git, and
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```sh
uv sync --locked
```

This creates `.venv` and installs the package, runtime dependencies, and development
tools from `pyproject.toml` and the committed `uv.lock`. For a server-only environment,
use `uv sync --locked --no-dev`.

This installs the exact Python-client revision used in
[client PR #9](https://github.com/Uthana/uthana-python-client/pull/9).
That client change is awaiting review; published client 0.4.1 alone does not
contain the additions. Git must be installed to resolve this temporary VCS pin.

Keep the virtual environment in a persistent location. Configure the host to
start that environment's `uthana-mcp` executable
as a **stdio** server. The process communicates through stdin/stdout; diagnostics
go to stderr. Discovery and workflow-resource reading work without a key.

Set the following in the server process environment through the host's private
configuration. Do not commit keys or put credentials in command arguments.

| Variable | Purpose |
| --- | --- |
| `UTHANA_API_KEY` | Existing staging API key; required when calling Uthana |
| `UTHANA_DOMAIN` | Defaults to `staging.uthana.com`; every other value is rejected |
| `UTHANA_MCP_DATA_DIR` | Persistent private state location; defaults to `~/.local/state/uthana-mcp` |
| `UTHANA_MCP_INPUT_DIR` | Dedicated directory containing files deliberately selected for upload; uploads disabled when absent |

A host-neutral connection descriptor (adapt its field names to the host's config):

```json
{
  "command": "/absolute/path/to/venv/bin/uthana-mcp",
  "args": [],
  "env": {
    "UTHANA_DOMAIN": "staging.uthana.com",
    "UTHANA_MCP_DATA_DIR": "/absolute/path/to/private-state",
    "UTHANA_MCP_INPUT_DIR": "/absolute/path/to/selected-inputs"
  }
}
```

Supply `UTHANA_API_KEY` separately through the host's protected environment.
Allow the host to wait at least 420 seconds for character-upload tool calls.
Character processing can take up to 300 seconds after transfer; the adapter uses
360-second HTTP phase timeouts for this operation (15 seconds to connect), rather
than the usual 180 seconds. These are inactivity/phase limits, not a total deadline;
slow transfers may need a longer host deadline. A host cancellation or ambiguous
upload timeout still requires receipt/staging inspection, never automatic resubmission.
Inputs must reside on the same machine as this process. This first implementation
uses POSIX file safeguards and is tested on Linux; Windows installation is not
claimed. Image-capable hosts can inspect returned PNG frame content without
opening local files themselves. Export files still require shared filesystem access.

## Documentation with Context7

Uthana already has a [Context7 library](https://context7.com/websites/uthana_api):
`/websites/uthana_api`, also linked from the [API quickstart](https://uthana.com/docs/api).
A host can connect Context7 for documentation and this MCP for Uthana operations.
Context7 is optional; the bundled tool schemas and workflow remain self-contained.

When Context7 is available, use its `query-docs` tool with the exact library ID
and a focused API question. The known ID skips the library-resolution step.
See [Context7's tool reference](https://github.com/upstash/context7#available-tools).
Use general documentation questions; credentials and private asset contents do
not belong in documentation searches.

Retrieved API examples may target different SDK versions or production. Check
the installed tool schema and this package's staging restrictions before acting.
A documented API capability is not automatically an available MCP tool.

The [acceptance guide](ACCEPTANCE.md#context7-documentation-check) includes a
retrieval/freshness check. Publishing this private-repository draft does not
update the existing public website index.

## Tools

| Tool | Result |
| --- | --- |
| `generate_motion` | TTM V3 job ID for compound actions or substantial re-choreography; 4–10 whole seconds, ≤1000 prompt characters |
| `generate_motion_v2` | TTM V2 motion ID for simple actions; 4–10 seconds in 0.4-second increments |
| `generate_locomotion` | Loop-intended travel motion ID; style, strides, speed, and direction |
| `list_locomotion_styles` | Live available style names |
| `estimate_model_cost` | USD estimate using a published capability's live backend rate and explicit quantity |
| `get_job` | Existing job state and normalized motion ID; unresolved completion is explicit |
| `get_motion` | Native bundle ID/hash, frame count, FPS, and authoritative trim duration |
| `get_request_status` | Local receipt, known IDs, rejection/recovery guidance, and cached-artifact status |
| `trim_motion` | New native motion with source lineage, no looping, and metadata verification |
| `get_preview` | APNG or WebM; APNG frame count and timing availability |
| `get_preview_frame` | One decoded image plus frame index, timing when available, motion ID, and character ID |
| `generate_motion_from_video` | Upload selected MP4/MOV/WebM; V2M 2.0 or 2.1 job |
| `upload_character` | Upload selected FBX/GLB with compatibility warnings; `auto_rig=false` for rigged Mixamo files |
| `list_characters` | Accessible character IDs in bounded result pages |
| `list_motions` | Name search and listing within the API's recent motion window, with source labels and filters |
| `get_usage` | Read-only organization PAYG USD balance/rates and separate monthly allowances |
| `check_download_allowed` | Read-only eligibility for one motion/character pair; no download or usage reservation |
| `save_motion` | Register host-edited, self-contained animated GLTF as a native revision |
| `download_motion` | Retargeted FBX/GLB/BVH; 24/30/60 FPS, mesh, speed, torso-only, in-place, and Roblox options |

The pilot exposes 19 tools. Resource: `uthana://workflow`. Prompt: `review_motion`.
The review prompt asks the host to check the original requirements and identify
the three most useful improvements from actual visual evidence. It does not
execute suggestions. This guidance is not a server-side approval system; the
host must respect the user's requested scope.

Examples and acceptance status are in [ACCEPTANCE.md](ACCEPTANCE.md).
[Live staging evidence](LIVE-ACCEPTANCE-2026-09-14.md) records the three-model demo,
actual export review, measured charges, and remaining limits.
API coverage and remaining gaps are listed in [COVERAGE.md](COVERAGE.md).

## Agent decisions

The bundled workflow gives the host agent product guidance, not an automatic
server-side prompt classifier: simple actions start with V2; compound actions
use V3; explicitly loopable travel starts with locomotion. An explicit user model
choice takes precedence. V2 and locomotion return motion IDs synchronously;
V3 returns a job ID to poll. Locomotion duration follows its generated strides
and contacts, so verify native timing and the loop seam.

For a change to an existing performance, the host assesses whether an available
editing skill can make a localized correction while preserving what matters.
Better foot contact favors a targeted repair when a validated skill exists.
Changing the sword hand, adding 270 degrees of backswing, and holding a new pose
favors a new V3 generation. Preserve the original, carry forward unchanged
requirements, and label regeneration honestly. Exact frame preservation can
require a question rather than silently choosing a new generation.

The MCP has no foot-contact repair or arm editor. The separate
[agent PR #1621](https://github.com/Uthana/uthana/pull/1621) connects its host agent
to this MCP; its [live acceptance record](https://github.com/Uthana/uthana/blob/codex/agent-mcp-pilot/tools/agent/LIVE-ACCEPTANCE-2026-09-14.md)
records actual V2/V3/locomotion calls and image-based reviews. That evidence used
the MCP before this cleanup; the cleanup adds offline regressions without new
paid generations. The prototype UI has not migrated to this layer. Sparse image
reviews do not establish complete motion quality or native host installation.

## Source/API boundaries

- `server.py`: protocol schemas, annotations, workflow resource, image content, and review prompt.
- `operations.py`: reusable ordinary Python operations, source/result checks, input handling, and export receipts.
- `catalog.py`: bounded motion filtering and explicit usage units/account semantics.
- `billing.py`: public capability mapping, live-rate cost estimates, and free-operation accounting policy.
- `api.py`: shared Python-client calls, staging configuration, MCP result normalization, and redacted failures.
- `errors.py`: redacted upstream failure categories and conservative rejection classification.
- `store.py`: atomic SQLite request claims, credential-scoped receipts, and private saved assets.
- `fingerprints.py`: canonical numeric request identity and compatibility with historical receipts.
- `artifact_io.py`: bounded integrity checks of cached regular files.

The shared [Uthana Python client](https://github.com/Uthana/uthana-python-client)
owns GraphQL documents, upload encoding, API routes, and HTTP transport. This
adapter calls its public modules for generation, uploads, metadata, previews,
usage, trim/save, and export. Missing capabilities are added to that client so
other integrations can reuse them. The MCP contains no parallel API transport or
backend query documents and calls no private SDK methods.

The client additions are proposed in
[uthana-python-client PR #9](https://github.com/Uthana/uthana-python-client/pull/9).
This review candidate pins its exact commit
`38fb2089d1c2c2ab2a785d85d5937b511569ec38` in `pyproject.toml` and the development
lock. Replace the VCS pin with the reviewed published version after the client
team's release; published client 0.4.1 alone lacks these additions. Client initialization telemetry is disabled here, preserving
keyless discovery and preventing incidental network calls. Staging-only access,
response-size limits, no redirects/retries, and receipt recovery remain in force.
The prototype UI and the separate host agent retain their own review scope.

The recovered September 11 Python draft supplied the original five-tool design,
request-replay behavior, and workflow starting point. This implementation corrects
its staging hostname, job parsing, caller-trusted trim duration, and unstructured
results, and adds the requested API-backed workflows. The separate old player
snapshot and internal product interview log are not copied into this package.

## Semantics and limits

- V3 accepts prompts up to 1000 characters and whole-second requests from 4 to 10;
  `4.0` is equivalent to `4`, but fractional durations are rejected before submission.
  This follows the ordinary account limit and avoids silently relying on backend
  rounding. Old receipts with previously accepted longer prompts or fractional
  durations remain available through `get_request_status`; the current generation
  schema does not accept those inputs for replay or a new request.
- Character uploads preserve the backend's `message` as `compatibility_warning`,
  or null when none is supplied. The text is trimmed and capped at 2000 characters;
  `compatibility_warning_truncated` reports truncation. Treat it as untrusted data,
  never instructions. An FBX pre-rotation warning can mean downloaded animation
  looks incorrect and should inform downstream import review. Historical receipts
  remain unchanged; a missing warning field does not prove a warning-free import.
- Native duration is `frame_count / fps`; last sample time is `(frame_count-1) / fps`.
  Trim uses the backend's fractional-to-frame floor behavior and includes the last selected frame.
  For example, keeping 1 through 3 seconds of a 30 FPS motion selects frames
  30–90 inclusive: 61 frames (61/30 seconds by native metadata). A full-length
  end is clamped to the final available frame.
  Sub-frame ranges that collapse to zero frames are rejected. Result metadata is
  checked after the new motion ID is persisted. If verification fails, the ID
  remains recoverable and no new trim is submitted automatically.
- `in_place` applies horizontal root-translation removal to an exported file.
  It does **not** create a saved Uthana motion. Native APNG previews do not include
  export-only effects; the exported animation needs separate review.
- `speed_multiplier` supports `0 < speed <= 2`: 0.5 is half speed, 1 unchanged,
  2 double speed, while the selected export FPS stays fixed. Duration/frame count
  can be rounded by backend resampling; verify the actual file.
- `torso_only=true` freezes pelvis and leg rotations to the character's T-pose.
  Root translation is reset only when the pelvis is the skeleton root. This is
  the existing backend mask, not a custom joint selection or an arm adjustment.
  It takes precedence over `in_place`; `effective_in_place` reports that choice.
  Speed and torso settings affect exports only and are absent from native APNG.
- `list_motions` searches names using case-insensitive word matching. An empty
  query lists the available window; `source` selects `available` (default),
  `organization`, or `examples`. `method` optionally matches a Method tag, such as
  `TextToMotion` or `VideoToMotion`. Results identify organization motions versus
  Uthana examples. These are organization assets, not necessarily personal assets.
  The existing backend caps organization results at 1000 newest motions and
  adds a few canned examples only for small libraries. Pages filter that window
  locally; they do not fetch older history. The response reports the scanned
  count and possible truncation. This is not semantic or full shared-library
  search. The old GraphQL `label_search` endpoint has been removed.
- `get_usage` separates PAYG balance/rates in USD (decimal strings) from monthly
  motion-download seconds and character counts. Active subscription quotas
  override the organization defaults following backend behavior. PAYG has no
  monthly download/character cap; its legacy remaining values and integer
  unlimited sentinel are not presented as limits. Auto-rig can still be metered.
  `null` means unknown or not applicable, never zero; known zero stays zero.
  These are organization snapshots, not per-job costs or generation allowances.
- `check_download_allowed` checks the specific motion and target character.
  Prior downloads and role exemptions can permit a download even with zero
  monthly seconds left. The check does not export, record usage, reserve quota,
  or promise a later export will succeed. The download endpoint checks again.
  Neither read-only tool changes billing, subscriptions, or auto-recharge.
- Roblox is an FBX compatibility option for supported Roblox characters, not a
  general format conversion for Tar or arbitrary Mixamo rigs. Use 30 FPS and
  `include_mesh=true` for the requested mesh-and-skeleton example. Import into
  Roblox Studio and inspection of actual assets remain required acceptance checks.
- Arm adjustment is implemented in `ui/src/app/lib/scene/armRotation.ts`, not an
  exposed API operation. No arm-adjustment MCP tool is claimed here. A capable host
  can supply already-edited GLTF to `save_motion`; rig/import correctness must be verified.
- APNG retrieval is the existing `/app/preview/{character_id}/{motion_id}/preview.png`
  route. Frame extraction does not mean an agent reviewed it. Existing preview
  resolution/camera coverage can limit useful assessment. Missing, zero, or unusable
  APNG delays return `timing_status=unavailable`, null timestamps, and null duration;
  frame indexes remain usable for review. Cached frames are checked from the saved
  bytes, so older zero-time metadata does not become false timing evidence.
  There is no custom
  camera or full-motion evaluator in this package.
- This is one local credential context per server, not a multi-tenant hosted service.
  A credential hash separates local state, including request IDs and assets.
  Key rotation creates a new namespace; reconcile old work before repeating it.
- `get_request_status` recovers completed receipts and known job/motion IDs from
  local state without calling Uthana. Repeating a completed operation with the
  same request ID and arguments returns its original result. Trim/save recovery
  uses the historical source identity and reports `verification_status=not_rechecked`;
  it does not repeat native metadata checks or establish visual quality.
  Repeating `save_motion` still validates the supplied file's bytes. If the original
  file is unavailable, use `get_request_status` to recover the saved motion ID.
- Confirmed authentication/permission rejections and recognized root mutation
  rejections persist as `state=rejected`, with a redacted category and next step.
  Connection-establishment failures also use this state when no request was sent.
  After correcting the cause, the host may explicitly retry the same request ID
  and arguments; the server never retries automatically. Read/write interruption,
  partial success, and other ambiguous outcomes remain `unknown`. Both `pending`
  and `unknown` block resubmission; a new ID must not be used to evade that block.
  Database upgrades retain existing receipts, and rejected retry claims are atomic.
- Completed export recovery checks the saved bytes without another download or
  character-metadata request, including Roblox exports. Missing, changed, or
  symlink-replaced artifacts, nonregular files (including FIFOs), or oversized
  replacements make `get_request_status` report
  `artifact_status=unavailable_or_changed`; known IDs remain available and no
  replacement is downloaded automatically. An intact artifact reports
  `artifact_status=verified_local_bytes`, which does not establish import quality.
  Recovery opens one no-follow, nonblocking descriptor, requires a regular file
  of the recorded size (at most 128 MiB), and bounds the read before hashing.
- Equivalent numeric arguments have one request identity, including omitted
  defaults versus explicit `4`/`4.0` or `0`/`0.0`. Compatibility matching recognizes
  historical raw-JSON hashes for the existing numeric operation fields without
  rewriting receipts. Changed values, booleans, and strings remain distinct;
  pending/unknown requests still block resubmission.
- New default export switches are omitted from request fingerprints so receipts
  created before the speed/torso expansion still replay. Non-default settings
  are included; changing them under the same request ID is rejected. Completed
  trim/save replay also rejects changed arguments or supplied save content.
  SQLite atomically claims requests across local processes, but cannot provide
  provider-side exactly-once execution or reconcile an upstream job automatically.
- Recovery preserves historical metadata verification separately from a fresh
  check. `previous_verification` retains the latest conclusive result and errors when available;
  `last_verification_attempt` records the latest attempt. An unavailable metadata
  read cannot erase a known failure. `verification_status=not_rechecked` means
  recovery made no new check; inspect the historical evidence before using a result.
- Read-only authentication, permission, connection, and provider failures describe
  the failed read without implying a submitted job. Ambiguous mutation failures
  retain recognized error categories while continuing to block resubmission.
- Pricing authority is [uthana.com/pricing](https://uthana.com/pricing): listed
  capabilities keep their published prices, unlisted platform operations are free.
  There is no extra API/MCP call fee or Uthana agent-token fee in this pilot.
  Trim, saving supplied motion, retargeted export, preview, metadata reads, and
  already-rigged uploads are free. Auto-rigging and model-based stitching/looping
  retain their published prices. Backend access and legacy allowances still apply.
- `estimate_model_cost` reads live `payg_prices`, maps only public capabilities,
  and multiplies the per-second/per-rig/per-character rate by a supplied quantity.
  The public capability mapping was checked on September 14, 2026. Hidden backend
  SKUs are excluded from the public usage-rate list. Review mappings when the
  pricing page changes, and reconcile any page/backend rate mismatch before release.
  Missing/ambiguous rates fail explicitly; they never become zero. USD values
  remain decimal strings; no credits-to-USD conversion is invented.
- Estimates are not measured charges. At the rates inspected on September 14,
  four seconds of V2 estimates $0.12 and V3 $0.40. Actual generated duration,
  account terms, and billing outcomes may differ. New free-operation receipts
  record `credits_used=0` and `billing.cost_status=free_by_policy`; priced operations
  retain unknown actual cost until measured accounting is available. Historical
  receipts are replayed unchanged, not retroactively repriced.
- Uploads are bounded snapshots from a dedicated input directory. Saved GLTF
  must embed all buffers/images and match the given character's rig. Uploaded
  videos/characters are at most 128 MiB; GLTF JSON is at most 16 MiB. Local state
  needs owner-managed retention; never place it under a public static directory.

## Validation and Buildkite

This repository provides `test.sh` for local use and invocation from Buildkite.
It does not contain a GitHub Actions workflow. From the repository root:

```sh
uv sync --locked
uv run --locked ./test.sh
```

`uv sync` without flags also works; `--locked` fails if the project declaration and
lock disagree. The `dev` dependency group is included by default, so no extra install
step or requirements file is needed. To select a particular interpreter, pass
`--python 3.11` (or `/opt/uve/bin/python3`) to `uv sync`. Uthana's full internal
environment is not required.

The selected interpreter runs all checks, including subprocess protocol tests.
The runner changes to its own directory, so Buildkite can invoke it from another
working directory:

```sh
MCP_PYTHON=/absolute/path/to/repo/.venv/bin/python /absolute/path/to/repo/test.sh
```

The script itself uses already-installed dependencies and makes no package-installation
or network requests. Buildkite must provision the environment and invoke the script;
a hosted pipeline is not connected automatically.

All direct runtime and development dependencies are declared in `pyproject.toml`;
`uv.lock` records the resolved versions and sources for reproducible installation.
To change a dependency, edit `pyproject.toml` (or use `uv add` / `uv add --dev`), run
`uv lock`, rerun the checks, and commit both files. The Python-client Git pin is
also part of the package metadata, so other Python installers retain the same
required client revision. Replace it with a released version after client review
and release.

Keep the MCP environment isolated. Shared uve currently pins older Pydantic and
Pillow versions; no shared dependency pins need to change for this setup.

These standalone checks need no backend services, credentials, or model account.
They cover real stdio sessions and image content, API contracts through the shared
client, native trim metadata, bounded uploads/exports, catalog and usage semantics,
pricing, redacted failures, and recovery across restarts and SDK migration.
Synthetic fixtures establish protocol and contract behavior, not visual quality.
Historical live results and remaining acceptance cases are documented separately.

The protocol dependency remains MCP Python SDK 1.30.0. The `uthana` dependency is
the Uthana API client; these are distinct libraries. Release, deployment, public
package publication, and native host installation remain separate acceptance work.
