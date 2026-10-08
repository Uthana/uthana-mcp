# Uthana ChatGPT plugin: MVP plan v2

Date: October 8, 2026 (revision 3: billing unchanged)
Status: Scope decided. Brandon approves the contracts (step 0); billing details stay provisional until G6 is answered, and that doesn't block auth, remote transport, or viewer work.
Supersedes: the v1 draft plan (not in the repo)
Companion files: `docs/chatgpt-plugin/contracts.md` (shared interfaces; authoritative where it overlaps this plan) and `docs/chatgpt-plugin/codex-briefs.md` (implementation briefs)
Audience: Viren, Brandon, and the implementing agents

## 0. How to read this

- **§7 is authoritative** for scope and order. Any other section that seems to disagree loses to §7.
- **The contracts document is authoritative** for tool names, payloads, states, and the billing rules. This plan explains why; the contracts say exactly what.
- There are no calendar dates. Each step starts when the steps it depends on are done.

## 1. Goal and release scenario

A ChatGPT user can:
1. Browse default avatars without an account.
2. Link or create a Uthana account. New accounts get $5 credit.
3. Pick a default avatar or upload a GLB/FBX.
4. See the price and their credits left, and confirm in the viewer.
5. Generate with Text-to-Motion V3.
6. Watch the result in 3D, download it, and open it on uthana.com.

> **Release scenario:** in ChatGPT (desktop, web, iOS, or Android), a new user asks to animate their character. They browse defaults anonymously, then link Uthana by signing up, which gives them $5. They upload an FBX, see "Auto-rig: $X.XX · $5.00 credit left — Confirm", and tap Confirm. Then they see "Text-to-Motion V3, 5 s: $Y.YY — Confirm" and tap Confirm. They watch the motion on their character, download an FBX, and tap "Open in Uthana" to find the same asset in their account.

**Target:** public directory listing as soon as possible. The pilot is internal only.

## 2. Decisions

| Area | Decision |
| --- | --- |
| Surfaces | **Desktop, web, iOS, and Android.** OpenAI's guidelines require plugins, including UI, to "function reliably in ChatGPT on both desktop and mobile," and nothing documented allows limiting surfaces. |
| UI | The viewer opens in the **conversation side panel** (`thread` entry point) where available. Elsewhere, including mobile, it's an **inline card with a fullscreen option**. Same bundle, responsive layout. It's read-only, with Confirm, Download, and "Open in Uthana". No logged-in Uthana editor is embedded. |
| Deferred extensions | `.fbx`/`.glb` file viewer (desktop-only) and the sidebar library are candidates for updates after approval. |
| Before linking | **Free browse** (`noauth`) of default avatars and sample motions. Anything billable needs a linked account. |
| New users | Sign up inside the OAuth linking screen. New orgs get the existing $5 welcome credit (`services.payg.init_payg_for_org`). Domain auto-join to an existing org with no new credit is intended. |
| Account and billing | **Uthana billing is not changed.** Users work off their existing credit balance ($5 on signup; more added by card on uthana.com). Every operation charges through the existing charge path, exactly as on the website/API. No holds, no new pricing rules, no new billing tables. |
| Credits shown | The viewer shows credits left on every quote and after every run. |
| Out of credits | Show how much is needed and send the user to uthana.com to add credits. **OpenAI rule:** a plugin may link to an *informational* page but not directly to a checkout or purchase page. So the link goes to a page that explains credits and pricing (e.g., `uthana.com/pricing`), from which the user adds credits, not straight to the card form. Linking straight to the card form risks rejection. |
| First-submission scope | **Text prompts + default avatars + custom GLB/FBX upload (with auto-rig).** |
| Fallback scope | **Default avatars only**, if custom upload isn't ready at step 10. This changes the promise from "animate *your* character" to "animate *a* character", so it's Viren's explicit call at that point, not automatic. |
| After approval | Video-to-motion, shipped as an update. New tools go through OpenAI's per-tool automated review, not a resubmission. |
| Model | Text-to-Motion V3. No silent fallback to V2. |
| Spend confirmation | **Every paid run needs an explicit Confirm tap in the viewer.** The quote shows the price from current published rates and the credits left. ChatGPT's own tool-approval prompt isn't relied on as consent, because users can set it to always allow. |
| Editing | None. Explain that it isn't supported; a new generation only when asked, with a new quote. |
| Ownership | Codex does the first pass on each step; Brandon validates and reviews before merge. |

## 3. Prerequisites

Each item blocks only the step(s) listed, not the whole project.

| # | Item | Blocks step | Owner |
| --- | --- | --- | --- |
| G1 | **Google-login token verification fix** in appserv (details tracked privately with Brandon). OAuth linking reuses this login, so it lands first. | 3 | Codex → Brandon |
| G2 | **Session cookie hardening:** `HttpOnly`, `Secure`, `SameSite=Lax` on `uthana_session_id2` (`appserv/utils.py` `set_cookie`); a session lifetime (sessions never expire today). | 3 | Codex → Brandon |
| G3 | **Fixed hostnames:** MCP origin (proposed `https://mcp.uthana.com/mcp`, which can never change once submitted) and OAuth issuer (proposed `https://uthana.com`). Confirm the openresty proxy that fronts Webflow can route `/.well-known/oauth-authorization-server`, `/oauth/*`, and login pages to appserv. | 3 (issuer config), 12 | Viren + Brandon |
| G4 | **Fix the `upload_character` backend failure** (support ref `c07835bb2fceed64d1e2`, fixture `rigged-figure.glb`, staging). | 10 | Backend |
| G5 | **MCP repo state:** resolve PR #6 (`v/rigging-capability`) and PR #7 (`codex/public-v1-generation`). The client pin is already done: main depends on `uthana>=0.5.1` (PR #8). | 5 | Viren |
| G6 | **Billing facts: answered by [uthana.com/pricing](https://uthana.com/pricing) (Viren, Oct 8).** TTM V3 $0.10/s; auto-rig $0.15/rig; downloads "free and unlimited"; retargeting and previews have no listed price, so they're free (matching the MCP's existing rule that unlisted operations are free). Quotes use the published rates. Remaining checks in step 8: requested vs produced seconds, and what happens today when a job fails. Neither is a new promise; the plugin reports whatever the existing path does. Separately, can a rig be inspected without rigging it? | 8 | Backend |
| G7 | **OpenAI org readiness:** business verification under "Uthana"; the project must not use EU data residency; Apps Management Write role; developer-mode access on test accounts. | 14 | Viren |
| G8 | **Legal/listing URLs:** privacy policy (covering prompts, uploaded files, and account email received via ChatGPT), ToS, support page, website. | 11, 14 | Viren |
| G9 | **Reviewer account:** dedicated prod account, email/password, no MFA, funded, with a sample character. | 13 | Viren |
| G10 | **Test devices:** one iOS and one Android device with the ChatGPT app and a developer-mode account. | 8 | Viren |

## 4. Current state: what is not built correctly yet

Reviewed: `Uthana/uthana-mcp` main `8ced0e2`, `Uthana/uthana-python-client` main `72977ba` (0.5.1), and `Uthana/uthana` main (appserv/services), on Oct 8, 2026.

### 4.1 Backend authentication (appserv)

| Finding | Location | Consequence |
| --- | --- | --- |
| Identity comes only from `?apikey=`, session cookies (`uthana_session_id2`/`uthana_session_id`), or HTTP Basic with the API key as username. No bearer tokens. | `appserv/app.py` `before_request` (~L159–177) | Must add bearer support (§5). |
| No OAuth authorization server, consent screen, client registry, or token store. | — | Must build (§5). |
| One API key per user, stored as a salted SHA-256 hash. | `services/user.py` (`hash_apikey`, `get_by_apikey`) | The server can't recover a user's key, and minting one would revoke the one they use. Mapping tokens to API keys isn't viable. |
| Any authenticated principal is a full user: no notion of a restricted credential. | `appserv/gql/auth.py` | OAuth tokens would be full account access (including deletes) unless the backend enforces scopes (§5, contracts §C1). |
| Google-login token verification needs a fix (details tracked privately). | appserv login views | G1. |
| Session cookie lacks `HttpOnly`/`Secure`/`SameSite`; sessions never expire. | `appserv/utils.py:20`, `migrations/0001-initial.sql` | G2. |
| `?apikey=` accepted in query strings. | `appserv/app.py` | Leaks keys into logs. Deprecate; OAuth tokens are header-only. |
| Every user has exactly one `org_id`; `require_access`/`require_write` resolve from `request.user`. | `appserv/gql/auth.py` | Good: bearer → `request.user` reuses all existing ownership checks. No org picker. |
| Signup (email + password + code, or Google) creates an org and grants $5. | `appserv/views/user.py`, `services/payg.py:437` | Reusable as is. |
| Asset files are served from cookie/Basic-authenticated paths. S3 presigning exists elsewhere. | client `client.py:323,348`; `services/vtm_move.py:419` | The ChatGPT iframe has no Uthana cookie, so it needs presigned URLs (contracts §C4). |

### 4.2 MCP server (`uthana-mcp`)

| Finding | Location | Required change |
| --- | --- | --- |
| stdio only. | `server.py:676` | Add Streamable HTTP at `/mcp`; keep stdio. |
| One global runtime from one env API key. | `server.py:124–129`, `config.py` | A per-request runtime from the caller's bearer token. |
| SQLite receipts keyed by `sha256(domain:key)`. | `store.py`, `api.py` | Port to a Postgres `quote` table in the MCP service, keyed by `user_id` (contracts §C3). Billing stays in the existing backend path. |
| Inputs are host file paths; outputs are written to local disk. | `WORKFLOW.md`, `artifact_io.py` | Staged uploads (contracts §C2) and presigned outputs (§C4–C5). |
| `openWorldHint=True` everywhere; `destructiveHint=False` on paid writes. | `server.py:26–27` | Per-tool annotations as in contracts §C7. |
| No `securitySchemes`, UI resources, or `outputSchema`. | `server.py` | Add per contracts §C7. |
| Guidance lives in the `uthana://workflow` resource, which ChatGPT won't read on its own. | `server.py:141–146` | Move it to a plugin skill. |
| `upload_character`/`download_motion` are synchronous and can block for minutes. | `server.py` | Backend jobs (§6.3); the MCP only starts and polls. |
| The model invents `request_id`s. | write tools | Backend quote IDs (contracts §C3). |
| 22 tools. | `server.py` | A `chatgpt` profile with the contracts §C7 surface. |
| `mcp==1.30.0` (client now `uthana>=0.5.1` via PR #8). | `pyproject.toml` | Verify the SDK's Streamable HTTP and resource-server auth; upgrade if needed. |

### 4.3 Python client

- Basic auth only (`client.py:76,147`). Add bearer auth: `Uthana(access_token=...)`.
- Add calls for the backend pieces this plan adds or reuses: `stageCharacterUpload`, the existing job/status queries, exports, and presigned viewer assets. Quotes live in the MCP service, not the client.

### 4.4 Viewer

- Production viewer: `ui/src/app/lib/scene/*` (Next.js 15, React 19, react-three-fiber 9, three 0.180).
- `tools/ui/gltf-viz` is a small standalone viewer and the likely starting point.
- The legacy FBX path is `www/static/elements/scene/animated-model.js`.
- Nothing is embeddable yet, and nothing has been tested on mobile WebGL.

## 5. Auth recommendation

Build a small OAuth 2.1 authorization server inside appserv that reuses the existing login, signup, and session model. It issues opaque, hashed, expiring tokens that resolve to `request.user`, **with scopes enforced in appserv itself**.

Why this fits Uthana's code:
1. **Login and signup exist.** `/oauth/authorize` only needs a session; without one it redirects to `/user/login?next=...`.
2. **The token pattern exists.** Tokens are stored hashed, like API keys.
3. **Ownership checks are reused.** Bearer → `request.user`, so every `require_access` keeps working.
4. **Scopes are enforced in the backend.** A bearer request carries its scopes and client. A deny-by-default allowlist maps each scope to permitted GraphQL operations and REST routes, so a token can't be used directly against appserv for anything outside its scopes (e.g., deletes). API keys and sessions are unaffected.
5. **No identity migration.** An external IdP (Auth0/WorkOS/Stytch) would still need 2–4 and would add a vendor to every login. It's a fallback only.

Components:
- Authlib's Flask OAuth2 server
- AS metadata at the issuer, client ID metadata documents (CIMD) with a ChatGPT allowlist, PKCE S256, `resource`-bound audience
- 1 h access tokens and rotating refresh tokens
- An introspection endpoint for the MCP
- A consent page with CSRF protection
- A "Connected apps" disconnect

Exact token, scope, and revocation semantics are in contracts §C1. Open choices for Brandon: Authlib vs. hand-rolled (recommend Authlib); opaque + introspection vs. JWT (recommend opaque, with a 60 s MCP cache); issuer on `uthana.com` via the proxy vs. `auth.uthana.com`.

## 6. Architecture

### 6.1 Ownership of state

- **Backend (appserv + task workers), unchanged billing:**
  - tokens and scopes
  - staged uploads and inspection
  - generation, preparation, and export jobs, using the existing ones wherever they exist
  - presigned URLs
  - balance and charging, exactly as today
- **MCP service:**
  - validates tokens, translates tool calls, shapes results
  - keeps one small Postgres table of quotes and their submission state (contracts §C3). That's the existing receipt store, ported from SQLite so it survives restarts and replicas.
  - no billing logic of its own

### 6.2 Remote MCP service

- `uthana-mcp serve-http`: Streamable HTTP at `https://mcp.uthana.com/mcp`, plus a staging host.
- Serves protected-resource metadata and the domain verification file.
- `chatgpt` tool profile per contracts §C7.
- Logs per-tool metrics (latency, outcome, hashed user, cost) for our own funnel analytics.

### 6.3 Durable execution

Long work never runs inside an MCP HTTP request:
- Motion generation already runs as a backend job (TTM V3 `create_job`). The plugin just uses it.
- Upload inspection, character preparation (upload and auto-rig), and export creation use whatever the backend does today. If any is a long synchronous call, it moves onto the existing `task` worker system. That's an existing-infrastructure change, not new execution machinery.
- Confirm that `task` jobs are queued and survive a worker restart. Some current uses, like `task.call` in `appserv/gql/mutations/share.py`, look like synchronous RPC. If it isn't queued, add a queued variant.
- The MCP and viewer only start jobs and poll them (contracts §C4).

### 6.4 Viewer

- **Bundle:** a single-file MCP Apps resource (`text/html;profile=mcp-app`) with a versioned URI.
- **Placement:** the side panel via `_meta["openai/ui"].entrypoints: [{type: "thread"}]` where supported; otherwise inline, with a fullscreen request.
- **Mobile:** a responsive layout that works from a 360 px width, touch orbit and scrub, a capped device pixel ratio, WebGL context-loss recovery, and an "Open in Uthana" fallback when WebGL is unavailable.
- **Screens:** quote card with **Confirm** → progress → player (orbit, play/pause, scrub, loop) → Download → Open in Uthana.
- Assets come from presigned URLs in widget-only `_meta`; decoders are bundled locally; the CSP lists only the asset hosts.
- Polls `get_job` and ignores late results for a stale selection.

### 6.5 Files

- Character uploads arrive through `_meta["openai/fileParams"]`, or `uploadFile`/`selectFiles` from the viewer.
- The MCP passes the ChatGPT `download_url` to the backend's staging call.
- The backend fetches it from allowlisted OpenAI file hosts only: no redirects, 30 MiB cap, type sniffing. It stores the file per user with a TTL and returns a staged upload ID (contracts §C2).

### 6.6 Model-visible vs hidden output

- **The model sees** what it needs to help the user:
  - character and motion names, duration, model, format
  - quote line items and totals, job states
  - inspection results and preparation warnings
  - actionable error messages, and a support reference when one exists
- **Hidden** in widget-only `_meta`, or never sent at all:
  - presigned URLs and approval tokens
  - credentials and internal hashes or fingerprints
  - raw upstream errors

### 6.7 Skill and metadata

- `skills/animate-character/SKILL.md` covers:
  - the workflow: choose or upload → inspect → quote → Confirm in viewer → watch → export → link
  - how to talk about cost
  - refusals: editing, buying credits, unsupported files
- Tool descriptions follow OpenAI's "Optimize Metadata" guide.
- A golden prompt set covers positive and negative cases.

## 7. Scope and order of work (authoritative)

**First submission:**
- Text prompts + default avatars + custom GLB/FBX upload.
- **Fallback:** default avatars only (Viren's explicit call at step 10).
- **After approval:** video-to-motion.

**Non-code steps (Viren), started immediately and run alongside:**
- N1. OpenAI verification and org checks (G7)
- N2. Hostnames and proxy routing (G3)
- N3. Privacy policy, ToS, support page (G8)
- N4. Reviewer account (G9)
- N5. Listing copy and icon
- N6. Test devices (G10)
- N7. Demo video, recorded after step 9

**Code steps (Codex → Brandon):**

| Step | Work | Brief | Depends on |
| --- | --- | --- | --- |
| 0 | **Shared contracts approved** (`docs/chatgpt-plugin/contracts.md`) | — | — |
| 1 | G1 Google-login fix + G2 cookie hardening | G1 | — |
| 2 | G5 MCP repo cleanup | — | — |
| 3 | OAuth server, bearer tokens, backend scope enforcement (staging) | A | 0, 1 |
| 4 | Approval + duplicate protection over the existing charge path; inspection and async character prep using existing infrastructure (staging) | F | 0 |
| 5 | Remote MCP, staging-only no-auth mode, contracts §C7 tools | B | 0, 2 (calls 4 as it lands) |
| 6 | Viewer: quote/Confirm, progress, player, mobile layout | C | 0 |
| 7 | Presigned viewer assets, static default catalog, exports | D | 0 |
| 8 | **Slice on staging:** default avatar → quote → Confirm → V3 → play → export → link, on desktop, web, iOS, Android. Check that the debit equals the quote. | — | 4, 5, 6, 7, G6, G10 |
| 9 | MCP switched to OAuth; no-auth mode removed; isolation and revocation tests | B | 3, 8 |
| 10 | Custom upload: stage → inspect → prep quote → Confirm → rig job → character; **decision point** for the fallback | F, D | 4, 7, 9, G4 |
| 11 | Plugin package, skill, review cases | E | 9, G8 |
| 12 | Production deploy (Brandon) | — | 9 (and 10 if in scope), G3 |
| 13 | 5 positive + 3 negative review cases on desktop, web, iOS, Android against production | — | 11, 12, N4 |
| 14 | Submit | — | 13, N1, N3, N5, N7 |
| 15 | Video-to-motion update | — | 14 |

**Longest chain:** 1 → 3 → 9 → 12 (auth to production), plus N1 (verification). Start those first. Auth (3), the remote MCP (5), and the viewer (6) start as soon as the contracts are approved; billing facts (G6) don't block them.

## 8. Submission package checklist

- [ ] Business verification complete (G7)
- [ ] Domain verification token at `https://mcp.uthana.com/.well-known/openai-apps-challenge`
- [ ] Plugin ZIP:
  - [ ] `plugin.json` (name, display name, descriptions, developer, category, website/support/privacy/ToS URLs)
  - [ ] Icon: square, ≥48 px, ≤5 MiB
  - [ ] `skills/animate-character/SKILL.md`
  - [ ] `.mcp.json` pointing at the prod URL
  - [ ] No secrets, no hooks
- [ ] Tool scan clean; annotations explicit; CSP matches actual fetches
- [ ] Reviewer account entered in Review details
- [ ] 5 positive + 3 negative cases, run on desktop, web, iOS, Android
- [ ] Demo video + release notes
- [ ] Country availability decided (`publication.countries`)

## 9. Acceptance matrix

| Scenario | Required outcome |
| --- | --- |
| Anonymous browse | Defaults play with no account and no backend user call |
| Link / sign up | OAuth + PKCE; consent shown; new org gets $5, visible in `get_balance` |
| Default avatar + prompt | Quote → Confirm tap → one V3 job → plays → export → visible on uthana.com |
| No Confirm, no charge | Without a Confirm tap the job never starts, even if the model calls every model-visible tool |
| Quote accuracy | The existing charge path's debit equals the quote for each v1 operation (mismatch = bug filed) |
| Credits shown | Credits left appear on the quote and after each run |
| Duplicate protection | Re-confirming a submitted quote returns the same job; one submission. An unknown outcome is never resubmitted |
| Expired quote | Confirm rejected; a new quote is required |
| Rigged GLB/FBX | Inspection finds a usable rig; no auto-rig charge |
| Unrigged GLB/FBX | Auto-rig quoted, confirmed, charged once, animates correctly |
| Bad file | Wrong type, oversize, or corrupt file rejected at staging/inspection, before any quote |
| Restart | Deploying the MCP, appserv, or workers mid-job doesn't lose or duplicate work |
| Out of credits | Says how much is needed; links to the informational credits/pricing page on uthana.com; no job; no direct checkout link |
| Token scope | A ChatGPT token used directly against appserv can't call non-allowlisted operations (e.g., delete) |
| Revocation | Disconnect stops new calls within 60 s; already-confirmed jobs finish |
| Account isolation | Account A can't read, quote, confirm, export, or charge B's assets |
| Expired download link | Refreshed without regeneration |
| Edit request | Says editing isn't supported; no silent regeneration |
| Mobile | Inline viewer, Confirm, playback, and download work on iOS and Android |
| Desktop + web | Side panel (or inline fallback) works on both |

Paid live tests use a dedicated account with an explicit budget. Mocked tests cover auth, scopes, isolation, quote states, and error handling.

## 10. Open questions

| Priority | Question | Resolve by |
| --- | --- | --- |
| P0 | Does ChatGPT enforce `ui.visibility: ["app"]` (model can't call app-only tools) on all surfaces? Approval also requires a widget-only token, so this is defense in depth. | Test in step 8 |
| P0 | OpenAI file-host domains for the `download_url` allowlist | Observe in step 8 |
| P0 | ChatGPT tool-call timeout | Measure in step 8 |
| P1 | Are upload/auto-rig and export long synchronous calls today? If so, does the existing `task` system queue them safely? | Backend, in step 4 |
| P1 | uthana.com deep-link format for a motion | Frontend |
| P1 | Side panel availability on mobile | Test in step 8 |

## References

- OpenAI plugin docs index: https://developers.openai.com/plugins/llms.txt
- Extensions: https://developers.openai.com/plugins/build/extensions
- UI and bridge: https://developers.openai.com/plugins/build/chatgpt-ui
- UI reference (fileParams, visibility, `_meta`): https://developers.openai.com/plugins/reference.md
- UI guidelines: https://developers.openai.com/plugins/concepts/ui-guidelines.md
- Auth: https://developers.openai.com/plugins/build/auth
- Guidelines (mobile, commerce, annotations, data): https://developers.openai.com/plugins/plugin-guidelines
- Skills: https://developers.openai.com/plugins/concepts/skills.md
- Submission: https://developers.openai.com/plugins/deploy/submission
- Review requirements: https://developers.openai.com/plugins/deploy/app-review
- Connect and test: https://developers.openai.com/plugins/deploy/connect-chatgpt
