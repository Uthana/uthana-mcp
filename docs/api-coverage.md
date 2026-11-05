# API coverage

The MCP uses the shared Uthana Python client and exposes 24 tools for the configured environment.

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
| Billing reads | Model estimate, balance/rates, allowances, export eligibility | No recharge, billing mutation, or ledger tool |
| Recovery | Durable local receipts and cached export verification | No upstream cancel or automatic ambiguous-request resubmission |

The MCP does not yet cover every Uthana API capability. Full shared-library search, general scene editing, bulk operations, deletion, billing administration, and a complete API explorer are outside this surface. A price entry or public API example does not imply a corresponding execution tool.

The MCP runs two ways, and both call the same Uthana API with production as the default. The hosted server at `https://mcp.uthana.com/mcp` is Uthana's production service: clients connect over Streamable HTTP and sign in with OAuth, files arrive as `input_file` handles from the file portal or a supported attachment integration, and previews and exports return download links. It registers one additional tool, `get_artifact_download`, which renews a cached file's link without another export. The open-source connector runs locally over stdio on Linux, macOS, and Windows with an API key, reads selected files from `UTHANA_MCP_INPUT_DIR`, and saves exports on the machine running it. Server-prepared stitching works on both. See [hosted integration](hosting.md) and [local installation](installation.md). Tool results currently use flexible JSON objects; a versioned, field-specific output schema remains future work.
