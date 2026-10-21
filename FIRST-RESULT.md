# First animation and export

This walkthrough uses a **rigged bipedal FBX or GLB that you own or have permission to upload**. A redistribution-cleared example character has not yet been selected for this repository. Do not substitute the Unreal mannequins or another vendor's character as a downloadable example without confirming its license.

## Prepare

1. Put your character file in a dedicated local input folder. Set `UTHANA_MCP_INPUT_DIR` to that folder in the MCP host configuration. The MCP process must be able to read the file.
2. [Install and connect the MCP](PARTNER-SETUP.md), then run `.venv/bin/uthana-mcp-smoke`. A passing protocol check does not verify your API key; `--api-read` does one read-only account check after you configure a key.
3. Use `list_characters` to check whether the character is already in your Uthana account. If it is, record its character ID and skip the upload. For an already-rigged file, upload with `auto_rig=false`. For an unrigged biped, use `auto_rig=true` and visually review the resulting character before animating it.

## First prompt

> Read Uthana's workflow. Use the rigged biped in my selected input folder, or its existing character ID if it is already uploaded. Check export eligibility and estimate the cost of a four-second V3 motion. Create a walk forward that ends in a wave. Keep the request ID for recovery, wait for the job, show preview frames, and export the chosen motion as FBX with mesh at 30 FPS for my game. Report the character ID, motion ID, exported file path, and anything that needs visual review.

The agent should choose a durable request ID for each mutation. `generate_motion` returns a job ID; `get_job` later returns a motion ID when complete. `get_preview` and `get_preview_frame` help review timing and action. `download_motion` saves the retargeted file on the machine running the MCP. A completed export receipt should include a verified local artifact path. Keep the state directory across restarts and inspect `get_request_status` before retrying an uncertain operation.

## Review the result

Open the exported file in the target editor or engine. Check that the expected skeleton and mesh are present, the character has the right scale and facing, the animation plays at the expected frame rate, and root motion behaves as desired. A successful Uthana export does not prove it imports and plays correctly in Unreal, Unity, Maya, Blender, or Three.js. Record the engine/editor version and import settings with any issue.

Try a visible, ordinary biped with separated arms and legs first. Already-rigged characters are generally the more direct retargeting path. For auto-rigging, avoid large wings, backpacks, held props, intersecting limbs, and flowing or rigged clothing until the specific character has been checked. If a result is poor, preserve the original asset and report the limitation rather than describing it as a supported success.

This is a runnable procedure, **not a recorded production acceptance run**. The repository currently has no downloadable character with confirmed redistribution rights, and game-engine import/playback remains to be validated.
