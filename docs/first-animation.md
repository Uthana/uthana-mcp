# First animation and export

This walkthrough starts with [Tar's rigged GLB](../examples/tar/cXi2eAP19XwQ.glb), a Uthana-owned bipedal character supplied for the example. The [FBX version](../examples/tar/cXi2eAP19XwQ.fbx) is also available. Start with the GLB so the workflow covers uploading a character, generating motion, and exporting it. If your account already has Uthana's Tar character ID `cXi2eAP19XwQ`, you can skip upload and use that ID; check it explicitly because other characters may also be named Tar.

Tar is provided under the [Tar Demo Asset License](../examples/tar/LICENSE.md)
for testing, evaluation, tutorials, and demos. Commercial evaluation is allowed;
shipping Tar in a production game is not. Public demos must preserve Tar's
appearance. Include the license when sharing editable Tar files, and configure
processing services not to train on Tar or derived materials. Use your own
appropriately licensed character for a production game.

## Prepare

1. [Install and connect the MCP](installation.md), then run `uthana-mcp-smoke`. A passing protocol check does not verify your API key; `--api-read` does one read-only account check after you configure a key.
2. Download [Tar GLB](../examples/tar/cXi2eAP19XwQ.glb) into a dedicated local input folder and set `UTHANA_MCP_INPUT_DIR` to that folder in the MCP host configuration. The MCP process must be able to read it. The 5.4 MB GLB is self-contained, has a 79-joint skin, and contains no animation. [Hashes and the alternate FBX](../examples/tar/README.md) let you verify the downloaded bytes.
3. Upload the selected GLB with `upload_character` and `auto_rig=false`; it is already rigged. Use the returned character ID, which may differ from the source filename. If your account already has Tar ID `cXi2eAP19XwQ`, you may choose that ID instead and skip upload. `list_characters` verifies access. If more than one character is named Tar, select by ID.

To use **your own character**, replace the downloaded Tar file with a bipedal FBX/GLB you may upload. Use `auto_rig=false` for an already-rigged file. Use `auto_rig=true` only for an unrigged biped, then visually review the result before animating it.

## First prompt

> Read Uthana's workflow. Upload the selected `cXi2eAP19XwQ.glb` as my already-rigged Tar character with `auto_rig=false`; use the returned character ID. Check export eligibility and estimate the cost of a four-second V3 motion. Create a walk forward that ends in a wave on Tar. Keep each request ID for recovery, wait for the job, show preview frames, and export the chosen motion as FBX with mesh at 30 FPS for my game-engine demo. Report the character ID, motion ID, exported file path, and anything that needs visual review.

The agent should choose a durable request ID for each mutation. `generate_motion` returns a job ID; `get_job` later returns a motion ID when complete. `get_preview` and `get_preview_frame` help review timing and action. `download_motion` saves the retargeted file on the machine running the MCP. A completed export receipt should include a verified local artifact path. Keep the state directory across restarts and inspect `get_request_status` before retrying an uncertain operation.

## Review the result

Open the exported file in the target editor or engine. Check that the expected skeleton and mesh are present, the character has the right scale and facing, the animation plays at the expected frame rate, and root motion behaves as desired. A successful Uthana export does not prove it imports and plays correctly in Unreal, Unity, Maya, Blender, or Three.js. Record the engine/editor version and import settings with any issue.

Try a visible, ordinary biped with separated arms and legs first. Already-rigged characters are generally the more direct retargeting path. For auto-rigging, avoid large wings, backpacks, held props, intersecting limbs, and flowing or rigged clothing until the specific character has been checked. If a result is poor, preserve the original asset and report the limitation rather than describing it as a supported success.

This is a runnable procedure with downloadable inputs, **not a recorded production acceptance run**. The source assets have been structurally checked, but this exact upload → generation → export sequence and game-engine import/playback remain to be validated.
