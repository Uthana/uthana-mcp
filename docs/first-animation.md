# First animation and export

This walkthrough starts with [Tar's rigged GLB](../examples/tar/cXi2eAP19XwQ.glb), a Uthana-owned bipedal character supplied for the example. The [FBX version](../examples/tar/cXi2eAP19XwQ.fbx) is also available. Start with the GLB so the workflow covers uploading a character, generating motion, and exporting it. If your account already has Uthana's Tar character ID `cXi2eAP19XwQ`, you can skip upload and use that ID; check it explicitly because other characters may also be named Tar.

Tar is provided under the [Tar Demo Asset License](../examples/tar/LICENSE.md) for testing, evaluation, tutorials, and demos. Commercial evaluation is allowed; shipping Tar in a production game is not. Public demos must preserve Tar's appearance. Include the license when sharing editable Tar files. Processing Tar through Uthana is permitted under its service terms; Uthana retains the right to train on its own Tar assets. Do not authorize other processing services to train on Tar or derived materials. Use your own appropriately licensed character for a production game.

## Prepare

Choose how you connected:

- **Hosted:** follow the [connection guide](https://uthana.com/docs/api/capabilities/hosted-mcp), then ask your agent to show your account’s available balance and allowances without creating or changing anything. No local install or API key is needed.
- **Local:** [install and connect](installation.md), then ask your agent to show your account’s available balance and allowances without creating or changing anything. You can also run `uthana-mcp-smoke --api-read` with your API key configured in the terminal for a read-only account check.

If your account has access to Tar ID `cXi2eAP19XwQ`, use it and skip uploading. Otherwise download [Tar GLB](../examples/tar/cXi2eAP19XwQ.glb). The 5.4 MB file is self-contained, has a 79-joint skin, and contains no animation. [Hashes and the alternate FBX](../examples/tar/README.md) let you verify it.

- **Hosted:** sign in to the [file portal](https://mcp.uthana.com/files) with the account you connected to your agent. Upload the GLB and paste the upload details into your conversation. This makes the file available to your agent; it does not create a character yet.
- **Local:** save the GLB in the folder configured as `UTHANA_MCP_INPUT_DIR`. Give your agent the file's path in that folder.

Use the prompt below to upload the selected file as a character with `auto_rig=false`; Tar is already rigged. The returned character ID may differ from the source filename. If multiple characters are named Tar, select by ID.

To use **your own character**, replace the downloaded Tar file with a bipedal FBX/GLB you may upload. Use `auto_rig=false` for an already-rigged file. Use `auto_rig=true` only for an unrigged biped, then visually review the result before animating it.

## First prompt

> Read Uthana's workflow. Use the Tar character ID we selected. If we have not selected an existing character, upload the supplied `cXi2eAP19XwQ.glb` as my already-rigged Tar character with `auto_rig=false` and use the returned character ID. Check export eligibility and estimate the cost of a four-second V3 motion. Create a walk forward that ends in a wave on Tar. Keep each request ID for recovery, wait for the job, show preview frames, and export the chosen motion as FBX with mesh at 30 FPS for my game-engine demo. Report the character ID, motion ID, a download link or local export path, and anything that needs visual review.

The agent should choose a durable request ID for each mutation. `generate_motion` returns a job ID; `get_job` later returns a motion ID when complete. `get_preview` and `get_preview_frame` help review timing and action. With hosted access, your agent can fetch the exported file directly or give you a download link. Links expire after 15 minutes; ask for a fresh link to the same file if needed. Refreshing a link or retrieving the cached file does not export or charge again. Keep working links private. With local stdio, `download_motion` saves the export on the machine running the connector; keep its state directory across restarts. If a task is interrupted, ask the agent to check `get_request_status` before starting it again.

## Review the result

Open the exported file in the target editor or engine. Check that the expected skeleton and mesh are present, the character has the right scale and facing, the animation plays at the expected frame rate, and root motion behaves as desired. A successful Uthana export does not prove it imports and plays correctly in Unreal, Unity, Maya, Blender, or Three.js. Record the engine/editor version and import settings with any issue.

Try a visible, ordinary biped with separated arms and legs first. Already-rigged characters are generally the more direct retargeting path. For auto-rigging, avoid large wings, backpacks, held props, intersecting limbs, and flowing or rigged clothing until the specific character has been checked. If a result is poor, preserve the original asset and report the limitation rather than describing it as a supported success.
