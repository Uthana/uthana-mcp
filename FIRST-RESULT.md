# First animation and export

This walkthrough starts with **Tar**, a Uthana-owned rigged bipedal character. Use character ID `cXi2eAP19XwQ` so the assistant does not confuse it with another character named Tar. That ID was found in Viren's production account on October 21, 2026; each reader must confirm their own account can access it. If Tar is unavailable, use a rigged bipedal FBX or GLB that you own or have permission to upload. A downloadable Tar source file has not yet been added to this repository.

## Prepare

1. [Install and connect the MCP](PARTNER-SETUP.md), then run `.venv/bin/uthana-mcp-smoke`. A passing protocol check does not verify your API key; `--api-read` does one read-only account check after you configure a key.
2. Use `list_characters` to check that your account can access Tar ID `cXi2eAP19XwQ`. Names alone are ambiguous; Viren's account currently has two characters named Tar. If the ID is absent, use a character you have access to and state which ID you selected.
3. To use **your own character**, put its file in a dedicated local input folder and set `UTHANA_MCP_INPUT_DIR` in the MCP host configuration. The MCP process must be able to read it. Upload an already-rigged FBX/GLB with `auto_rig=false`; use `auto_rig=true` only for an unrigged biped, then visually review the result before animating it.

## First prompt

> Read Uthana's workflow. Check that my account can access Uthana's Tar character ID `cXi2eAP19XwQ`; stop and tell me if it cannot. Check export eligibility and estimate the cost of a four-second V3 motion. Create a walk forward that ends in a wave on Tar. Keep the request ID for recovery, wait for the job, show preview frames, and export the chosen motion as FBX with mesh at 30 FPS for my game. Report the character ID, motion ID, exported file path, and anything that needs visual review.

The agent should choose a durable request ID for each mutation. `generate_motion` returns a job ID; `get_job` later returns a motion ID when complete. `get_preview` and `get_preview_frame` help review timing and action. `download_motion` saves the retargeted file on the machine running the MCP. A completed export receipt should include a verified local artifact path. Keep the state directory across restarts and inspect `get_request_status` before retrying an uncertain operation.

## Review the result

Open the exported file in the target editor or engine. Check that the expected skeleton and mesh are present, the character has the right scale and facing, the animation plays at the expected frame rate, and root motion behaves as desired. A successful Uthana export does not prove it imports and plays correctly in Unreal, Unity, Maya, Blender, or Three.js. Record the engine/editor version and import settings with any issue.

Try a visible, ordinary biped with separated arms and legs first. Already-rigged characters are generally the more direct retargeting path. For auto-rigging, avoid large wings, backpacks, held props, intersecting limbs, and flowing or rigged clothing until the specific character has been checked. If a result is poor, preserve the original asset and report the limitation rather than describing it as a supported success.

This is a runnable procedure, **not a recorded production acceptance run**. Tar is available in the account checked above, but other accounts still need access verified. A downloadable Tar source file is not yet packaged, and game-engine import/playback remains to be validated.
