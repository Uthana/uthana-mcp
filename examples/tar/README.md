# Tar example character

These Uthana-owned Tar source files are included for the first MCP workflow:

| File | Format | Size | SHA-256 |
| --- | --- | ---: | --- |
| [cXi2eAP19XwQ.glb](cXi2eAP19XwQ.glb) | Self-contained rigged GLB | 5,391,416 bytes | `8e7ff48acb9131c050fd21e47c31424dc124f42f57b80448bbf382189e12da78` |
| [cXi2eAP19XwQ.fbx](cXi2eAP19XwQ.fbx) | Rigged FBX | 14,358,332 bytes | `92d0720e797769bf2f04cb608b77ae55505c4ce76c2a5acce199f7aa01ed88b5` |

The GLB has one mesh, one skin with 79 joints, and no animation; it has no external buffer URI. A headless Blender import of the FBX found one armature with 79 bones, two mesh objects, and no action. The shared joint names include `pelvis`, `head`, and left arm/hand joints. These are static character inputs. They have not yet been uploaded and animated through this draft MCP release flow.

Use the GLB for the [first animation walkthrough](../../docs/first-animation.md); the FBX is an alternate source for host and engine checks. The existing Uthana character ID `cXi2eAP19XwQ` is a separate shortcut for accounts that can access it. Uploading either source file may return a different character ID; use the ID returned by `upload_character`.

Copyright Uthana, Inc.

## Usage permissions

These character files use the [Uthana Tar Demo Asset License 1.0](LICENSE.md), separately from the connector's Apache-2.0 license. The license is authoritative; this summary explains the intended workflow.

### Things to try

- Test and evaluate animation pipelines, including within a commercial team.
- Animate and retarget Tar; share demos, tutorials, screenshots, and videos.
- Make private appearance changes for testing.
- Share technical changes that preserve Tar's appearance, such as rig changes, mesh optimization, and format conversion.
- Include editable Tar files in tutorial and demo projects with the license and copyright notice. Public credit is optional.

### Things to avoid

- Publishing appearance changes, including changed clothing or textures, whether as editable assets or rendered images and videos.
- Shipping Tar in a game or product beyond a tutorial or demo.
- Selling Tar or distributing it standalone or in asset packs.
- Training or fine-tuning models on Tar or representations derived from it. Uthana retains the right to train on its own Tar assets, and processing Tar through Uthana services is permitted under the applicable service terms. Other processing services must not be authorized to train on these materials.

Use your own appropriately licensed character when preparing a production game.
