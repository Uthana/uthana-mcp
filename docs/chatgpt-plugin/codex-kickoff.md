# Codex kickoff: Uthana ChatGPT plugin, first wave

Date: October 8, 2026

This is what to paste into Codex to start implementation: one prompt per Codex task. Each prompt stands alone.

**Before you start**
- The docs PR (`v/chatgpt-plugin-docs` in `Uthana/uthana-mcp`) is merged, or each prompt points at that branch. The docs are in `docs/chatgpt-plugin/`: `plan.md`, `contracts.md`, `codex-briefs.md`.
- Brandon has approved `contracts.md` (plan step 0).
- Tasks 1–5 can run at the same time. Task 6 starts after tasks 1 and 2 land on staging.

**Rules for every task**
- New `v/` branch.
- Draft PR only.
- Never push to `main`/`staging`; never deploy.
- Brandon reviews before merge.
- Read the repo's `AGENTS.md`.
- **Don't change Uthana billing.**

---

## Task 1: Google-login fix + session cookie hardening (repo `Uthana/uthana`)

> Repo `Uthana/uthana`, branch `v/google-login-audience`. Read `AGENTS.md`.
>
> (1) Google-login token verification fix: the exact prompt is shared privately by Viren/Brandon, not kept in this repo.
>
> (2) In `appserv/utils.py` `set_cookie`, set `httponly=True`, `secure=True` (when not local dev), and `samesite="Lax"` for the session cookie `uthana_session_id2`. Propose a session lifetime in the PR description; today sessions never expire. Don't implement expiry without Brandon's OK.
>
> Add tests for both changes, including that the cookie flags are present. Open a draft PR.

## Task 2: Brief A, OAuth server + backend scope enforcement (repo `Uthana/uthana`)

> Repo `Uthana/uthana`, branch `v/oauth-server`. Read `AGENTS.md`. Then read `docs/chatgpt-plugin/contracts.md` §C1 and `docs/chatgpt-plugin/codex-briefs.md` "Brief A" in `Uthana/uthana-mcp` (branch `v/chatgpt-plugin-docs` until merged).
>
> Implement Brief A exactly as written: Authlib OAuth 2.1 server in appserv reusing the existing login/signup/session, CIMD client allowlist (`https://chatgpt.com/oauth/client.json`), PKCE S256, `resource`-bound tokens stored hashed, refresh rotation, `/oauth/introspect`, a Bearer branch in `before_request`, a **deny-by-default scope allowlist** for bearer requests, and Connected-apps revocation.
>
> If anything in the contract can't be built as written, stop and propose a change to `contracts.md` in the PR description; don't reinterpret it. This task depends on Task 1 being merged before production, but you can develop in parallel. Open a draft PR with Brief A's test list passing.

## Task 3: Brief B, remote MCP service (repo `Uthana/uthana-mcp`)

> Repo `Uthana/uthana-mcp`, branch `v/remote-chatgpt` from `main`. Read `docs/chatgpt-plugin/plan.md`, `contracts.md` (§C1, C6, C7), and `codex-briefs.md` "Brief B".
>
> Add `uthana-mcp serve-http` (Streamable HTTP at `/mcp`), keeping stdio unchanged. Build the `chatgpt` tool profile exactly per contracts §C7: annotations, `securitySchemes`, `ui.visibility`, and fileParams. Use a per-request client from the bearer token. Shape output per plan §6.6.
>
> Until Task 2 is on staging, use the **staging-only** no-auth mode (`UTHANA_MCP_DEV_STATIC_TOKEN_FILE`). It must refuse to start against production.
>
> Bearer support in `uthana-python-client` goes in a separate draft PR (`v/bearer-auth`): `Uthana(access_token=...)`. Check whether `mcp==1.30.0` supports Streamable HTTP and resource-server auth; upgrade if needed. Open draft PRs with Brief B's tests.

## Task 4: Brief F, quote → Confirm → submit over existing billing (repos `Uthana/uthana-mcp` + `Uthana/uthana`)

> Branch `v/chatgpt-quotes` in both repos as needed. Read `contracts.md` §C2–C3 and `codex-briefs.md` "Brief F".
>
> **Do not change Uthana billing.** Prices come from uthana.com/pricing via `payg_prices` (TTM V3 $0.10/s, auto-rig $0.15/rig; downloads, retargeting, and previews are free). Charging stays in the existing backend path.
>
> MCP side:
> - Postgres `quote` table (the existing SQLite receipt store, ported)
> - `create_quote` using the existing `estimate_model_cost` + balance
> - `approve_quote` (app-only, widget-only approval token) with an **atomic compare-and-set** `quoted → submitting`
> - `run_free_quote` (accepts only a total that is numerically zero by `Decimal`)
> - submission through the existing operations (TTM V3 `create_job`)
> - `unknown` outcomes never resubmitted
>
> Backend side, only what's missing:
> - `stageCharacterUpload` (OpenAI file-host allowlist, no redirects, 30 MiB, content sniffing, 24 h TTL)
> - rig inspection without rigging
> - running long upload/auto-rig on the existing `task` system, if it's synchronous today. Check first that the task system queues safely, and report what you find.
>
> Tests must include **two simultaneous `approve_quote` calls → one submission**, plus the rest of Brief F's list. Open draft PRs.

## Task 5: Brief C, viewer (repo `Uthana/uthana-mcp`, dir `viewer/`)

> Repo `Uthana/uthana-mcp`, branch `v/chatgpt-viewer`. Read `plan.md` §6.4, `contracts.md` §C3–C5, and `codex-briefs.md` "Brief C".
>
> Build a single-file MCP Apps viewer (Vite + three.js), starting from `Uthana/uthana:tools/ui/gltf-viz` and borrowing from `ui/src/app/lib/scene` (three 0.180) only as needed. Versioned resource URI, `text/html;profile=mcp-app`.
>
> Screens: quote card (line items, total, **credits left**, **Confirm**/Cancel), progress (poll `get_job`), player (orbit, play/pause, scrub, loop), Download (`create_export` → `get_export`), and Open in Uthana. Out of credits: say how much is needed, and link to the **informational** credits/pricing page on uthana.com, never directly to the card form.
>
> Completion → playback per contracts §C4: poll `get_job` → `show_motion(character_id, motion_id)` → load assets from that result's `_meta`.
>
> Side panel (`thread` entry point) where supported; inline + fullscreen elsewhere. **Mobile is required:** responsive from 360 px, touch controls, DPR cap of 2, WebGL context-loss recovery, and a no-WebGL fallback.
>
> Use mocked tool results until Tasks 3–4 are on staging. Open a draft PR with screenshots from desktop, web, iOS, and Android once it's connected.

## Task 6: Brief D, viewer assets, catalog, exports (starts after Tasks 1–2 land on staging)

> Repos `Uthana/uthana` + `Uthana/uthana-mcp`, branch `v/chatgpt-assets`. Read `contracts.md` §C4–C5 and `codex-briefs.md` "Brief D".
>
> Build:
> - `viewerAssets` with presigned S3 URLs (≤15 min) and `require_access` on both IDs, reusing the presign pattern in `services/vtm_move.py`
> - `createExport`/`getExport`: dedupe identical exports; retrieval never re-renders; defaults match the web app
> - a static public catalog of default avatars + 5–10 sample motions, as a JSON manifest in the C4 shape
> - the uthana.com deep link for "Open in Uthana"
>
> Allowlist every new operation in Task 2's scope map. Exports and downloads stay free, as on uthana.com/pricing. Open a draft PR.

---

**After these land:** plan §7 step 8. Run the first complete flow on staging (default avatar → quote → Confirm → V3 → playback → export → Open in Uthana) on desktop, web, iOS, and Android, and check that the debit equals the quote. Use what that run turns up for the next changes; don't rewrite the plan again first.
