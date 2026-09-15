# Uthana MCP verification runbook (v1, from TEST AGENT 2's 2026-09-15 pass)

A rerunnable test plan for the 22-tool staging server. Hand this to a fresh agent after
the next MCP change. Ordered: free/read checks first, then paid, dependencies explicit.

## Conventions
- Call tools with the helper: `python <scratchpad>/mcpcall.py <tool> '<json>' [...]` (SSH, fresh process per run; state persists on the box).
- Long jobs: `python <scratchpad>/poll.py <JOB_ID>`.
- `<RUN>` = a short unique run tag, e.g. `r1-0917`. Every request_id below embeds it; a rerun MUST use a fresh tag (request_ids are permanent replay keys).
- Never change a request_id to retry an unresolved/unknown request; reuse the same one only for intentional replay of identical args.
- Existing fixtures (already paid for; verify they still resolve in step 3):
  - `mMLxCnVcuMmf` dance+cartwheel 8.04 s @24 fps; `mTJwB6J51MX3` cartwheel 3.97 s @30 fps; `m6L6P35ot1jo` cartwheel 4.04 s @24 fps; character Tar `cXi2eAP19XwQ`.
  - Old jobs: `J1b5pRsvx13h` → mMLxCnVcuMmf; `JYncU4cbUYVy` → m6L6P35ot1jo.
  - Server-side inputs: `/home/viren/claude-work/mcp-inputs/{dance-reference.mp4, rigged-figure.glb, character-snapshot.png}`.
- Expected paid total for the full pass: **≈ $1.80** (measure it: get_usage before and after; delta should match the itemized estimates below within a cent or two).

## Phase 0 — handshake (free)
1. `tools/list` → expect exactly 22 tools; scan descriptions for mojibake (U+FFFD) — should be FIXED (was present 2026-09-15).
2. `@resource uthana://workflow` → non-empty markdown.

## Phase 1 — read-only/free (no request_ids needed)
| Step | Call | Expect |
|---|---|---|
| 1.1 | `list_locomotion_styles {}` | ~113 styles incl. `zombie`, `neutral_male_a` |
| 1.2 | `get_usage {}` | `payg.balance_usd` present; record as OPENING BALANCE; 9 rate rows |
| 1.3 | `estimate_model_cost {"model":"text-to-motion-3.0","quantity":4}` | $0.4000 (or current rate) |
| 1.4 | `estimate_model_cost {"model":"text-to-motion-9.9","quantity":4}` | enum rejection listing valid models |
| 1.5 | `estimate_model_cost {"model":"text-to-motion-3.0","quantity":0}` | greater-than-0 rejection |
| 1.6 | `list_characters {"limit":10}` | **Watch item:** failed 2026-09-15 with "response exceeded the configured size limit" at every limit (BLOCKER B1). Must return Tar + others after the fix |
| 1.7 | `list_motions {"query":"cartwheel","limit":10}` | ≥3 fixture motions, `scope_note` present |
| 1.8 | `list_motions {"query":"cartwheel","method":"bucmd-ttm"}` | only mTJwB6J51MX3 |
| 1.9 | `list_motions {"limit":200}` | pydantic limit≤100 rejection |
| 1.10 | `get_motion {"motion_id":"mMLxCnVcuMmf"}` | fps 24, frames 193, duration 8.0417, bundle id+sha present |
| 1.11 | `get_motion {"motion_id":"m0000notreal"}` | should say motion not found (2026-09-15: misleading "check account and asset permissions" — M4) |
| 1.12 | `get_motion {"motion_id":"bad id with spaces"}` | pattern rejection |
| 1.13 | `get_job {"job_id":"J1b5pRsvx13h"}` | state complete, motion mMLxCnVcuMmf |
| 1.14 | `get_job {"job_id":"Jnope00000000"}` | should say job not found (2026-09-15: vague GraphQL failure — M4) |
| 1.15 | `get_request_status {"request_id":"<RUN>-never-used"}` | `state: "not_found"` |
| 1.16 | `check_download_allowed {"motion_id":"mMLxCnVcuMmf"}` | `allowed: true` with reason |
| 1.17 | `check_download_allowed {"motion_id":"m0000notreal"}` | `allowed: false`, reason |

## Phase 2 — preview pipeline (free)
| Step | Call | Expect |
|---|---|---|
| 2.1 | `get_preview {"motion_id":"m6L6P35ot1jo"}` | apng, 40 frames, `artifact_id` (SAVE as ART1), timing_status likely `unavailable` |
| 2.2 | `get_preview {"motion_id":"mBBWHrCdL9sE","format":"webm"}` | webm artifact (motion from prior pass; substitute any V2 motion) |
| 2.3 | `get_preview {"motion_id":"m0000notreal"}` | not-found error (2026-09-15: misleading "retry when service available, HTTP 404" — M4) |
| 2.4 | `get_preview_frame {"artifact_id":"<ART1>","frame_index":20}` | image + frame metadata |
| 2.5 | `get_preview_frame {"artifact_id":"<ART1>","frame_index":999}` | "Frame index is outside this preview" |
| 2.6 | `get_preview_frame {"artifact_id":"deadbeef00000000","frame_index":0}` | "Artifact not found in this credential's local state" |

## Phase 3 — text/locomotion generation (paid ≈ $0.59)
| Step | Call | Cost | Expect |
|---|---|---|---|
| 3.1 | `generate_motion {"request_id":"<RUN>-genv3","prompt":"A man crouches low, then leaps forward into a superhero landing pose.","duration_seconds":4}` | ~$0.40 | job_id (SAVE as JOB3); billing model text-to-motion-3.0 |
| 3.2 | `generate_motion` duration 3 / duration 4.5 (request_ids `<RUN>-genv3-dur3`, `-dur45`) | $0 | schema rejections (≥4; multiple-of-1) |
| 3.3 | `poll.py <JOB3>` | — | FINISHED with motion_id (SAVE as V3M); RESERVED→FINISHED within ~3 min |
| 3.4 | `generate_motion_v2 {"request_id":"<RUN>-genv2","prompt":"A man waves hello enthusiastically with his right hand.","duration_seconds":4}` | ~$0.12 | synchronous motion_id (SAVE as V2M2) |
| 3.5 | same call again, identical args | $0 | `replayed: true`, same motion_id, NO new charge |
| 3.6 | same request_id, different prompt | $0 | "request_id was already used with different arguments" |
| 3.7 | `generate_motion_v2` duration 4.3 (`<RUN>-genv2-incr`) | $0 | "V2 duration must use 0.4-second increments..." |
| 3.8 | `generate_locomotion {"request_id":"<RUN>-loco","style_id":"zombie","move_speed":1.0,"strides":3}` | ~$0.06 | motion_id (SAVE as LOCO); then `get_motion` — note actual duration; check name vs strides (m6) |
| 3.9 | `generate_locomotion {"request_id":"<RUN>-loco-bad","style_id":"not_a_real_style"}` | $0 | "Unknown locomotion style; use list_locomotion_styles" |
| 3.10 | replay 3.1 exact args | $0 | `replayed: true`, same job_id (note stale provider_status — m7) |

## Phase 4 — video + characters (paid ≈ $1.03)
| Step | Call | Cost | Expect |
|---|---|---|---|
| 4.1 | `generate_motion_from_video {"request_id":"<RUN>-v2m","file_path":"/home/viren/claude-work/mcp-inputs/dance-reference.mp4","name":"V2M dance reference (<RUN>)"}` | ~$0.28 (5.6 s actual) | job_id; poll → motion (10 fps) |
| 4.2 | same with `does-not-exist.mp4` (`<RUN>-v2m-bad`) | $0 | clean "no such file in UTHANA_MCP_INPUT_DIR" message (2026-09-15: raw errno leak — M3) |
| 4.3 | `upload_character {"request_id":"<RUN>-upchar","file_path":"/home/viren/claude-work/mcp-inputs/rigged-figure.glb","name":"RiggedFigure <RUN>","auto_rig":false}` — Bash timeout 600000 | $0 | character_id + compatibility warnings. **Watch item:** 2026-09-15 this failed fast with an opaque GraphQL error → state=unknown, unrecoverable (M2). If it fails: get_request_status, record, DO NOT resubmit |
| 4.4 | `upload_character` with host-style path `C:/nope.glb` (`<RUN>-upchar-bad`) | $0 | clean input-dir message (2026-09-15: `[Errno 2] ... 'C:'` leak — M3) |
| 4.5 | `create_character_from_image {"request_id":"<RUN>-imgchar","file_path":"/home/viren/claude-work/mcp-inputs/character-snapshot.png","name":"Snapshot character <RUN>"}` — run detached; took ~6 min on 2026-09-15 but allow 1080 s | $0.75 | character_id, stage `character_created`, auto_rig_confidence |
| 4.6 | `create_character_from_image {"request_id":"<RUN>-imgchar-trav","file_path":"../../../etc/passwd","name":"Traversal probe"}` | $0 | "Choose a supported file inside UTHANA_MCP_INPUT_DIR" (traversal must stay blocked) |

## Phase 5 — trim / download / save (free)
| Step | Call | Expect |
|---|---|---|
| 5.1 | `trim_motion {"request_id":"<RUN>-trim","motion_id":"mMLxCnVcuMmf","start_seconds":0,"end_seconds":4.4,"name":"Dance intro (trimmed <RUN>)"}` | new motion (SAVE as TRIM), 106 frames, verification `verified_metadata` |
| 5.2 | `trim_motion` start 5 end 99 (`<RUN>-trim-oob`) | "Require 0 <= start < end <= actual native duration" |
| 5.3 | replay 5.1 | `replayed: true`, `verification_status: "not_rechecked"` |
| 5.4 | `get_request_status {"request_id":"<RUN>-trim"}` | complete, replay-marked result |
| 5.5 | `download_motion {"request_id":"<RUN>-dl","motion_id":"<TRIM>","format":"glb","fps":24}` | artifact_id + local_path on box + sha256 (SAVE path as PREFIX_GLB) |
| 5.6 | `download_motion {"request_id":"<RUN>-dl-fx","motion_id":"<TRIM>","format":"glb","fps":24,"speed_multiplier":0.5,"in_place":true}` | `effective_in_place: true`; different sha than 5.5 |
| 5.7 | replay 5.5 | `replayed: true`, identical sha256 |
| 5.8 | `download_motion` format bvh + include_mesh true (`<RUN>-dl-bvh`) | "BVH contains skeleton animation only; set include_mesh=false or choose FBX/GLB" |
| 5.9 | `download_motion {"request_id":"<RUN>-dl-suffix","motion_id":"m6L6P35ot1jo","format":"glb","fps":24}` | GLB for stitch prep (SAVE as SUFFIX_GLB) |
| 5.10 | `save_motion` with `rigged-figure.glb` (`<RUN>-save-glb`) | rejection; should name required .gltf format (2026-09-15: misleading generic message — m3) |
| 5.11 | (optional full round trip) scp PREFIX_GLB local → convert to .gltf JSON (embed BIN chunk as base64 data URI) → scp to `/home/viren/claude-work/mcp-inputs/<RUN>-edited.gltf` → `save_motion {"request_id":"<RUN>-save","file_path":".../<RUN>-edited.gltf","source_motion_id":"<TRIM>","character_id":"cXi2eAP19XwQ","name":"Resaved (<RUN>)"}` | new motion, `verified_metadata`, same frame count/duration as TRIM |

## Phase 6 — loop + stitch (paid ≈ $0.14)
| Step | Call | Cost | Expect |
|---|---|---|---|
| 6.1 | `create_looped_motion {"request_id":"<RUN>-loop","motion_id":"mTJwB6J51MX3","loop_mode":"closed","zone_mode":"modify","zone_duration":1.0}` | ~$0.04 | new motion; NOTE output fps (was 20, source 30 — m4) |
| 6.2 | `create_looped_motion` trim_start_pct 0.9 trim_end_pct 0.2 (`<RUN>-loop-bad`) | $0 | "Require start < end and 0 < zone_duration <= 3 seconds" |
| 6.3 | Stitch prep: scp PREFIX_GLB + SUFFIX_GLB from box (`/home/viren/claude-work/mcp-state/<scope>/<artifact>.glb`); run `sample_poses.py` (in scratchpad; pure-Python GLB sampler). **Gotchas encoded there:** root node carries ~0.0116 scale (cm→m) — must propagate scale through the TRS chain or positions come out in cm; pelvis node name `pelvis`; yaw = atan2(fwd.x, fwd.z), fwd = (thigh_r − thigh_l) × up; prefix end sampled at native duration − 0.051; offset suffix so its start pelvis aligns with prefix end pelvis (x/z) | — | `stitch_args.json` with plausible values: pelvis y ≈ 1.0–1.4 m, yaw in ±π |
| 6.4 | `create_stitched_motion "$(cat stitch_args.json)"` with request_id `<RUN>-stitch`, sources TRIM (prefix, 0→dur−0.051) + m6L6P35ot1jo (suffix, 0→4.0), stitch_duration 1.0 | ~$0.09 | new motion ≈ 9.4 s; `pose_samples_source: host_supplied_not_independently_verified`; both sources in receipt |
| 6.5 | tampered-sha probe: same args, request_id `<RUN>-stitch-badsha`, prefix sha first 8 chars → `deadbeef` | $0 | "Sampled source bundle changed; inspect the current motion and resample before stitching" |
| 6.6 | `get_preview` on the stitched motion; `get_preview_frame` at ~44/48/52/58 of 94 (transition zone = prefix_end → +stitch_duration, scaled to preview frame count) | $0 | continuous poses, no teleport/floor break |

## Phase 7 — closeout (free)
1. `get_usage {}` → CLOSING BALANCE; delta vs opening ≈ itemized paid total (±$0.02). Any larger gap = billing regression (or concurrent org activity — check with the team).
2. `get_request_status` on every `<RUN>-*` mutating id → all `complete` (or documented unknown).
3. Record all created motion/character IDs in the report.

## Cleanup
- No delete tool exists in the MCP; created motions/characters accumulate in the org (they are cheap but pollute `list_motions` — prefix names with the run tag so they're identifiable).
- Remove `<RUN>-edited.gltf` from `mcp-inputs` via SSH if you staged one.
- Note: repeated runs grow the character list — which is what broke `list_characters` (B1). After the fix, verify paging works at whatever size the org has reached.
