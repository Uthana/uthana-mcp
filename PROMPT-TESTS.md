# Example prompts and expected outcomes

This catalog is a reusable acceptance script and capability guide. Examples describe intended behavior, not results of a particular test run. Use [ACCEPTANCE.md](ACCEPTANCE.md) to record execution and quality separately.

## Fixture and execution contract

Replace uppercase placeholders with accessible assets or request IDs from the **selected account and environment**. Do not paste literal placeholders into tools. Create fixtures through the connector or select tester-owned, redistributable assets: an existing motion, two motion clips, a target character, a supported Roblox character where needed, a short video, rigged FBX/GLB files, a PNG/JPEG, and editor-produced self-contained animated GLTF JSON. Store uploads inside the configured input directory. Not every account has every model entitlement or character.

Every row has three prompt variants. Run only the variants needed for the acceptance scope; running them all incurs model charges. Obtain a spending budget, inspect current pricing, preserve prompt intent, and choose a fresh durable request ID for each intentional mutation. Recovery variants use an existing ID and its original arguments. Read-only and review-only prompts must not trigger generation or edits.

Judge each case separately for tool selection/protocol, output identity, visual quality, and destination import where applicable. Mark missing prerequisites as blocked; never invent assets, pose samples, charges, or successful inspections. Persist private fixture IDs and results outside this catalog. [WORKFLOW.md](src/uthana_mcp/WORKFLOW.md) owns shared request, pricing, and review rules.

## Tool scenarios

### Styled or compound motion

Tool: `generate_motion`.

- "Create a four-second motion: run, jump, then hold the landing."
- "Make a theatrical bow with expressive hand and finger movement."
- "Generate a four-second cartwheel."

**Expected:** Use V3 unless the user chose another model; estimate cost, submit once, poll with get_job, inspect metadata and preview frames. Check action order, landing hold, style/fingers, or inversion respectively; do not claim fine finger/contact quality from insufficient images.

### Fast basic placeholder

Tool: `generate_motion_v2`.

- "Give me a quick four-second placeholder walk; detail is unimportant."
- "Use V2 for a four-second basic turn for previz."
- "Create a fast four-second basic jump placeholder."

**Expected:** Use V2 for these explicit speed/basic requests, return a motion ID, and inspect the requested action. Explain that V2 has no finger animation. About five seconds is an expectation, not a guaranteed deadline.

### Find a usable cycle style

Tool: `list_locomotion_styles`.

- "Which locomotion styles can I choose?"
- "Show me the available walk/run cycle styles."
- "Find a suitable available style before generating a walking loop."

**Expected:** Return actual styles from the API. Choose only a returned style identifier; do not invent a style from its desired name.

### Loopable locomotion

Tool: `generate_locomotion`.

- "Create a neutral walking cycle using two strides."
- "Create a loopable run using an available style."
- "Make a walking cycle traveling to the right using an available style."

**Expected:** Select an available style, explain speed/direction units, and generate once. Duration follows strides. Review travel/facing and multiple cycles; matching first/last images alone does not prove a smooth loop.

### Quote published model usage

Tool: `estimate_model_cost`.

- "Estimate a four-second V3 generation; do not generate it."
- "Compare the estimates for four seconds of V2 and V3."
- "Estimate the cost of generating one character from an image."

**Expected:** Return current rate, quantity, billing unit, USD estimate, and unknown actual charge. Do not mutate, convert credits without evidence, or interpret missing rates as free.

### Follow an existing job

Tool: `get_job`.

- "Check JOB_ID and show its motion when finished."
- "My generation is still running; inspect JOB_ID without starting another."
- "Explain why JOB_ID failed and what I can do next."

**Expected:** Read the existing job; poll at the workflow interval when needed. FINISHED without a motion ID is unresolved. A missing ID is not-found, not an outage or permission claim without evidence.

### Inspect native motion data

Tool: `get_motion`.

- "What is the native duration and frame rate of MOTION_ID?"
- "Inspect MOTION_ID before choosing trim boundaries."
- "Get the exact source identity of MOTION_ID for sampling."

**Expected:** Return available native frame/timing and source identity. Preserve unknown values. Metadata does not prove visual quality; do not generate another motion.

### Recover without duplicates

Tool: `get_request_status`.

- "The tool timed out; inspect REQUEST_ID before doing anything else."
- "After restarting, recover the output of REQUEST_ID."
- "Was REQUEST_ID completed or is its outcome still unknown?"

**Expected:** Use the same persistent state and environment/key scope. Report stored state and known IDs; refresh a known job separately. Unknown/pending requests must not be bypassed using a new request ID.

### Keep a source interval

Tool: `trim_motion`.

- "Keep the middle two seconds of MOTION_ID as a new motion."
- "Trim MOTION_ID to the selected valid interval START_SECONDS through END_SECONDS."
- "Remove the ending from MOTION_ID while preserving the original."

**Expected:** Inspect native timing, resolve an unambiguous valid interval, save separately, and report actual rounded frame bounds. Verify the source is unchanged and inspect the retained action.

### Obtain review media

Tool: `get_preview`.

- "Get an APNG preview of MOTION_ID on CHARACTER_ID."
- "Show a preview of MOTION_ID before I download it."
- "Prepare frames so I can review the landing in MOTION_ID."

**Expected:** Obtain existing-motion preview media; use get_preview_frame for image delivery as needed. Report unavailable timing accurately. Do not claim export-only effects are visible in a native preview.

### Review evidence from frames

Tool: `get_preview_frame`.

- "Inspect frames around the jump in the cached preview."
- "Show the first, middle, and final frames of the cached APNG."
- "Review the saved preview and suggest improvements without applying them."

**Expected:** Use a preview artifact returned by get_preview; select valid frame indexes and cite them when timing is unavailable. State sampling limits, and make no edit/generation call for a review-only request.

### Video-to-motion

Tool: `generate_motion_from_video`.

- "Animate the motion from VIDEO_PATH."
- "Use video-to-motion 2.1 for VIDEO_PATH and inspect the result."
- "Check whether VIDEO_PATH meets upload requirements before submitting it."

**Expected:** Use a tester-selected supported video inside the input directory, inspect size and schema constraints, and submit only when requested. Poll the returned job and compare observed action with the input. Local replay=false does not prove a new upstream job or charge.

### Import a rigged character

Tool: `upload_character`.

- "Upload RIGGED_CHARACTER_PATH without auto-rigging it."
- "Import the two supplied rigged characters separately so I can preview a motion on both."
- "Inspect the receipt for my interrupted character upload before trying again."

**Expected:** Use supported selected FBX/GLB inputs. Set auto_rig=false for rigged assets; treat auto-rig as a separate priced choice when requested. Inspect actual rig usability. For uncertainty, inspect the saved request and catalog; a name match alone is insufficient to retry or claim success.

### Image to rigged character

Tool: `create_character_from_image`.

- "Create a character from IMAGE_PATH."
- "Turn this selected PNG into a rigged character and show what was created."
- "Resume my confirmed rejected image-generation request using its saved preparation."

**Expected:** Require supported single-frame PNG/JPEG and limits. Quote priced generation. Preparation ID alone is not a ready character. Resume only under documented receipt semantics and review the finished character.

### Loop an existing motion

Tool: `create_looped_motion`.

- "Make MOTION_ID into a closed loop."
- "Create an open loop from MOTION_ID that continues its travel."
- "Extend MOTION_ID with a transition rather than modifying its existing frames."

**Expected:** Inspect timing, resolve trim/loop choices, and use the simplified loop tool with real inputs. Return a separate motion, preserve source identity, and inspect repeated-cycle playback for pose, velocity, and travel discontinuities.

### Join two motions (advanced)

Tool: `create_stitched_motion`.

- "Join PREFIX_ID then SUFFIX_ID on CHARACTER_ID using my validated pose sampler."
- "Stitch the selected clip intervals with a two-second transition using their sampled poses."
- "Check whether I have enough data to stitch PREFIX_ID and SUFFIX_ID; do not generate yet."

**Expected:** Require both sources on the same character, identity hashes, native-time samples, full ancestor transforms, and calibrated hip yaw. Without these, explain the missing prerequisite and do not submit. A successful result needs playback review through the join; preserve both sources.

### Find character IDs

Tool: `list_characters`.

- "List one character available to my account."
- "Find characters whose name contains CHARACTER_NAME."
- "Show the next page of matching characters and explain the search scope."

**Expected:** Return a bounded page with scan/scope information. Filtering is local over a capped catalog; a limit of one does not reduce the upstream fetch. Report no matches within scope, not global nonexistence.

### Find an existing motion

Tool: `list_motions`.

- "Find recent organization motions with walk in the name."
- "Find MOTION_NAME among the motions I can search."
- "Show the next page of matching recent motions without generating anything."

**Expected:** Search the bounded recent organization/example window using documented name/source filters. Preserve teammate ownership context and state the window limitation. Inspect suitability instead of treating a name match as proof.

### Read balance and allowances

Tool: `get_usage`.

- "Show my current Uthana usage and available model rates."
- "Check my balance before estimating a generation."
- "Explain the returned credit balance and download allowance without changing my account."

**Expected:** Read only. Keep balance and allowance units separate and do not equate role exemptions with credits. Do not recharge, change billing, or invent an actual charge for an unmeasured operation.

### Check export eligibility

Tool: `check_download_allowed`.

- "Can I download MOTION_ID?"
- "Check export eligibility before preparing this download."
- "Explain why the account may or may not download MOTION_ID."

**Expected:** Read current eligibility for the requested motion. This does not reserve allowance; a zero allowance is not automatically a denial if the API grants another entitlement. Do not mutate account settings.

### Register an edited result

Tool: `save_motion`.

- "Save EDITED_GLTF_PATH as a new motion based on MOTION_ID for CHARACTER_ID."
- "Register this self-contained animated GLTF and preserve its source."
- "Check whether my supplied edited GLB can be used directly by save_motion."

**Expected:** Accept validated self-contained animated GLTF JSON for the selected character; preserve lineage and return a distinct motion. For binary GLB/FBX explain the unsupported format rather than renaming bytes. Editing/conversion requires a real host capability.

### Retarget and export

Tool: `download_motion`.

- "Export MOTION_ID on CHARACTER_ID as GLB at 30 FPS with mesh."
- "Download MOTION_ID as Roblox-compatible FBX at 30 FPS with mesh on ROBLOX_CHARACTER_ID."
- "Export MOTION_ID on both supplied character IDs, preserving the original motion."

**Expected:** Check eligibility; use the requested target and compatible options. Roblox needs a supported character and FBX; BVH cannot include mesh. Verify returned bytes and actual sampling/rig/mesh; claim destination compatibility only after import testing. Replaying an export must not regenerate the motion.

## Host skills are a separate capability

"Fix this motion's foot sliding" and "adjust its arm while keeping the other frames unchanged" require a suitable host editing skill or external editor. The MCP has no generic foot-contact or arm-repair tool. Without that capability, explain the limitation rather than pretending that trim, retarget, or save performs the repair. When an actual skill edits the data, validate and review the output, then register it through `save_motion`.

A request to swap sword hands, add a large backswing, and hold a new pose often favors a new V3 generation. Explain that it is regeneration and preserve unchanged requirements. If exact frame preservation is required, do not silently substitute regeneration.

A request to use V1 must receive an honest limitation: V1 pricing can be read but this MCP does not expose a V1 generation tool. V1/V2 have no finger animation; V3 does. Agent-written repairs and automatically prepared stitching poses must not be advertised as bundled connector capabilities.
