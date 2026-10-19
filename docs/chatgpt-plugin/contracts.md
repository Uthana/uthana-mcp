# Uthana ChatGPT plugin: shared contracts

Version: 0.5 draft, October 19, 2026 (release boundaries clarified; billing unchanged)
Status: **needs Brandon's approval (plan step 0) before Briefs A–F start in parallel**
Within the stage-3 ChatGPT integration, authoritative over the implementation details in `plan.md` after approval. The release boundaries in plan §0 govern applicability. Change this file first, then the code.

These are proposed ChatGPT-profile contracts, not prerequisites for publishing the
local MCP or launching a general hosted MCP. Viewer-only approval and quote
storage requirements apply to that profile. Before implementation, Brandon reviews
reuse of existing auth, jobs, assets, and durable state; revise these contracts if
existing infrastructure changes the design. Preserve the local stdio/API-key path
and its receipt behavior. Keep existing signup/email verification intact; no
unverified-account generation allowance or email-code bypass is introduced.

Conventions:
- IDs are opaque strings in Uthana's existing `generate_uid` style.
- Money is a decimal string in USD (`"0.4000"`).
- Times are ISO 8601 UTC.
- TTM V3 *requested* durations are whole seconds (`requested_duration_seconds`); a generated motion keeps its measured `duration_seconds` as reported by the backend.
- "Backend" = appserv GraphQL/REST + task workers.
- "MCP" = the remote MCP server.

---

## C1. Token identity, scopes, revocation

**Token:** opaque, header-only (`Authorization: Bearer`), stored hashed. Access TTL 1 h; refresh TTL 60 d, rotating (each use revokes the old token).

**Identity:** a token is bound to `{user_id, org_id, client_id, scopes[], resource, expires}`.
- `resource` must equal the MCP resource URL (`https://mcp.uthana.com/mcp`, or the staging equivalent).
- The backend rejects bearer tokens whose `resource` doesn't match the configured value.

**Introspection** (`POST /oauth/introspect`, authenticated with the MCP server's secret):

```json
{ "active": true, "sub": "<user_id>", "org_id": "<org_id>", "client_id": "https://chatgpt.com/oauth/client.json",
  "scope": "motion:read motion:generate", "aud": "https://mcp.uthana.com/mcp", "exp": 1760000000 }
```

The MCP caches introspection results for at most 60 s and keys all per-user state by `sub`, never by token.

**Scopes:**

| Scope | Allows |
| --- | --- |
| `motion:read` | Read own characters, motions, balance, quotes, jobs, exports; create presigned viewer/download URLs |
| `motion:generate` | Everything in read, plus: stage uploads, submit generation and character preparation, create exports |

**Backend enforcement:** bearer-authenticated requests are **deny by default**. An explicit allowlist maps each scope to the permitted GraphQL top-level fields and REST routes. The list lives in code (`services/oauth_scopes.py`) and is reviewed in Brief A. Explicitly excluded for all OAuth tokens:
- any delete, rename, or share mutation
- API key management
- account, org, or billing settings
- auto-recharge
- user management

Sessions and API keys are unchanged.

**Revocation:**
- Disconnect (uthana.com "Connected apps") revokes every token for `(user_id, client_id)`.
- The backend rejects revoked tokens immediately. The MCP stops within its 60 s cache window.
- Jobs already submitted before revocation run to completion and are charged as usual. Nothing new can start.
- Deleting a user or org invalidates tokens through the existing joins.

**MCP auth errors:**
- Missing or invalid token → HTTP 401 with `WWW-Authenticate: Bearer resource_metadata="https://mcp.uthana.com/.well-known/oauth-protected-resource"`.
- An OAuth tool called anonymously → tool error with `_meta["mcp/www_authenticate"]` to trigger linking.
- Insufficient scope → error `code: "insufficient_scope"`.

---

## C2. Staged uploads and inspection

**Stage:** `stageCharacterUpload(source_url, file_name?, mime_type?)` → `StagedUpload`.
- The backend fetches `source_url` from allowlisted OpenAI file hosts only. No redirects; 30 MiB cap.
- Accepts `.glb` and `.fbx` only, sniffed by content, not by extension.
- Stored under the user's prefix; 24 h TTL.
- Creating it starts an inspection job, which charges nothing (G6 confirms that inspection is possible without rigging).

```json
{ "staged_upload_id": "su_…", "file_name": "hero.fbx", "format": "fbx", "bytes": 4194304,
  "sha256": "<hidden from model>", "expires_at": "…", "inspection_job_id": "job_…" }
```

**Inspection result** (the job result, kind `inspection`; no charge; no persisted character):

```json
{ "staged_upload_id": "su_…", "status": "usable_rig | needs_autorig | unsupported",
  "rig": { "detected": true, "type": "humanoid", "bone_count": 65, "has_fingers": true },
  "mesh": { "triangles": 48000, "has_textures": true },
  "warnings": ["Character faces -Z; will be auto-oriented"],
  "unsupported_reason": null }
```

- `usable_rig` → preparation is an upload without auto-rig. It has no listed price, so it's $0 and goes through `run_free_quote`.
- `needs_autorig` → a paid preparation quote follows, priced at the existing auto-rig rate.
- `unsupported` → stop and show `unsupported_reason`.

If the backend can't inspect a rig without rigging it (G6), this contract changes before Brief F starts.

---

## C3. Quotes, explicit approval, execution (billing unchanged)

**Principle: Uthana's existing billing is not changed.** Users have a credit balance ($5 on signup, more added by card on uthana.com). Every operation charges through the **existing charge path** exactly as it does on the website and API. The plugin adds only three things: a price shown up front, an explicit Confirm, and duplicate protection.

**Quote kinds:**
- `character_prep` (input: `staged_upload_id`)
- `motion_generation` (input: `character_id`, `prompt`, `requested_duration_seconds`, `model: "text-to-motion-3.0"`)
- `export`: **not used.** Per uthana.com/pricing, downloads are free and unlimited, and retargeting and previews have no price. Kept in reserve only in case pricing changes.

**Create:** `create_quote(kind, params)` → `Quote`.
- The price is computed from current published rates, using the existing `estimate_model_cost` logic over `payg_prices`.
- Includes the current balance.
- Nothing is charged or reserved.
- Quotes are stored by the MCP service (C3 storage, below), not in new backend billing tables.

```json
{ "quote_id": "q_…", "kind": "motion_generation", "state": "quoted",
  "inputs": { "character_id": "c_…", "character_name": "Hero", "prompt": "a backflip", "requested_duration_seconds": 5,
              "model": "text-to-motion-3.0" },
  "line_items": [ { "description": "Text-to-Motion V3, 5 s", "unit_price_usd": "0.0800", "unit": "second",
                    "quantity": 5, "amount_usd": "0.4000" } ],
  "total_usd": "0.4000", "balance_usd": "4.6000", "sufficient_balance": true,
  "expires_at": "<created + 15 min>", "requires_approval": true,
  "approval_token": "<widget-only, never sent to the model>" }
```

**Rules:**
1. **Inputs are fixed.** Executing a quote uses exactly its stored inputs. Changing anything means a new quote.
2. **The charge is whatever the existing billing path charges.** The quote is the price under current published rates for those inputs. It is a display, not a new billing contract. Step 8 verifies that the debit matches the quote for each v1 operation (G6). A mismatch is a bug to report, not something the plugin compensates for.
3. **Explicit approval for paid quotes:** `approve_quote(quote_id, approval_token)`.
   - Allowed only in state `quoted`, before expiry, with a matching token, the `motion:generate` scope, and the same `user_id` that created the quote.
   - It then submits the operation through the existing backend mutation (e.g., TTM V3 `create_job`) and returns `{quote, job_id}`.
4. **Zero-cost execution is a separate path:** `run_free_quote(quote_id)`. It has no approval token and the model may call it. The server **rejects it unless the stored `total_usd` is numerically zero**, compared with `Decimal` (`"0"`, `"0.00"`, and `"0.0000"` are equal; never string comparison) (e.g., preparing an upload that already has a usable rig, if that is free today). Paid quotes can only go through `approve_quote`.
5. **Duplicate protection reuses the existing MCP receipt semantics:**
   - Before submitting, the quote moves to `submitting` with a single **atomic compare-and-set** (`UPDATE quote SET state='submitting' WHERE id=$1 AND state='quoted' AND expires_at > now()` and check that exactly one row changed). Only the caller that wins the transition submits. Concurrent callers get the current state, plus the `job_id` once it's recorded.
   - On a confirmed backend response it records `job_id` and moves to `submitted`.
   - If the outcome is unknown (timeout, crash between submit and record), it moves to `unknown` and is **never resubmitted automatically**. Recovery inspects the account's recent jobs, as the current `WORKFLOW.md` recovery rules do.
   - Re-approving a `submitted` quote returns the same `job_id`.
6. **Balance:** if `sufficient_balance` is false, approval returns `insufficient_balance`. The backend's existing balance check stays authoritative at submit time.
7. **Out of credits:** the viewer and model say how much is needed and link to Uthana's credits page on uthana.com (see the plan, §2 "Out of credits", for the link rule).

**Quote states:** `quoted` → `submitting` → `submitted` (has `job_id`) | `unknown`. A quote can also go `quoted` → `expired`, or `quoted` → `cancelled` when the user dismisses it in the viewer. After `submitted`, the job (C4) carries the outcome.

**No billable work without approval:** no model-callable tool may start an operation that costs money. Today, exports and viewer assets are free (uthana.com/pricing), so `show_motion` and `create_export` run directly. If pricing ever changes, then:
- `show_motion` and `create_export` start nothing billable. They return `{"state": "requires_quote", "quote": {…}}`, and the viewer shows the quote card with Confirm.
- Alternatively, those costs go on the original generation quote as extra line items, approved in the same tap.
- Choose one once G6 is answered. The default is a separate `export` quote.

**Who can approve:** only the viewer's Confirm button. `approve_quote` is an **app-only** tool (`ui.visibility: ["app"]`), and the `approval_token` exists only in widget-only `_meta`.

**Storage:** a small Postgres table in the MCP service (`quote`: id, user_id, kind, inputs, line items, total, state, approval token hash, job_id, timestamps). Keyed by `user_id` from introspection; safe across replicas and restarts. This is the existing SQLite receipt store ported to Postgres. No backend billing schema changes.

---

## C4. Jobs and viewer asset payloads

**Job** (MCP `get_job(job_id)`, mapped onto the backend's existing job/status queries per kind; kinds `inspection`, `character_prep`, `motion_generation`, `export`):

```json
{ "job_id": "job_…", "kind": "motion_generation", "state": "queued | running | succeeded | failed",
  "quote_id": "q_…", "progress": { "message": "Generating", "fraction": null },
  "result": { "motion_id": "m_…", "character_id": "c_…", "name": "a backflip", "duration_seconds": 5 },
  "quoted_usd": "0.4000", "balance_after_usd": "4.2000",
  "error": null, "created_at": "…", "updated_at": "…" }
```

- Results by kind:
  - `inspection`: the C2 inspection result
  - `character_prep`: `{character_id, character_name, rig_type, autorigged: bool}`
  - `motion_generation`: as above
  - `export`: the C5 export
- Motion generation uses the backend's existing job (TTM V3 `create_job`), which already runs asynchronously.
- `character_prep` and `export` reuse whatever the backend does today. If an existing call is synchronous and long, the MCP must not hold it open in-process. Making it a backend job is a backend decision, scoped in Brief F after the task-system check, using existing infrastructure only.
- `progress.fraction` is `null` unless it's real. Don't invent percentages.
- `balance_after_usd` is read from the existing balance after the job ends, so the viewer can show credits left.
- **Completion to playback:**
  1. The viewer polls `get_job` until `state` is `succeeded`.
  2. It reads `result.motion_id` and `result.character_id`.
  3. It calls `show_motion(character_id, motion_id)`.
  4. It loads the `viewerAssets` payload returned in that result's `_meta`.
  5. If `viewerAssets` returns `{"state": "preparing", "job_id"}`, it polls that job, then calls `show_motion` again.

**Viewer assets** (`viewerAssets(character_id, motion_id?)`; billing per existing behavior):

```json
{ "character": { "id": "c_…", "name": "Hero", "glb_url": "<presigned>", "expires_at": "…" },
  "motion": { "id": "m_…", "name": "a backflip", "duration_seconds": 5, "fps": 30,
              "glb_url": "<presigned, motion retargeted to character>", "expires_at": "…" },
  "open_in_uthana_url": "https://uthana.com/app/…" }
```

- Presigned URLs live ≤15 min. Refresh by calling `viewerAssets` again, never by regenerating.
- Charging for viewer assets and exports follows existing behavior (G6). Nothing here makes them free or paid.
- If the retargeted viewer GLB doesn't exist yet, the response is `{"state": "preparing", "job_id": …}`. That's an export-class job, billed as exports are today.
- The MCP puts this whole object in result `_meta` (widget-only). The model sees only the names, IDs, duration, and `open_in_uthana_url`.

**Anonymous catalog** (`browse_defaults`, no backend call): a static JSON manifest served from the public CDN, with the same `character`/`motion` shape but permanent public URLs.

---

## C5. Exports: creation vs retrieval

- **Create:** `createExport(motion_id, character_id, format: "fbx"|"glb", fps: 24|30|60, options)` → `Export`.
  - Charged (or not) exactly as an export is today (G6). If exports turn out to be billable, they go through a quote like any paid operation.
  - Options and defaults match the web app: `include_mesh=true`, `in_place=false`, `fps=30`.
  - If an identical export exists (same motion, character, format, fps, options), it returns that one (`state: "ready"`). Otherwise it starts an `export` job.
- **Retrieve:** `getExport(export_id)` → `Export` with a fresh presigned `download_url` (≤15 min) when ready.
  - Retrieval never re-renders or regenerates.
  - An expired URL is fixed by calling `getExport` again.

```json
{ "export_id": "x_…", "state": "pending | ready | failed", "job_id": "job_…",
  "motion_id": "m_…", "character_id": "c_…", "format": "fbx", "fps": 30, "options": { "include_mesh": true, "in_place": false },
  "file_name": "Hero-a-backflip.fbx", "bytes": 2097152, "download_url": "<presigned when ready>", "expires_at": "…" }
```

---

## C6. Errors

All backend and MCP errors share one shape. The model sees `code`, `message`, `retryable`, and `support_reference`:

```json
{ "code": "insufficient_balance | quote_expired | quote_not_approvable | invalid_file | file_too_large | unsupported_rig | job_failed | not_found | insufficient_scope | auth_required | rate_limited | internal",
  "message": "Human-readable, actionable sentence.", "retryable": false, "support_reference": "c07835bb…" }
```

- Never put raw upstream errors, stack traces, or internal hostnames in `message`.
- `retryable: true` means retrying the same call is safe. It never means "create a new quote automatically".

---

## C7. MCP tool surface (`chatgpt` profile)

Annotations are given as readOnly/destructive/openWorld; `openWorldHint` is `false` on every tool.

| Tool | Scheme / scope | Annotations | Visibility | UI | Backend call |
| --- | --- | --- | --- | --- | --- |
| `browse_defaults` | noauth | T/F/F | model, app | viewer | static catalog |
| `list_my_characters` | oauth `motion:read` | T/F/F | model, app | — | characters query |
| `stage_character_upload` (fileParams: `file`) | oauth `motion:generate` | F/F/F | model, app | — | `stageCharacterUpload` |
| `create_quote` | oauth `motion:generate` | F/F/F | model, app | viewer (quote card) | rates + balance queries (existing) |
| `approve_quote` | oauth `motion:generate` | F/F/F | **app only** | — | existing operation (e.g., `create_job`) |
| `run_free_quote` | oauth `motion:generate` | F/F/F | model, app | — | existing operation; **rejects any quote with `total_usd` ≠ 0** |
| `get_job` | oauth `motion:read` | T/F/F | model, app | — | `getJob` |
| `show_motion` | oauth `motion:read` | T/F/F | model, app | viewer | `viewerAssets`; never starts billable work (returns `requires_quote` if it would) |
| `create_export` | oauth `motion:generate` | F/F/F | model, app | — | `createExport` if free today; otherwise returns `requires_quote` (C3) |
| `get_export` | oauth `motion:read` | T/F/F | model, app | — | `getExport` |
| `get_balance` | oauth `motion:read` | T/F/F | model, app | — | balance query |

- Every tool declares `securitySchemes` explicitly.
- Tools that render the viewer set `_meta.ui.resourceUri` (versioned) and `_meta["openai/ui"].entrypoints: [{type: "thread"}]`.
- `destructiveHint` is `false` throughout: no tool deletes, overwrites, or revokes. Paid actions are gated by the C3 Confirm instead. Keep this justification ready for review.
