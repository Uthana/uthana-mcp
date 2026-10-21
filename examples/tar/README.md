# Tar example character

These Uthana-owned Tar source files are included for the first MCP workflow:

| File | Format | Size | SHA-256 |
| --- | --- | ---: | --- |
| [cXi2eAP19XwQ.glb](cXi2eAP19XwQ.glb) | Self-contained rigged GLB | 5,391,416 bytes | `8e7ff48acb9131c050fd21e47c31424dc124f42f57b80448bbf382189e12da78` |
| [cXi2eAP19XwQ.fbx](cXi2eAP19XwQ.fbx) | Rigged FBX | 14,358,332 bytes | `92d0720e797769bf2f04cb608b77ae55505c4ce76c2a5acce199f7aa01ed88b5` |

The GLB has one mesh, one skin with 79 joints, and no animation; it has no external buffer URI. A headless Blender import of the FBX found one armature with 79 bones, two mesh objects, and no action. The shared joint names include `pelvis`, `head`, and left arm/hand joints. These are static character inputs. They have not yet been uploaded and animated through this draft MCP release flow.

Use the GLB for the [first animation walkthrough](../../FIRST-RESULT.md); the FBX is an alternate source for host and engine checks. The existing Uthana character ID `cXi2eAP19XwQ` is a separate shortcut for accounts that can access it. Uploading either source file may return a different character ID; use the ID returned by `upload_character`.

Copyright Uthana, Inc.
