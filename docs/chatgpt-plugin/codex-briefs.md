# Codex briefs: Uthana ChatGPT plugin

Date: October 19, 2026 (revision 3: staged delivery)
Read first:
- `docs/chatgpt-plugin/contracts.md`: the proposed stage-3 interfaces. After approval, they're authoritative within that profile; don't reinterpret them. If something can't be built as written, stop and propose a contracts change.
- `docs/chatgpt-plugin/plan.md` §0: release boundaries and infrastructure-reuse review; §7: stage-3 scope and order.

Both live next to this file in `docs/chatgpt-plugin/`.

These briefs implement the ChatGPT integration, not the open-source release checklist.
Do not start them merely because the docs PR is merged. Brandon must first approve
the contracts and reuse review. Keep signup/email verification unchanged.

Process:
- Codex implements on a `v/` branch and opens a **draft PR**. Brandon reviews before merge.
- Never push to `main`/`staging`; never deploy.
- Read the repo's `AGENTS.md` first.
- Check existing open PRs before opening another. Aim for roughly five active PRs per repository for Viren's work; the existing six MCP PRs are accepted. This is a planning guideline, not automatic closure or consolidation. Prefer updating an existing PR when scope fits, and explain necessary stacks. Keep public diffs focused and reviewable.

Stage-3 order (plan §7): reuse review and contracts approved (step 0; billing details provisional until G6) → G1/G2 → A, B, C, D, F in parallel → E once B is on OAuth. No calendar dates; start when dependencies land.

---

## Brief A: OAuth server and backend scope enforcement (repo `Uthana/uthana`, branch `v/oauth-server`)

**Implements:** contracts §C1. Plan §5.

**Build**
1. Authlib Flask OAuth2 server (check deps first). New `services/oauth.py`, `services/oauth_scopes.py`, and an `appserv/views/oauth.py` blueprint.
2. Migrations:
   - `oauth_token`: hashed token, kind, user_id, client_id, scopes, resource, expires, revoked, created, last_used. Hash like `hash_apikey`.
   - `oauth_code`: code hash, user, client, redirect_uri, PKCE challenge, resource, scopes, expires, used.
3. `GET /.well-known/oauth-authorization-server`. Issuer from config.
4. `GET/POST /oauth/authorize`:
   - Requires a session; otherwise redirect to `/user/login?next=…`, with signup reachable from there.
   - Validate `client_id` as a client-metadata URL on an allowlist (`https://chatgpt.com/oauth/client.json`): fetch it, cache it, check `redirect_uri`.
   - Require S256 and `resource` equal to config.
   - Consent page with CSRF protection. Return `code`, `state`, `iss`.
5. `POST /oauth/token`: auth code + PKCE (single use); refresh with rotation. TTLs per C1. Public client.
6. `POST /oauth/introspect`: response shape per C1, authenticated with the MCP server's secret.
7. `before_request`: `Authorization: Bearer` → user + `request.oauth = {client_id, scopes}`. Header only. Existing Basic/session/`?apikey=` paths must keep working.
8. **Scope enforcement:** deny-by-default allowlist from scopes to GraphQL top-level fields and REST routes. Enforced in GraphQL middleware and a view decorator, only when `request.oauth` is set. Include the C1 exclusion list.
9. Revocation: "Connected apps" + Disconnect on the account page, or a `revokeOAuthClient` mutation if the UI would hold up the rest.

**Done when:** tests cover:
- PKCE success and failure, code reuse, wrong `redirect_uri`, wrong `resource`
- refresh rotation, revoked and expired tokens, deleted user
- bearer → `require_access` unchanged
- **a bearer token calling a delete mutation → rejected**, and a non-allowlisted REST route → rejected
- API-key and session regression

A manual OAuth client run against staging succeeds.

---

## Brief F: approval and duplicate protection over existing billing; upload inspection and preparation (repos `Uthana/uthana-mcp` + `Uthana/uthana`, branch `v/chatgpt-quotes`)

**Implements:** contracts §C2 and §C3. Plan §6.1, §6.3.

**Do not change Uthana billing.** No holds, no new pricing rules, no new billing tables, no change to how or when the existing path charges. If something seems to require a billing change, stop and raise it with Viren.

**Build**
1. **MCP side** (`uthana-mcp`):
   - Postgres `quote` table per C3 storage: the existing SQLite receipt store ported to Postgres, keyed by `user_id`.
   - `create_quote` prices with the existing `estimate_model_cost` logic over `payg_prices`, and reads the current balance.
   - `approve_quote` (app-only, approval token) and `run_free_quote` (rejects any total that isn't numerically zero, compared with `Decimal`) submit through the **existing** backend operations (e.g., TTM V3 `create_job`).
   - State machine `quoted → submitting → submitted | unknown`. The `quoted → submitting` step is an atomic compare-and-set (C3 rule 5). Never auto-resubmit `unknown`.
   - Prices come from uthana.com/pricing via `payg_prices`: TTM V3 $0.10/s, auto-rig $0.15/rig. Exports, downloads, and viewer assets are free and need no quote.
2. **Backend side** (`uthana`), only what the existing code lacks:
   - `stageCharacterUpload` per C2, with the OpenAI file-host allowlist, no redirects, 30 MiB, content sniffing, per-user prefix, and 24 h TTL.
   - Rig **inspection** without rigging, if it isn't possible today (G6).
   - If upload/auto-rig is a long synchronous call today, run it on the **existing** `task` system so the MCP can start it and poll. First confirm the task system queues work safely, and document what you find.
3. Write up the G6 facts in the PR description, recording **existing** behavior: what's charged for TTM V3, auto-rig, upload, viewer assets, and exports, and what happens when a job fails. Make the quote mirror them.

**Done when:** tests cover:
- `approve_quote` without the token, or by another user → rejected
- an expired quote → rejected
- re-approving a submitted quote returns the same `job_id`
- **two simultaneous `approve_quote` calls** on one quote → exactly one backend submission; both return the same `job_id`
- `run_free_quote` accepts `"0"`, `"0.00"`, and `"0.0000"` alike and rejects `"0.0001"`
- a quote for 5 s of TTM V3 shows $0.50; auto-rig shows $0.15
- a crash between submit and record → `unknown`, not resubmitted
- `run_free_quote` on a paid quote → rejected
- the staging SSRF cases: non-allowlisted host, redirect, oversize, wrong type

Then one live TTM V3 run on staging where the existing debit equals the quote.

---

## Brief B: remote MCP service (repo `Uthana/uthana-mcp`, branch `v/remote-chatgpt`)

**Implements:** contracts §C1 (resource-server side), §C6, §C7. Plan §6.2, §6.6.

**Build**
1. Base on main after G5. Use `uthana>=0.5.1`. In a separate client PR (`v/bearer-auth`), add `Uthana(access_token=…)` plus calls for the Brief F/D GraphQL operations.
2. `uthana-mcp serve-http` (Streamable HTTP at `/mcp`); stdio unchanged. Check `mcp==1.30.0` support; upgrade if needed.
3. Protected-resource metadata. Introspection with a 60 s cache. 401s and `_meta["mcp/www_authenticate"]` per C1.
4. A per-request client from the bearer. The only state is Brief F's Postgres quote table; no local SQLite in HTTP mode.
5. Exactly the C7 tool table, with annotations, visibility, securitySchemes, and fileParams on `stage_character_upload`.
   - `approve_quote` is app-only and takes the widget-only `approval_token`.
   - `run_free_quote` rejects any quote with `total_usd > 0`.
6. Output shaping per plan §6.6:
   - The model gets names, durations, quote line items, job states, inspection warnings, and actionable C6 errors.
   - Presigned URLs and approval tokens go in result `_meta` only.
7. **Staging-only no-auth mode** for step 8: `UTHANA_MCP_DEV_STATIC_TOKEN_FILE`. It refuses to start when the domain is production, and is removed in step 9.

**Done when:** tests cover:
- the model-visible output of `create_quote` never contains `approval_token` or URLs
- `approve_quote` is absent from model-visible tool listings
- two-user isolation, missing or invalid token, insufficient scope
- the scan-relevant metadata (annotations and securitySchemes on every tool)

Connected in ChatGPT developer mode on staging.

---

## Brief C: viewer (repo `Uthana/uthana-mcp`, dir `viewer/`, branch `v/chatgpt-viewer`)

**Implements:** contracts §C3 (approval UI), §C4 (asset payloads), §C5 (download). Plan §6.4.

**Build**
1. Vite + three.js single-file bundle, starting from `Uthana/uthana:tools/ui/gltf-viz`; use `ui/src/app/lib/scene` (three 0.180) only as needed. Versioned resource URI; `text/html;profile=mcp-app`.
2. MCP Apps bridge. Feature-detect `window.openai`. Use the `thread` entry point where supported, inline + fullscreen request elsewhere.
3. Screens:
   - **Quote card:** line items, total, balance, **Confirm** and Cancel. Confirm calls `approve_quote(quote_id, approval_token)`.
   - **Credits left** shown on every quote and after each run.
   - Out of credits: says how much is needed and links to the informational credits/pricing page on uthana.com, never directly to the card form.
   - Progress: `get_job` polling.
   - Player: orbit, play/pause, scrub, loop.
   - Download: `create_export` → poll `get_export` → open `download_url`.
   - Open in Uthana.
4. **Mobile:** responsive from 360 px; touch orbit and scrub; DPR cap of 2; WebGL context-loss recovery; a no-WebGL fallback (poster + Open in Uthana). Large tap targets for Confirm.
5. Bundle Draco/KTX2 decoders locally. The CSP lists only asset hosts. Ignore late job results for a stale selection.

**Done when:**
- It works in ChatGPT developer mode on desktop, web, iOS, and Android, with screenshots of each in the PR: quote → Confirm → progress → playback → download.
- No console errors.
- Bundle target under 2 MB gzip.

---

## Brief D: viewer assets, catalog, exports (repos `Uthana/uthana` + `Uthana/uthana-mcp`, branch `v/chatgpt-assets`)

**Implements:** contracts §C4 (`viewerAssets`, catalog) and §C5. Billing for viewer assets and exports stays exactly as it is today.

**Build**
1. Backend `viewerAssets(character_id, motion_id?)`: presigned S3 URLs (≤15 min), `require_access` on both IDs, reusing the presign pattern in `services/vtm_move.py`. If the retargeted viewer GLB doesn't exist, return an export-class job (billed as exports are today).
2. Backend `createExport`/`getExport`: dedupe identical exports; retrieval never re-renders. Defaults match the web app (confirm with the frontend code).
3. Static anonymous catalog: default avatars + 5–10 sample motions as public CDN GLBs + a JSON manifest in the C4 shape.
4. Deep-link format for `open_in_uthana_url` (confirm with the frontend).
5. Allowlist all new operations in Brief A's scope map.

**Done when:** tests cover:
- another user's asset → denied
- an identical export returns the existing one
- an expired URL is refreshed via `getExport` without a new job
- confirmation that `viewerAssets` and exports charge exactly what they charge today, with nothing new
- the catalog loading in the viewer

---

## Brief E: plugin package and review assets (repo `Uthana/uthana-mcp`, dir `plugin/`, branch `v/chatgpt-package`)

**Implements:** plan §6.7, §8.

**Build**
1. `plugin.json` (listing fields, four URLs), icon, `.mcp.json` → `https://mcp.uthana.com/mcp`. No secrets, no hooks.
2. `skills/animate-character/SKILL.md`:
   - workflow: choose or upload → inspect → quote → Confirm in viewer → watch → export → link
   - cost wording
   - refusals: editing, buying credits, unsupported files
3. Tool descriptions per OpenAI's "Optimize Metadata" guide; short server instructions.
4. `REVIEW-CASES.md`: 5 positive and 3 negative cases, with the steps to run them on desktop, web, iOS, and Android.
5. A build script that produces the ZIP.

**Done when:** the ZIP passes OpenAI's dashboard upload checks (metadata + skill scan).
