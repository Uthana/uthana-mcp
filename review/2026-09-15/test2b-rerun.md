# test2b — verification rerun of the review runbook (2026-09-15)

Server under test: `uthana-mcp` PR #2 head **1088c53** on `codex/image-character-loop` (fix commit for the pre-release review), live staging over SSH.
Baseline: TEST AGENT 2 pass at `45c5b61` (`test2-tool-test.md`, `test2-RUNBOOK.md`).
Run tag: `t2b` (all request_ids `t2b-*-0915`). All calls via `mcpcall.py` / `t2b_call.py` (a progress-token variant written for this run).

**Measured spend: $1.4637** (opening PAYG balance 1309.3815 → closing 1307.9178).
Itemized: V3 4.0417 s × $0.10 = 0.4042 + V2 3.9667 s × $0.03 = 0.1190 + locomotion 2.8 s × $0.02 = 0.0560 + video-to-motion **$0 (upstream dedupe, see 4.1)** + character-gen 0.75 + loop 4.05 s × $0.01 = 0.0405 + stitch 9.4 s × $0.01 = 0.0940 = **$1.4637 — matches the balance delta to the fourth decimal.** Well under the ~$4 budget.

## Verdict

**No regressions. All six targeted review fixes verified live. Ready for Brandon's human pass**, with one standing caveat: the `upload_character` happy path still fails (upstream/backend, not MCP — see 4.3), now with proper diagnostics and recovery instead of the previous wedge.

---

## Review-fix verification (a)–(f)

| Fix | Result | Evidence |
|---|---|---|
| (a) `list_characters` works at limit=1 and limit=50 | **PASS (B1 fixed)** | Both return rows; `scanned_count: 46324`, `pagination: "local_bounded_catalog"`, scope_note explains the 16 MiB catalog cap and local paging. Query filtering works ("Rigged" → 20 rows, "RiggedFigure" → 0). |
| (b) Absent motion/job/preview IDs → `category=not_found` | **PASS (M4 fixed)** | `get_motion m0000notreal`, `get_job Jnope00000000`, `get_preview m0000notreal` all return `{"category":"not_found", ... "Motion, character, or job not found or not accessible to this account. Verify the ID."}` (preview adds HTTP 404). No more "check permissions"/"retry when available" misdirection. |
| (c) Bad file paths → actionable message, no raw errno | **PASS (M3 fixed)** | Nonexistent server path and host-style `C:/nope.glb` both → `file_path must name a readable regular file inside UTHANA_MCP_INPUT_DIR on the MCP server`. Traversal still blocked (`file_path must be inside UTHANA_MCP_INPUT_DIR`). Zero `[Errno 2]` leaks anywhere this run. |
| (d) Every tool parameter carries a schema description | **PASS** | Programmatic scan of `tools/list` (22 tools, incl. `$defs` for stitch clip/pose objects): **0 properties missing a description**. |
| (e) 4 long tools report progress | **PASS — observed live** (not just code review) | With a `progressToken` over raw stdio: `upload_character` (started/stopped), `create_character_from_image` (started + "waiting for Uthana" heartbeat ~every 30 s, 18 ticks over ~9 min, completed), `create_stitched_motion` (started/completed), `create_looped_motion` (started/completed). |
| (f) V2 schema exposes the 0.4 s increment | **PASS** | `generate_motion_v2.duration_seconds`: `multipleOf: 0.4`, min 4, max 10, description "…in 0.4-second increments." Duration 4.3 now rejected at schema level. V3 correspondingly `multipleOf: 1`. |

Also re-verified: **mojibake gone** (m1 fixed — 0 U+FFFD across all 22 descriptions/schemas).

---

## Per-runbook-item results (PASS/FAIL/CHANGED vs baseline)

### Phase 0 — handshake
| Item | Result |
|---|---|
| 0.1 tools/list = 22, no mojibake | **PASS (CHANGED — mojibake fixed)** |
| 0.2 `uthana://workflow` | PASS — 10.4 KB markdown |

### Phase 1 — read-only
| Item | Result |
|---|---|
| 1.1 113 styles incl. zombie, neutral_male_a | PASS |
| 1.2 get_usage: balance 1309.3815, 9 rate rows | PASS |
| 1.3 estimate $0.4000 | PASS |
| 1.4 enum rejection | PASS |
| 1.5 quantity>0 rejection | PASS |
| 1.6 list_characters | **PASS (CHANGED — B1 fixed)**; see (a) above |
| 1.7 list_motions cartwheel: 3 motions + scope_note | PASS |
| 1.8 method=bucmd-ttm → only mTJwB6J51MX3 | PASS |
| 1.9 limit 200 → pydantic ≤100 | PASS |
| 1.10 get_motion mMLxCnVcuMmf: 24 fps / 193 f / 8.0417 s / bundle id+sha | PASS |
| 1.11 nonexistent motion | **PASS (CHANGED — M4 fixed, not_found)** |
| 1.12 malformed id → pattern rejection | PASS |
| 1.13 get_job J1b5pRsvx13h complete → mMLxCnVcuMmf | PASS |
| 1.14 nonexistent job | **PASS (CHANGED — M4 fixed, not_found)** |
| 1.15 never-used request_id → not_found | PASS |
| 1.16 check_download_allowed true ("User is admin") | PASS |
| 1.17 nonexistent → allowed:false + reason | PASS |

### Phase 2 — preview pipeline
| Item | Result |
|---|---|
| 2.1 apng, 40 frames, artifact_id (ART1 `0bb48edb0f434015b484a823ca3bc33b`), timing unavailable | PASS (m5 null-array spam **still present** — 40 explicit nulls) |
| 2.2 webm of mBBWHrCdL9sE | PASS |
| 2.3 nonexistent preview | **PASS (CHANGED — M4 fixed, not_found + HTTP 404, no "retry" advice)** |
| 2.4 frame 20 → image + metadata | PASS |
| 2.5 frame 999 → "Frame index is outside this preview" | PASS |
| 2.6 bad artifact → "Artifact not found in this credential's local state" | PASS |

### Phase 3 — text/locomotion (paid $0.579)
| Item | Result |
|---|---|
| 3.1 generate_motion → job JNyRU2z3m8xD, model text-to-motion-3.0 | PASS |
| 3.2 duration 3 / 4.5 rejections | PASS |
| 3.3 poll → FINISHED, motion **mF1k8f98EAQ8** (~105 s, 4.0417 s @24 fps) | PASS |
| 3.4 generate_motion_v2 → **mZF9hrvUL4Vy** (3.9667 s @30 fps) | PASS |
| 3.5 identical replay → replayed:true, same motion, $0 (balance-confirmed) | PASS |
| 3.6 same id + different prompt → "request_id was already used with different arguments" | PASS |
| 3.7 duration 4.3 | **PASS (CHANGED — now schema-level `multipleOf 0.4` pydantic rejection instead of the runtime prose message; fix f)** |
| 3.8 locomotion zombie strides=3 → **mSNAKy75Uk39**, 2.8 s @30 fps, name "zombie-1.0-3steps-0deg" | PASS (**m6 persists**: schema now says "stride pairs (two steps each)" yet upstream names it "3steps" and 2.8 s looks like 3 steps, not 6) |
| 3.9 bad style → "Unknown locomotion style; use list_locomotion_styles" | PASS |
| 3.10 replay 3.1 → replayed:true, same job | PASS (**m7 persists**: stale `provider_status: "READY"`, no pointer to get_job) |

### Phase 4 — video + characters (paid $0.75; video was $0)
| Item | Result |
|---|---|
| 4.1 generate_motion_from_video (fresh id t2b-v2m-0915) | **CHANGED**: upstream deduped the identical video — returned the *prior run's* job **JuafQNiN844e** already FINISHED (motion mbUTtMJoLLwQ) with `replayed:false`, and **charged $0** (balance-confirmed). Not an MCP defect, but `replayed:false` + someone else's finished job is surprising; worth one doc line. |
| 4.2 nonexistent file | **PASS (CHANGED — M3 fixed)** |
| 4.3 upload_character retest (fresh `t2b-upchar-happy-0915`, auto_rig=false, "Rigged Figure t2b") | **FAIL upstream — but CHANGED/IMPROVED**, see below |
| 4.4 host-style path | **PASS (CHANGED — M3 fixed)** |
| 4.5 create_character_from_image → **c96bNNF6Kqqf**, stage character_created, auto_rig_confidence 1.0, ~9 min, $0.75 | PASS (heartbeat progress throughout) |
| 4.6 traversal probe blocked | PASS |

**4.3 detail (M1/M2 verification).**
- Pre-check: `list_characters query="RiggedFigure"` → **0 matches** in 46,324 scanned — the prior wedged `t2-upchar-happy-0915` upload **never created a character**.
- `get_request_status t2-upchar-happy-0915` (old receipt): state unknown, `next_action: "Inspect list_characters using the original upload name. A name match is only a candidate; verify it in Uthana. Contact support with the request ID if unresolved."` + an `inspection` block naming the tool and arguments. Recovery path now exists and works (M1 fixed). Note: this pre-fix receipt's `inspection.arguments.query` is `""` (name wasn't stored then); new receipts store it.
- Fresh upload failed again in ~seconds with: "Character processing did not return a confirmed result. Inspect list_characters by name and get_request_status before another upload. If no usable character is found, contact Uthana support with the request ID and support reference." Receipt now carries `category: character_processing`, **`support_reference: "c07835bb2fceed64d1e2"`**, `upstream_summary`, `content_sha256`, and an inspection block with the exact query ("Rigged Figure t2b", → 0 matches, so no orphan character; `safe_to_resubmit: false`). Progress start/stop notifications were emitted.
- **Remaining issue:** `upstream_summary` just repeats the generic sentence — the underlying reason this GLB fails is still not diagnosable from the MCP side. The failure itself looks like a staging backend problem with this endpoint/file, to chase with the support reference. The happy path therefore remains unverified end-to-end.

### Phase 5 — trim/download/save (free)
| Item | Result |
|---|---|
| 5.1 trim → **m3UeBBmA9u3W**, 106 frames, verified_metadata | PASS |
| 5.2 OOB trim | **PASS (IMPROVED — message now includes the actual duration and received values: "…at most 8.042 seconds (received 5.0, 99.0)"; baseline nit fixed)** |
| 5.3 replay → replayed:true, not_rechecked | PASS |
| 5.4 get_request_status complete | PASS |
| 5.5 download glb → artifact b66704dbc9af47d8, sha 76360fc6… | PASS |
| 5.6 fx export → effective_in_place:true, different sha | PASS |
| 5.7 replay → identical sha | PASS |
| 5.8 BVH + mesh → clean rejection naming the fix | PASS |
| 5.9 suffix download | SKIPPED — suffix GLB already local from baseline; bundle id/sha re-verified unchanged via get_motion |
| 5.10 save_motion with .glb | **PASS (CHANGED — m3 fixed: "file_path must use .gltf inside UTHANA_MCP_INPUT_DIR; .gltf means self-contained JSON, not binary .glb")** |
| 5.11 full GLTF round trip | SKIPPED (optional; proven at baseline → mDFMsp4wFA2a) |

### Phase 6 — loop + stitch (paid $0.135)
| Item | Result |
|---|---|
| 6.1 loop → **m86ioX8V9dtJ**, 4.05 s, 81 f @20 fps | PASS (**m4 persists**: 30 fps source → 20 fps output still undocumented in descriptions/WORKFLOW/STITCHING) |
| 6.2 bad trim pcts | **PASS (IMPROVED — message now echoes received values)** |
| 6.3 pose re-derivation | PASS — reran `sample_poses.py` on the baseline GLBs after re-verifying both bundle ids/shas unchanged (prefix mDFjtFsPJpQB `ADY1MgYiShth`/8fa1ffd9…, suffix m6L6P35ot1jo `A8AqyjZs8wUe`/fd6bc677…). Pelvis y ≈ 1.065–1.375 m (meters — the documented ~0.0116 root-scale trap avoided), yaws within ±π. **STITCHING.md at 1088c53 now documents the scale trap and the observed yaw convention (M5 substantially addressed in docs; a reference sampler tool is still not shipped).** |
| 6.4 stitch → **mp6h9MXctbxU**, 9.4 s, 188 f @20 fps; `pose_samples_source: host_supplied_not_independently_verified`; both sources in receipt; progress emitted | PASS |
| 6.5 tampered sha (prefix → deadbeef…) | PASS — "Sampled source bundle changed; inspect the current motion and resample before stitching", rejected pre-submission, $0 |
| 6.6 transition frames 44/48/52/58 of 94 | PASS — continuous dance→gather→cartwheel-prep poses, no teleport/facing flip/floor break at preview resolution |

### Phase 7 — closeout
- Closing balance 1307.9178; **delta $1.4637 matches the itemized total exactly** (which also proves the deduped video call, both replays, and the rejected stitch charged $0).
- Request status sweep: all t2b mutating ids **complete** (genv3, genv2, loco, v2m, imgchar, trim, dl, dl-fx, loop, stitch); `t2b-upchar-happy-0915` **unknown** (documented above); pre-validation rejections (e.g. stitch-badsha, loco-bad) → `not_found` (no receipt written — consistent).

## Created IDs this run
| Kind | ID | From (request_id) |
|---|---|---|
| Job | JNyRU2z3m8xD | t2b-genv3-0915 |
| Motion | mF1k8f98EAQ8 | V3 superhero landing (via job above) |
| Motion | mZF9hrvUL4Vy | t2b-genv2-0915 (wave) |
| Motion | mSNAKy75Uk39 | t2b-loco-0915 (zombie) |
| (reused) Job JuafQNiN844e → mbUTtMJoLLwQ | — | t2b-v2m-0915 (upstream dedupe of baseline video job) |
| Motion | m3UeBBmA9u3W | t2b-trim-0915 |
| Motion | m86ioX8V9dtJ | t2b-loop-0915 |
| Motion | mp6h9MXctbxU | t2b-stitch-0915 |
| Character | c96bNNF6Kqqf | t2b-imgchar-0915 |
| Character | none created | t2b-upchar-happy-0915 (unknown/failed upstream) |
| Preview artifacts | 0bb48edb0f434015b484a823ca3bc33b (m6L6P35ot1jo apng), 011437a9ee764e098db964a0d38a5528 (mBBWHrCdL9sE webm), 0c5f6ca7af99453e9eddddcc9be3e16e (stitch apng), b66704dbc9af47d8ad041980ca3931ae / e067dfde00304f8b845dbe03d36be171 (trim GLBs) | — |

## Remaining issues (none blocking)
1. **upload_character happy path still fails upstream** (support_reference c07835bb2fceed64d1e2, content sha d6be8541…). MCP-side handling is now correct and recoverable; the backend failure itself needs chasing before the tool can be called verified. `upstream_summary` carrying only the generic sentence is the one diagnostics gap left from M2.
2. Minor carryovers, unchanged: m5 (40–94 explicit nulls in `frame_times_seconds` when timing unavailable), m4 (loop/stitch output resampled to 20 fps, undocumented), m6 (strides="pairs" in schema vs "3steps" upstream naming and ~3-step duration), m7 (replayed async submissions show stale `provider_status: READY` without a get_job pointer), m8 (upstream ~80-char name truncation).
3. Cosmetic/new: upstream video dedupe returns a finished prior job with `replayed:false` (doc note suggested); pre-fix unknown receipts have an empty `inspection.arguments.query`.
