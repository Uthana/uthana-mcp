# API coverage

The MCP uses the shared Uthana Python client and exposes 25 tools for the configured environment.

| Capability | MCP coverage | Limit |
| --- | --- | --- |
| Text-to-motion V2/V3 | Generate, poll V3, inspect | V2/V3 duration limits appear in tool schemas |
| Video-to-motion (V2M) 2.0/2.1 | Selected-file upload and job polling | 128 MiB input limit |
| Locomotion | Styles and cycle generation | Duration follows strides |
| Character upload / auto-rig | FBX/GLB and warning results | Synchronous; recovery may require catalog inspection |
| Character from image | Image preparation and generation | PNG/JPEG, 16 MiB, 16 megapixels, one frame |
| Character from prompt | Preview images, then finalize one preview | A preview can be finalized by only one request ID |
| Existing-motion loop | Simplified loop preview API | Contract may change |
| Two-clip stitching | `stitch` accepts typed motion/transition/motion steps with server sampling and alignment | Automatic input requires the coordinated backend and Python client 0.6.0; see [stitching](stitching.md) |
| Native motion edits | Trim and register edited GLTF | Custom pose editing belongs to host tools |
| Character listing | Name filter and result pages | Local filtering over a 16 MiB catalog; no upstream pagination |
| Motion search | Recent organization names and examples | Up to 1000 organization motions, not full library search |
| Inspection | Metadata, APNG/WebM, decoded APNG frames | Visual review belongs to the host |
| Export | Retargeted FBX/GLB/BVH, mesh, FPS, speed, torso, in-place, Roblox | Destination import requires separate verification |
| Robot export | Unitree G1 joint trajectory CSV at 24/30/60 FPS | One robot; playback and balance require separate verification |
| Billing reads | Model estimate, balance/rates, allowances, export eligibility | No recharge, billing mutation, or ledger tool |
| Recovery | Durable local receipts and cached export verification | No upstream cancel or automatic ambiguous-request resubmission |

The MCP does not yet cover every Uthana API capability. Full shared-library search, general scene editing, bulk operations, deletion, billing administration, and a complete API explorer are outside this surface. A price entry or public API example does not imply a corresponding execution tool.

The transport is local stdio on Linux, macOS, and Windows. The local MCP calls the configured Uthana API; production is the default. Authenticated remote MCP hosting is separate work and is not required for server-prepared stitching. Tool results currently use flexible JSON objects; a versioned, field-specific output schema remains future work.
