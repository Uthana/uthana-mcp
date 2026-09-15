# TEST AGENT 2 — Uthana MCP tool-by-tool review (live staging, 2026-09-15)

Server under test: `uthana-mcp` PR #2 head `45c5b61`, 22 tools, staging credentials.
All calls made via `mcpcall.py` over SSH (fresh server process per invocation; durable state on box).

**Measured total spend: $1.749** (opening PAYG balance 1311.1305 → closing 1309.3815).
Caveat: other test agents may share the org, but my per-item estimate ($1.745 = V3 4.04 s × $0.10 + V2 3.97 s × $0.03 + locomotion 3.07 s × $0.02 + V2M 5.6 s × $0.05 + character-gen $0.75 + loop 4.05 s × $0.01 + stitch 9.4 s × $0.01) matches the delta to within half a cent — billing math checks out exactly against published rates × **actual** output seconds.

## Created IDs (this session)
| Kind | ID | From |
|---|---|---|
| Motion | mBBWHrCdL9sE | generate_motion_v2 (wave, 4 s → actual 3.97 s) |
| Motion | mjL2FVTpZDLc | generate_motion V3 via job Jg5sqmCkvwhC (superhero landing) |
| Motion | mJbVmLNUMAnq | generate_locomotion (zombie, 3 strides → "zombie-1.0-3steps-0deg", 3.07 s) |
| Motion | mbUTtMJoLLwQ | generate_motion_from_video via job JuafQNiN844e (5.6 s @ 10 fps) |
| Motion | mDFjtFsPJpQB | trim_motion "Dance intro (trimmed)" (0–4.4 s of mMLxCnVcuMmf) |
| Motion | mfQ8JVtAmxLW | create_looped_motion (closed loop of mTJwB6J51MX3; 4.05 s @ 20 fps) |
| Motion | muQ26uyUJS9b | create_stitched_motion (dance intro + cartwheel; 9.4 s @ 20 fps) |
| Motion | mDFMsp4wFA2a | save_motion (GLB→GLTF-JSON round trip of the trim) |
| Character | c3KJymK79zR2 | create_character_from_image ($0.75) |
| Character | (unknown) | upload_character t2-upchar-happy-0915 — outcome UNKNOWN, see M2 |

---

# Severity-ranked findings

## BLOCKER

**B1. `list_characters` is completely broken on this org — every call fails, including `limit=1`.**
Error: `Uthana response exceeded the configured size limit`. Root cause (read from code): `operations.py:394-401` pages **locally** (`rows[offset:offset+limit]`) after `api.py` fetches the entire upstream character list under a 2 MiB `max_response_bytes` cap (`api.py:31`). Once the org's character-list payload exceeds 2 MiB (it now does — the review agents' uploads likely pushed it over), no limit/offset can ever succeed. The tool that is the documented entry point for "use their IDs for preview and retargeted export" is unusable, and the error message offers no workaround (there is none).
Fix: pass offset/limit to the upstream query (server-side paging), or request a fields-reduced list; at minimum raise the cap for this read and say in the error that paging cannot help.

## MAJOR

**M1. Broken `list_characters` also breaks the documented recovery path.** When `upload_character` ended in `state=unknown` (M2), the receipt said `next_action: "Inspect staging; do not resubmit"`. The only MCP way to inspect whether the character got created is `list_characters` — which is down. An agent is left permanently wedged: cannot confirm, forbidden to resubmit. Recovery guidance should name a concrete tool that works (e.g. a `get_character(name)` lookup, or make the receipt store the provisional upstream ID).

**M2. `upload_character` happy path failed with an opaque uncertain-outcome error.**
Call: `t2-upchar-happy-0915`, `/home/viren/claude-work/mcp-inputs/rigged-figure.glb`, `auto_rig=false`. Failed within seconds (not a timeout):
`Uthana GraphQL request failed; submission may have been accepted. Inspect the saved request. Use get_request_status; do not resubmit an unconfirmed operation.`
The receipt (category `graphql_error`, `safe_to_resubmit: false`) contains **no upstream error detail whatsoever** — I cannot tell whether the file was rejected (bad rig? duplicate name from another agent's run?) or the mutation half-succeeded. The unknown-outcome discipline is correct and well implemented, but hiding the entire GraphQL error body makes the failure undiagnosable and unrecoverable. Fix: include a sanitized upstream error summary in the receipt. (Per rules I did not retry under a new ID, so the happy path is UNVERIFIED for this tool.)

**M3. Raw Python errno leaks for nonexistent input files.**
- `upload_character` with a host-style path: `[Errno 2] No such file or directory: 'C:'` — truncated at the drive colon, actively confusing.
- `generate_motion_from_video` with a nonexistent file: `[Errno 2] No such file or directory: '/home/viren/claude-work/mcp-inputs/does-not-exist.mp4'`.
Contrast: a traversal attempt (`../../../etc/passwd`) is caught cleanly with `Choose a supported file inside UTHANA_MCP_INPUT_DIR`. The containment check clearly runs, but the existence check leaks raw exceptions first/afterwards. Fix: normalize all file errors to the same message and name the input dir requirement.

**M4. Misleading error mapping for nonexistent motions on read paths.**
- `get_motion m0000notreal` → `Uthana denied this read request. Check account and asset permissions.` (It's not a permission problem; the motion doesn't exist.)
- `get_preview m0000notreal` → `Uthana could not serve this read request. Retry the read when the service is available. HTTP 404.` (Tells the agent to *retry* a permanent 404.)
- `get_job Jnope00000000` → `Uthana GraphQL request failed while reading data. No complete result was returned.` (Vague.)
An agent following these messages verbatim would re-check API keys or retry in a loop. Fix: map upstream 404/not-found GraphQL errors to "No such motion/job (or not visible to this account)".

**M5. `create_stitched_motion` demands data no tool in the server can produce, and the gap is a real trap.** I did succeed — but only by: downloading both GLBs, scp-ing them off the box, writing a ~180-line pure-Python GLB animation evaluator (accessor decoding, TRS hierarchy walk, slerp, quaternion math), and deriving hip yaw from thigh positions. Two traps consumed most of the effort:
  1. **Unit trap:** the exported rig's root node (`UE5_Manny_DEFORM.004`) carries scale ≈ 0.0116. A naive sampler that ignores node scale produces centimeter-scale positions (pelvis y ≈ 94.7). Those values are *within* the ±1e6 schema bounds, so the server would have accepted them silently — garbage in, paid garbage out. Nothing in the docs warns that the GLB export embeds a cm→m scale node.
  2. **Facing-yaw convention:** "hip-derived facing yaw" is underspecified (which axis is zero? CW or CCW positive?). I guessed atan2(fwd.x, fwd.z) with forward = (thigh_r − thigh_l) × up; the receipt honestly labels poses `host_supplied_not_independently_verified`, which also means the server cannot tell me if my convention was wrong.
Recommendation: ship a reference sampler script (even in STITCHING.md as copyable code), or better, an MCP tool/resource that returns pelvis/root samples for a motion at given times — the backend already has the animation. The current contract limits this tool to hosts with a 3D engine or unusual persistence.

## MINOR

**m1. Mojibake in tool descriptions.** `4�10 seconds` (generate_motion_v2), `90 right, -90 left, �180 backward` (generate_locomotion), `0�100 percentages` (create_looped_motion), `0.1�3 seconds`. En-dash/± became U+FFFD somewhere between source and tools/list. Partner-facing polish issue, and `�180` genuinely hides whether ±180 is meant.

**m2. `get_preview` → `get_preview_frame` linkage undocumented.** `get_preview_frame` requires `artifact_id`; no description says `get_preview` returns one. First-time agents can only discover the pairing by calling. One sentence in each description fixes it.

**m3. `save_motion` rejects a `.glb` inside the input dir with `Choose a supported file inside UTHANA_MCP_INPUT_DIR`.** The file *was* inside the dir; the real reason is the extension (only GLTF JSON is supported). Given that `download_motion` emits `.glb` by default, the natural round-trip hits exactly this misleading message. Say "save_motion requires .gltf (JSON); convert .glb first". (The conversion — embed the BIN chunk as a base64 data URI — works: mDFMsp4wFA2a saved and verified.)

**m4. Output FPS silently changes on loop/stitch.** Loop of a 30 fps source came back 20 fps (mfQ8JVtAmxLW); stitch of 24 fps sources came back 20 fps (muQ26uyUJS9b). Nothing in descriptions/WORKFLOW warns that stitch-loop output is resampled to 20 fps. Worth documenting for anyone with frame-accurate needs.

**m5. Preview timing is always unavailable and the payload is noisy.** Both APNG previews returned `frame_times_seconds` as an array of 40/94 explicit `null`s. The guidance ("cite frame indexes") is good, but sending 94 nulls per call is waste; summarize as `frame_times_seconds: null` when timing_status=unavailable.

**m6. Locomotion naming/param inconsistency.** `strides=3` produced `zombie-1.0-3steps-0deg`. The description defines a stride as "a pair of steps" — so is the output 3 strides or 3 steps? Actual duration 3.07 s at 1.0 m/s suggests the name's "steps" == the param's "strides". One of them is wrong.

**m7. Replayed async submissions show stale `provider_status: "READY"`.** Replaying `generate_motion` (t2-genv3-happy-0915) after the job FINISHED returns the original submission snapshot with READY. Correct-by-design (it replays the original result) but an agent may think the job regressed; a `replayed: true` note pointing to get_job would help (get_job does resolve it).

**m8. Motion names truncated at ~80 chars upstream** (`"...both hands on the floor and le"`) — makes `list_motions` word-matching miss tail words; not MCP's fault but worth surfacing.

## NIT

- Raw pydantic error dumps (with `https://errors.pydantic.dev/...` links) for schema violations; functional but verbose, and `Input should be a multiple of 1` is jargon for "whole seconds only".
- `trim_motion` out-of-bounds message `Require 0 <= start_seconds < end_seconds <= actual native duration` could include the actual duration value (agent then needs another get_motion call).
- `estimate_model_cost` duplicate-ish rates surface: `get_usage` exposes both `model_key` ("text-to-motion-bucmd") and `model` ("text-to-motion-2.0") — the internal bucmd key leaks.
- `list_characters {"limit":0}`/`list_motions {"limit":200}` → plain pydantic errors (fine).

## What is genuinely good (verified live)
- **Idempotency/replay is solid.** Same request_id + same args replays original result with `replayed: true` for generate_motion_v2 (paid — no double charge, confirmed by balance math), generate_motion, trim_motion, download_motion (same sha256/artifact). Same request_id + different args → clean `request_id was already used with different arguments`.
- **Billing transparency is real:** measured delta $1.749 vs my computed $1.745 from published rates × actual generated seconds. Every response carries a billing block; free ops report `free_by_policy` with 0.
- **Safety checks work:** path traversal blocked; tampered `source_bundle_sha256` rejected pre-submission with the excellent message `Sampled source bundle changed; inspect the current motion and resample before stitching`; BVH+mesh rejected with `BVH contains skeleton animation only; set include_mesh=false or choose FBX/GLB`; unknown style → `Unknown locomotion style; use list_locomotion_styles`; V2 duration 4.3 → `V2 duration must use 0.4-second increments from 4 to 10 seconds`.
- **Unknown-outcome discipline** (upload_character) held: receipt persisted, resubmission blocked, replay refused — exactly as documented, even though the diagnostics are lacking (M2).

## Stitch result (visual judgment)
muQ26uyUJS9b, 9.4 s, 188 f @ 20 fps, transition 4.365–5.365 s (preview frames ~44–54 of 94). Inspected frames 38/44/48/52/58/70: dance step → arms sweep out and gather (44–52) → weight shift and lunge (58) → inverted cartwheel (70). No teleport, facing flip, or floor penetration visible; the generated transition reads as a plausible "gather yourself, then cartwheel" beat. At 96-px preview resolution, foot slide and contact quality cannot be certified — needs the exported GLB in a viewer for sign-off.

---

# Phase A cold-read notes (verbatim, recorded before any live calls)

Cross-cutting:
- Several descriptions contain mojibake: "4�10 seconds", "90 right, -90 left, �180 backward", "0�100 percentages", "0.1�3 seconds". Looks like en-dashes/± got mangled to U+FFFD somewhere in the pipeline. Unprofessional for partner-facing surface; also "�180" hides whether it means ±180.
- Every mutating tool requires request_id but no tool description says what makes a GOOD request_id (uniqueness scope? per-operation? collision behavior?). Schema pattern alone doesn't tell me that reusing one replays.
- Tool descriptions never state the concrete price; they say "published model pricing applies" — I must know the model-key mapping (which is not given per tool) to use estimate_model_cost.

Per tool:
1. **generate_motion** — I think: submits async text-to-motion V3 job, poll get_job. Questions: Why is duration a `number` with multipleOf 1 instead of `integer`? Which estimate_model_cost key is this — "text-to-motion-3.0"? (not stated). "Preserve the user's prompt" — preserve it where/how? Would-get-wrong: nothing says the returned job can take minutes; nothing about polling cadence (workflow says 15 s, description doesn't).
2. **generate_motion_v2** — I think: synchronous simple-action generation, returns motion_id. Questions: schema allows any number 4–10 but text says 0.4-s increments — is 4.3 rejected, rounded, or accepted? Mojibake "4�10". "a timeout can mean an unknown outcome" — good warning but what do I DO then? (get_request_status, presumably — not referenced here.)
3. **list_locomotion_styles** — clear, no questions.
4. **generate_locomotion** — Questions: who/what is "Manny"? (I guess the UE5 mannequin; a first-time agent may have no idea.) How do strides map to seconds/cost — I cannot estimate price before calling since output seconds are unknown. Mojibake "�180 backward". What's in a style_id — must call list_locomotion_styles first (good that it says query styles).
5. **estimate_model_cost** — Questions: which tool maps to which model enum key? generate_motion → text-to-motion-3.0? create_looped_motion → stitch-loop-2.0? Guessable but unstated. "text-to-motion-1.0" and "autorig" have no obvious execution tool — description does address this ("a pricing entry does not imply an execution tool exists") — good.
6. **get_job** — terse. Questions: what are the possible status values? What does a failed job look like? "A finished job without a motion ID is unresolved, not success" is a genuinely useful warning.
7. **get_motion** — Questions: "native bundle identity" is jargon; I only later learn (stitching doc) why bundle id/hash matter. Fine otherwise.
8. **get_request_status** — I think: local receipt lookup for any past request_id. Questions: "verify cached export bytes without staging" — phrase is hard to parse ("staging" = re-uploading input? or the staging env?). What states exist? (workflow says rejected/pending/unknown/completed — description doesn't enumerate.)
9. **trim_motion** — clear: free, seconds in, new motion out, inclusive end frame. Question: is end_seconds beyond native duration rejected or clamped? "Metadata verification is not visual review" — good.
10. **get_preview** — Questions: WHERE does the preview go? Description doesn't say what the tool returns (a path? bytes? an artifact_id?). Critically, get_preview_frame needs an `artifact_id` and NOTHING says get_preview returns one — a first-time agent cannot connect the two tools from descriptions alone. "APNG reports timing availability" is grammatically confusing.
11. **get_preview_frame** — Question: where do I get artifact_id? (see above). Otherwise good guidance about sparse frames.
12. **generate_motion_from_video** — Questions: "May charge" — how much, which model key? What is UTHANA_MCP_INPUT_DIR set to and is file_path absolute or relative to it? Would-get-wrong: I'd probably pass a local (host-side) path — nothing says the path is interpreted on the server box.
13. **upload_character** — "Upload two characters separately with distinct IDs" — reads like a non-sequitur without the retarget-workflow context; confusing. Timeout guidance (>360 s) is concretely useful. Question: what happens with auto_rig=true on an already-rigged file?
14. **create_character_from_image** — clear about two stages + 1080 s + recovery discipline. Question: 1080 s exceeds many hosts' max tool timeout (Claude Code Bash max is 600 s) — description could acknowledge running it detached.
15. **create_looped_motion** — Dense but mostly good; the fractions-not-seconds callout is exactly the footgun I'd have hit. Questions: "May charge" — how is output seconds determined for a loop (source duration? zone?); "Published stitch/loop pricing is per generated output second, not just zone_duration" implies I can't predict the bill before calling. facing_angle in radians bounded ±1e6 — why not ±2π?
16. **create_stitched_motion** — I think: join two clips with a generated transition. Questions (many): How do I obtain root/pelvis world samples — which tool gives me the animation data? (download_motion, presumably, but the description says export effects could corrupt samples — which options are safe?) What node is "root" vs "pelvis" on Tar's rig — actual node names unknown. Is root_node_world_pos sampled at a time or scene placement? Where do the two characters GO in the shared scene — is overlap at origin acceptable? Would-get-wrong: I would absolutely have invented zero-ish placeholders if the description didn't forbid it; even wanting to comply, there is no bundled way to comply — the tool demands data no other tool in this server provides directly.
17. **list_characters** — clear.
18. **list_motions** — good scope warnings. Question: what are valid `method` values? (No enum, no examples — "TTM V2"? "text-to-motion-2.0"? Unknown. Live answer: "TextToMotion", "bucmd-ttm" — still undiscoverable a priori.)
19. **get_usage** — clear; "Null is unknown, not zero" good.
20. **check_download_allowed** — clear.
21. **save_motion** — Questions: "animated GLTF JSON" — does .glb count? (Probably NO since GLB is binary, but download_motion emits glb by default — the round-trip pairing pushes you toward an input save_motion will reject.) "for the exact target rig" — how do I verify rig match beforehand? Would-get-wrong: I'd try to feed a downloaded .glb straight back.
22. **download_motion** — Question: where do the bytes land (host? server box? returned inline)? Description says "Retry the same request_id for the saved bytes" — saved where? Otherwise the option semantics (torso_only overrides in_place, APNG doesn't show export effects) are unusually well documented.

---

# Per-tool call log (request_ids and outcomes)

| # | Tool | Calls (request_id) | Outcome |
|---|---|---|---|
| 1 | list_locomotion_styles | happy | PASS — 113 styles |
| 2 | list_characters | limit 10 / 3 / 1; limit 0 | **BLOCKER B1** — all fail with size limit; limit 0 → pydantic |
| 3 | list_motions | "cartwheel"; +method=bucmd-ttm; source=examples; limit 200 | PASS — good scope metadata; examples empty; 200 → pydantic |
| 4 | get_usage | happy ×3 (open/close balance) | PASS — used for exact spend measurement |
| 5 | estimate_model_cost | 6 models happy; bad model; quantity 0 | PASS — clean estimates; enum + gt-0 rejections |
| 6 | get_motion | 8× happy; nonexistent id; malformed id | PASS / **M4** misleading "permissions" error |
| 7 | get_job | J1b5pRsvx13h, JYncU4cbUYVy, Jg5sqmCkvwhC (poll), JuafQNiN844e (poll); bad id | PASS / **M4** vague not-found |
| 8 | get_request_status | trim, v2m, stitch, upchar receipts; never-used id → not_found | PASS — replay semantics (`not_rechecked`) correct |
| 9 | check_download_allowed | mMLxCnVcuMmf (allowed, "User is admin"); nonexistent id (allowed:false) | PASS |
| 10 | get_preview | m6L6P35ot1jo apng; muQ26uyUJS9b apng; mBBWHrCdL9sE webm; nonexistent id | PASS / **M4** "retry" advice on 404; **m5** null spam |
| 11 | get_preview_frame | 7 frames across 2 artifacts; frame 999; bad artifact | PASS — clean range + not-found errors |
| 12 | generate_motion (V3) | t2-genv3-happy-0915 (→Jg5sqmCkvwhC→mjL2FVTpZDLc); duration 3; duration 4.5; replay | PASS — replay `replayed:true` (**m7** stale READY) |
| 13 | generate_motion_v2 | t2-genv2-happy-0915 (→mBBWHrCdL9sE); t2-genv2-incr-0915 (4.3 s, rejected); replay; changed-args replay | PASS — exemplary increment error and replay behavior |
| 14 | generate_locomotion | t2-loco-happy-0915 (→mJbVmLNUMAnq); t2-loco-badstyle-0915 | PASS (**m6** strides/steps naming) |
| 15 | generate_motion_from_video | t2-v2m-happy-0915 (→JuafQNiN844e→mbUTtMJoLLwQ); t2-v2m-badpath-0915 | PASS / **M3** errno leak |
| 16 | upload_character | t2-upchar-happy-0915 (UNKNOWN outcome); t2-upchar-badpath-0915 | **M2 + M3** — happy path unverified |
| 17 | create_character_from_image | t2-imgchar-happy-0915 (→c3KJymK79zR2, ~6 min); t2-imgchar-badpath-0915 (traversal blocked) | PASS |
| 18 | trim_motion | t2-trim-happy-0915 (→mDFjtFsPJpQB); t2-trim-oob-0915; replay | PASS |
| 19 | create_looped_motion | t2-loop-happy-0915 (→mfQ8JVtAmxLW); t2-loop-badpct-0915 | PASS (**m4** 20 fps output) |
| 20 | create_stitched_motion | t2-stitch-happy-0915 (→muQ26uyUJS9b); t2-stitch-badsha-0915 (tampered sha rejected) | PASS with heavy host-side effort (**M5**) |
| 21 | save_motion | t2-save-happy-0915 (→mDFMsp4wFA2a); t2-save-png-0915; t2-save-glb-0915 | PASS / **m3** misleading .glb rejection |
| 22 | download_motion | t2-dl-glb-0915; t2-dl-fx-0915 (0.5× + in_place); t2-dl-glb-0915 replay (same sha); t2-dl-suffix-0915; t2-dl-badbvh-0915 | PASS — replay byte-identical |

Idempotency replays performed (requirement ≥3 mutating): generate_motion_v2, generate_motion, trim_motion, download_motion — all correct; plus changed-args rejection on generate_motion_v2.
