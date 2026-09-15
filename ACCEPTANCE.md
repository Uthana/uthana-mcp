# Review and staging acceptance

The review target is a standalone MCP package plus shared Python-client additions for Brandon and Tony.
First interactive target: this coding assistant, through a local stdio server.
The host selects its model; compatibility with another reasoning model is not
blocked by adapter code. Actual host installation still needs acceptance.

## Current evidence

- The original pilot used Python 3.12; the standalone revision also targets uve's Python 3.11 in an isolated environment.
- Unit, API-contract, and real stdio protocol tests exercise synthetic responses.
- API source inspected against GitHub main commit
  `5cc7d8a9df1134be2ecba748741949acd37d1668`; relevant API files match the baseline.
- Before the shared-client migration, **261 offline tests passed**, including real stdio sessions with synthetic providers. Current migration checks are recorded below.
- The live V2/V3/locomotion demonstration, native trim, actual GLB inspection,
  recovery, and accounting reconciliation completed on September 14, 2026.
  See [the live acceptance record](LIVE-ACCEPTANCE-2026-09-14.md) for motion IDs,
  hashes, measured charges, visual findings, and the APNG timing correction.
- The requested forward run was not fully satisfied in the inspected V3 export;
  technical workflow success is distinct from prompt-quality acceptance.
- Cases below are the broader acceptance checklist. Completion is limited to the
  evidence explicitly recorded above; uploads and destination imports remain open.

## Shared-client migration

[Python-client PR #9](https://github.com/Uthana/uthana-python-client/pull/9)
contains the shared-client changes, pinned here at
`38fb2089d1c2c2ab2a785d85d5937b511569ec38`.

Tony's review moves backend queries, upload encoding, response handling, and
missing capabilities into the existing Uthana Python client. The MCP uses public
client modules and retains its tool schemas, receipt recovery, product guidance,
and normalized errors. The standalone repository has a Buildkite-callable
`test.sh`, its own formatting configuration, and isolated Python 3.11 dependencies.
Runtime and development dependencies are declared in `pyproject.toml`; `uv.lock`
replaces the separate requirements lock following Tony's dependency review.
Shared uve pins are not modified.

The standalone package passes **266 offline tests on Python 3.11.14**, including
real stdio sessions. `test.sh` also passes formatting/static checks and builds a
wheel and source archive without an isolated build environment.

The September 15 dependency follow-up passes the same 266 tests after a fresh
`uv sync --locked` installation with uv 0.12.14. Default `uv sync` includes the
runtime package and test/build tools; the client is still pinned to the same
review commit. This follow-up changes dependency declarations, the lock, and
setup documentation, with no MCP tool implementation changes.

Regression tests exercise the real client with synthetic HTTP, including no
initialization telemetry, legacy completed-receipt replay without submission,
response bounds, authentication/permission rejection, uncertain outcomes,
V2/V3/locomotion routing, uploads, previews, and export options. Historical live
results below predate the client migration and do not prove live acceptance of
the new client path. No new paid generation is needed for offline migration tests.

## Cleanup regression evidence

The pre-review cleanup adds real stdio retries with omitted versus explicit
numeric defaults, historical hash compatibility, and pending/unknown/rejected
state checks. V3 inputs are limited to ordinary-account 1000-character prompts
and whole seconds from 4 to 10; unsupported historical inputs are recoverable
through `get_request_status` without another generation. Cost estimation still
uses the supplied output quantity and does not round it to requested seconds.

Character-upload contract tests check the upload-specific 360-second HTTP phase
timeouts (15 seconds to connect), leaving other requests at 180 seconds. They
verify bounded compatibility warnings, truncation, absent messages, and replay.
These are transport assertions, not a live five-minute upload. Configure the host
to wait at least 420 seconds, longer for slow transfers, and inspect unresolved
receipts before any further submission.

Local recovery tests replace cached exports with FIFOs, directories, symlinks,
changed files, and oversized sparse files. The reader rejects them promptly,
retains known IDs, and makes no replacement request. Read bounds, size changes,
and integrity hashes are tested separately. Source-package inspection verifies
that the linked live acceptance report is included.

The V3 prompt/duration and synchronous character-processing contracts were checked
against main `0b7d0111807b9e62815b89a823619548ef9314ea` during this review.
No new live model calls or uploads were required for the cleanup. Actual host-agent
calls and reviews are documented separately in
[agent PR #1621's acceptance record](https://github.com/Uthana/uthana/blob/codex/agent-mcp-pilot/tools/agent/LIVE-ACCEPTANCE-2026-09-14.md);
that run used the MCP before this cleanup.

## 1. Text -> trim -> in-place export -> review

Use a prompt with three observable requirements, such as a short run, a jump,
and a stable landing. Keep the original prompt and write the requirements before
viewing the result.

1. Generate with a distinct `request_id`; poll the returned job. Restart the local
   server and recover the same receipt without a second generation.
2. Read the native metadata and inspect the APNG frames, including the action and
   contact transitions. Record the three most useful improvement suggestions,
   supporting each with available timestamps or frame indexes and uncertainty. Execute none of the suggestions.
3. On an explicit trim instruction, select an interval within the actual native
   duration. Verify a new motion ID, distinct bundle, expected frame count/FPS,
   original bundle ID/hash retained, and no looping. Native trim includes the
   final selected frame; at 30 FPS, 1 through 3 seconds selects 61 frames. Review the trimmed preview.
4. Export with `in_place=true`. Inspect the actual export to verify horizontal
   root travel is removed and vertical jump motion is retained. The original APNG
   is not evidence for this export-only effect. Native saved in-place editing is
   not implemented in this PR.

Backend references: `appserv/gql/mutations/ttm_job.py`,
`appserv/gql/mutations/motion.py::TrimAndLoopMotion`, `services/motion.py::trim_and_loop`,
`services/motion.py::create_bundle`, `poselib/skeleton/skeleton3d.py::SkeletonState.clip`, `appserv/views/app.py::png_image`,
`appserv/views/motion.py::_file`.

## 2. Video -> review -> optional host edit -> save

Upload one deliberately selected video using `generate_motion_from_video` and a
specific V2M version. Poll the same job and inspect the resulting motion. Record
which output the job selected; do not claim unreturned base/refined variants.

Arm adjustment is a follow-up implementation: the frontend has transform code,
but the API has no equivalent arm-adjustment operation. Do not invoke an invented
tool. If the host already has a validated editing skill, it may prepare animated,
self-contained GLTF for the specified character and call `save_motion` with the
source motion ID. Verify the new native bundle, preserved source, intended edit,
and preservation of unedited motion before calling that workflow accepted.

References: `appserv/gql/mutations/vtm.py`,
`ui/src/app/lib/scene/armRotation.ts`,
`appserv/gql/mutations/motion.py::CreateMotionFromGltf`,
`services/motion.py::create_motion_from_gltf`.

## 3. Saved result -> Roblox FBX at 30 FPS with mesh and skeleton

Choose a character whose metadata reports `engine=roblox`. Export the selected
saved motion using `format=fbx`, `fps=30`, `include_mesh=true`, and
`roblox_compatible=true`. Confirm that the file is FBX, has the expected mesh,
skeleton and animation, and imports correctly into Roblox Studio. Download with
the same request ID again and verify byte identity without a second download.

The backend rejects Roblox compatibility for other character metadata and non-FBX
formats. Native trim/save already creates a persisted motion; download creates a
local export, not another native motion.

Reference: `appserv/views/motion.py::_file`.

## 4. Two Mixamo characters -> one motion -> two retargeted exports

Place two owner-selected rigged FBX or GLB files in the configured input directory.
Upload them separately with `auto_rig=false`; keep both IDs and any compatibility warnings. Generate or reuse one
Uthana motion. Preview it on each uploaded character, then export each using its
own character ID, preserving the same source motion ID. Inspect both meshes,
contacts, skeletons, animation duration, and downstream imports. Repeated export
with the same request ID should return the original local artifact.

References: `appserv/gql/mutations/character.py::CreateCharacter`,
`appserv/views/motion.py::_file`.

## 5. Find and reuse existing motions

In an organization with known motion names, use `list_motions(query="walk")`,
then check `source=organization`, `source=examples`, a Method filter, and a second
page. Confirm returned IDs are usable with `get_motion` and preview. Test no
matches without triggering a generation. Confirm source labels are correct.
For an organization with at least 1000 recent motions, verify the truncation
signal and that the agent explains it cannot search older history or the full
shared library. Search here is name matching, not semantic retrieval. The old
`label_search` resolver returns a removal error and is deliberately not used.

References: `appserv/gql/query.py::Query.resolve_motions`,
`appserv/gql/query.py::Query.resolve_label_search`, `appserv/gql/objects/motion.py`.

## 6. Inspect usage and export eligibility without consuming an export

Compare `get_usage` against staging account records for a legacy account, an
active subscription, and PAYG. Check USD decimal precision, separate units,
subscription overrides, known zero versus missing values, and the absence of
legacy quota/sentinel limits for PAYG. Check `check_download_allowed` with an
allowed pair, a denied pair, and a previously downloaded pair after monthly
seconds are exhausted. Confirm no download record or billing change occurs.
Recheck actual export behavior separately; a read does not reserve an allowance.
Do not report account balances/rates as a measured cost for a particular job.

References: `appserv/gql/objects/user.py::Org`,
`appserv/gql/objects/subscription.py::Subscription`, `appserv/gql/objects/payg.py`,
`services/motion_download.py::download_allowed` and `download_secs_org_quota`.

## 7. Speed and torso-only export on the target rig

Export a known animation at 0.5, 1, and 2 speed with a fixed 30 FPS. Inspect output
frame counts, duration, and playback; backend resampling can round timing. Export
with `torso_only=true`, then combine it with `in_place=true`. Verify pelvis/leg
rotations are frozen to the target T-pose. Check pelvis-root and non-pelvis-root
rigs separately: root translation resets only for the former. Confirm no new
native motion is created, the source is retained, and native APNG remains unchanged.
Replay an export request and confirm identical local bytes; changing speed or
torso settings under the same request ID must fail without another export.
Offline tests also seed a receipt in the original format and verify recovery
with the new default options after upgrading.

References: `appserv/views/motion.py::_file`,
`poselib/tools/retarget_character_motion_bundle.py::retarget_character_motion`,
`poselib/skeleton/skeleton3d.py::modify_speed_multiplier` and `remove_non_torso_motion`.

## 8. Agent route selection and edit-versus-regenerate judgment

Using the bundled workflow in the selected host, test these requests and record
which tool the agent actually chooses. Offline protocol tests do not prove the
model makes these decisions correctly.

| Request | Expected approach |
| --- | --- |
| Generate a simple walk | TTM V2; receive a motion ID directly |
| Run, jump, and hold a landing pose | TTM V3; poll the returned job |
| Generate a loopable walk | Locomotion; inspect repeated playback at the seam |
| Improve foot contact on this otherwise-correct motion | Assess available editing skills; prefer a targeted correction if supported |
| Switch sword hands, add a 270-degree backswing, then hold | Prefer a new V3 prompt carrying forward unchanged requirements; retain and label the source |
| Same change, but preserve every unedited frame exactly | Explain regeneration tradeoff; do not silently substitute it |
| Review and give three suggestions only | No edits or regeneration |

Verify V2's `diffusion-v2` mapping, 1000-character prompt bound, and 0.4-second
increments (20 FPS, multiples of eight frames), with this pilot limited to 4–10
seconds. Verify locomotion's live style names, 1–5 strides, Manny-relative speed,
and direction. Both synchronous calls must recover the same receipt after a
successful submission; an unknown outcome must not be retried with a new ID.

References: `appserv/gql/mutations/ttm.py`, `services/ue5.py::UE5_FPS`,
`ml/bucmd/infer.py::BUCMDTTMInference`, `appserv/gql/mutations/locomotion.py`,
`services/ml/camdm.py::camdm_auto_steps`.

## 9. Published pricing and free platform operations

Product decision, September 14: capabilities on https://uthana.com/pricing keep
their published prices; unlisted platform operations are free. No separate
API/MCP or Uthana agent-token fee is applied. Future token-to-credit accounting
is outside this implementation.

Compare the public pricing page with staging `payg_prices` before release. Check
TTM V2/V3 and locomotion per-second estimates, auto-rig per-rig estimates, and
character-generation per-character estimates. The inspected rates were $0.03/s,
$0.10/s, $0.02/s, $0.15/rig, and $0.75/character respectively. Model-based stitch/loop
remains $0.01/s. Unit prices are fetched at runtime, not hardcoded into estimates;
keep the public capability mapping current and reconcile mismatches explicitly.

Verify free receipts for trim, saving supplied motion, export/retargeting, and
already-rigged upload. Auto-rig=true must remain a priced request with unknown
actual cost until accounted for. Check that unknown prices do not become zero,
USD estimates are not labelled measured credits, hidden backend SKUs are excluded
from public rates, and historical receipts are unchanged. No token fee is added.
Confirm actual provider accounting in staging separately; this PR does not alter
the billing backend or remove existing entitlement enforcement.

References: `services/payg.py::_PRICES`, `services/payg.py::get_model_prices`,
`services/motion_download.py::download_allowed`, public pricing page.

## 10. Failure handling and local recovery

The recovery tests use synthetic responses and local fixtures. They do not
establish live mutation rejection behavior or actual billing outcomes. Review
these cases before treating recovery as accepted in the selected host:

1. A confirmed authentication or permission rejection reports `state=rejected`
   with a safe category and next action, without raw provider content. Recognized
   GraphQL rejections must identify the root mutation and contain no partial
   success. A failed connection before submission can also be retried explicitly.
   Correct the reported cause and explicitly repeat the same request ID and
   arguments; verify one new submission. Changing arguments under that ID fails.
2. A timeout after submission may have started, nested or mixed GraphQL errors,
   partial data, or an interrupted submission remains `unknown`. Pending and
   unknown requests must not be resubmitted, including under a new ID. Use
   synthetic failure injection to test these cases without risking duplicate work.
3. Restart with the same private state and credential. Recover completed trim,
   save, and Roblox export receipts while upstream access is unavailable. IDs,
   historical source identity, and intact export bytes must remain recoverable
   without metadata or download calls. Trim/save recovery reports
   `verification_status=not_rechecked`; review this as historical recovery, not
   a new metadata or visual check. Known verification failures must remain visible
   in `previous_verification` after restart. A later metadata outage updates
   `last_verification_attempt` without erasing that conclusive historical finding.
4. Change trim arguments, save content/name/source/character, or export settings
   under a completed request ID. Verify rejection without another mutation.
   Repeating `save_motion` requires the original bytes; when its input file is
   gone, `get_request_status` must still return the saved motion ID locally.
5. In disposable local fixtures, remove or change an exported file, or replace it
   with a symlink. `get_request_status` must report
   `artifact_status=unavailable_or_changed`, retain known IDs, and download no
   replacement. An intact cache reports `verified_local_bytes`; this does not
   prove the file imports or animates correctly.
6. Upgrade a legacy receipt database and verify existing results remain intact.
   Concurrent explicit retries of a rejected request must claim one submission;
   pending/unknown requests stay blocked across process restarts.

References: `src/uthana_mcp/errors.py`, `src/uthana_mcp/store.py`,
`src/uthana_mcp/operations.py`, `tests/test_recovery.py`.

## Review decisions for Brandon and Tony

1. Review the standalone package boundary and shared Python-client integration. The prototype UI has not
   yet migrated to this shared Python operation layer.
2. Confirm staging schema/entitlements, conservative rejection classification,
   local recovery behavior, and the live acceptance cases with explicit test
   assets and actual usage accounting.
3. Decide whether native saved in-place and arm-adjustment operations should be
   introduced through shared backend code before expanding MCP tools.
4. Keep remote authenticated MCP hosting and public publication separate from
   the local package's initial review. No production switch or deployment is included.

For each live case, record host/version, staging environment, model/version where
applicable, request/job/motion/character/bundle IDs, export settings, source/result
hashes, observed evidence, known credits or unknown usage, and outstanding limits.
Keep credentials and customer assets out of the PR.

## Context7 documentation check

The public [Uthana Context7 library](https://context7.com/websites/uthana_api)
exists and its raw documentation is retrievable. On September 14, 2026, its public
page reported “Update: 2 months ago.” This is a freshness signal, not proof that
every retrieved example is incorrect. A configured Context7 MCP query session
has not been tested as part of this PR.

With Context7 available in the chosen host, retrieve documentation using the
exact library ID `/websites/uthana_api` for these questions:

- When should the agent choose V2, V3, or locomotion, and which returns a job?
- Which operations are free and what are the current published capability prices?
- How do native trimming and in-place export differ?
- How do I export Roblox-compatible FBX at 30 FPS with mesh and skeleton?
- How do I upload two rigged characters and retarget one motion onto each?

Compare retrieved examples with the current API/SDK and this package's tool
contracts. Record source URLs, version assumptions, missing coverage, and errors.
The existing public library covers API documentation; it should not imply that
this private draft is already a released MCP product.

Before release, publish approved MCP onboarding/workflow examples to Uthana's
public documentation, refresh the website library after that documentation is
deployed, and repeat these retrieval checks. Context7 supports a logged-in
[manual refresh](https://context7.com/docs/library-updates); background refreshes
can initially return the older index. Ownership and refresh access should be
confirmed by the documentation maintainer. No index refresh, private repository
submission, account setup, or documentation deployment was performed for this change.
