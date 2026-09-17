# Production partner beta: acceptance checklist

September 17, 2026. Review candidate, not a published release. This follow-up builds on MCP PR #2 and retains the shared-client commit pin until its reviewed release is available.

## Evidence for this revision

- 374 offline tests pass, including both API origins, production mutation/read/export routing, invalid domains, authentication rejection without fallback, selected-origin support references, private key-file validation, credential/environment receipt isolation, restart recovery, and real stdio discovery.
- Formatting, lint, and source/wheel builds pass. A fresh locked, server-only Linux installation succeeds.
- The fresh Linux runtime passed live staging reads through stdio: initialization identified staging, all 22 tools were visible, private key-file authentication worked, `get_usage` and `list_characters(limit=1, query="Tar")` succeeded, and a four-second V3 estimate returned $0.40. No generation was submitted.
- Production rejected the staging credential with an actionable authentication error and no environment fallback. A separately supplied production key then authenticated successfully.
- The fresh Linux stdio runtime completed the production core workflow: account usage, character listing with limit 1, default Tar access, pricing, one four-second V3 generation, job polling, native metadata, APNG preview/frame delivery, trim, export eligibility, and GLB download with mesh at 30 FPS.
- Native source metadata reported 97 frames at 24 FPS. Trim verification passed with 73 frames at 24 FPS. Independent GLB inspection found one mesh, one skin, one animation, and 90 uniformly sampled keys at approximately 30 FPS; this checks file structure and sampling, not a destination-engine import.
- A second server process recovered the generation, trim, and export receipts with `replayed=true`. No second generation was submitted.
- Generation estimate: $0.40. Observed organization balance decrease: $0.4042. A ledger query did not find a row directly keyed by the returned job ID, so the balance change is observational evidence, not independently attributed job billing. Account balances and identifiers are not published here.
- Visual review of five returned 96-by-96 preview frames showed changing leg poses and a raised right-hand wave. This supports the broad walk-and-wave action. The resolution and sparse sampling cannot establish foot contact, finger quality, or continuous motion quality. No visual improvements were executed.
- macOS and native Codex/Claude Code acceptance remain pending. Configuration follows the linked host documentation; generic stdio tests alone do not prove native host timeout behavior.

## Repeatable production verification

Use an authorized production test account, its own key, a persistent private data directory, and a recorded spend threshold. Keep credentials, account balances, and private assets out of committed evidence.

1. Confirm initialization and workflow identify `uthana.com`; call `get_usage` and `list_characters(limit=1, query="Tar")`. Verify the SDK default Tar character or select an accessible returned ID explicitly.
2. Fetch current model prices, estimate a four-second V3 generation, and confirm the estimate fits the authorized budget. Record expected and measured cost separately; estimates are not actual charges.
3. Submit one uniquely named generation with a durable request ID. Poll `get_job` to a terminal state. On interruption, inspect `get_request_status` and the known job instead of starting a new request.
4. Read motion metadata, retrieve an APNG preview, and inspect representative frames. Record output quality separately from API/protocol success.
5. Trim a valid interval, check export eligibility, and download a GLB with mesh at 30 FPS. Verify nonempty bytes and inspect the exported animation. A successful download is not proof of successful Roblox or DCC import.
6. Restart the connector with the same state. Reuse completed request IDs with identical arguments and verify recovery without new generation. Confirm changed arguments are rejected.
7. Using a second authorized account, verify private asset access is denied. Offline receipt separation does not establish upstream account authorization.
8. Verify each feature that will be advertised beyond this core workflow separately, including production model entitlement and relevant account limits.

## Linux and macOS host acceptance

For each target OS, record OS version/architecture, Python and uv versions, exact MCP revision, host/version, and model used:

- Fresh `uv sync --locked --no-dev` from the supplied fixed revision.
- Private key-file loading and all 22 tools visible in Codex and Claude Code.
- Two clearly named connections with separate production/staging keys; no accidental environment selection.
- Generation, preview image visibility, export path usability, and recovery after host restart.
- Progress and configured deadlines for long operations. Image creation can need 1080 seconds or more; the guide configures 1200 seconds. Verify the actual host rather than assuming progress extends a deadline.
- Paths containing spaces, private file permissions, selected upload directories, and persisted local artifacts.

Use platform-specific failures to refine setup or mark the combination unsupported before inviting a partner.

## Known limitations and release gates

Character upload has an unresolved upstream failure on the reviewed fixture. Image creation, looping, and stitching are experimental; stitching needs a separately validated host pose sampler and facing convention. Character catalogs still use bounded local pagination. No hosted multi-account MCP service is included.

Before partner distribution, finish the relevant MCP/client reviews, verify the partner's actual OS/host and account entitlements, and provide an approved fixed release plus known limitations. Invitation-only distribution is separate from API authorization. This PR does not create a distribution repository, invite collaborators, change visibility, merge, or deploy.
