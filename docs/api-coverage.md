# API coverage

The MCP exposes 35 local tools and 36 hosted tools; the hosted server adds `get_artifact_download`.

Agents can ask the server directly: `get_capabilities` and the `uthana://capabilities` resource return a read-only catalog of every reviewed Uthana operation with its status (`available`, `platform_only`, `planned`, `not_offered`), models, limits, required access, documentation link, this server's version, environment and registered tools, plus optional account eligibility for priced models. The catalog lives in `src/uthana_mcp/capabilities.py`; update it with any tool change (a test fails if a tool is missing from it).

| Capability | MCP coverage | Limit |
| --- | --- | --- |
| Capability discovery | `get_capabilities`, `uthana://capabilities` | Reviewed catalog, not a live platform probe; account rates read at call time |
| Text-to-motion V2/V3 | Generate, poll V3, inspect | V2/V3 duration limits appear in tool schemas |
| Video-to-motion (V2M) 2.0/2.1/3.0 | Selected-file upload and job polling | 128 MiB input limit |
| Text-to-motion V1 | Not a tool by design; listed as `platform_only` | Offered in the web app and API; use V2 or V3 here |
| Locomotion | Styles and cycle generation | Duration follows strides |
| Character upload / auto-rig | FBX/GLB and warning results | Synchronous; recovery may require catalog inspection |
| Character from image | Image preparation and generation | PNG/JPEG, 16 MiB, 16 megapixels, one frame |
| Character from prompt | Preview images, then finalize one preview | A preview can be finalized by only one request ID |
| Existing-motion loop | Simplified loop preview API | Contract may change |
| Two-clip stitching | `stitch` accepts two flat motion steps with server sampling and alignment | Requires the flat-contract backend and Python client 0.8.0; see [stitching](stitching.md) |
| Native motion edits | Trim and register edited GLTF | Custom pose editing belongs to host tools |
| Character listing | Name filter and result pages | Local filtering over a 16 MiB catalog; no upstream pagination |
| Motion search | Recent organization names and examples | Up to 1000 organization motions, not full library search |
| Library search | `copy_best_library_motion` copies the single closest shared-library or organization clip | Charged as library-search-1.0; one result, no candidate list, paging, or similarity-to-motion search |
| Inspection | Metadata, APNG/WebM, decoded APNG frames | Visual review belongs to the host |
| Export | Retargeted FBX/GLB/BVH, mesh, FPS, speed, torso, in-place, Roblox | Destination import requires separate verification |
| Robot export | Unitree G1 joint trajectory CSV at 24/30/60 FPS | One robot; playback and balance require separate verification |
| Billing reads | Model estimate, balance/rates, allowances, export eligibility, recorded PAYG ledger (`get_billing_history`) | No purchase, recharge, auto top-up or spending-limit change; invoices and receipts stay on the account page |
| Asset management | Rename, soft-delete and restore one character or motion your organization owns; download a character's own model | Built-in, example and other organizations' assets are refused; delete takes only the selected ID; deleted assets are not listed, so restore needs the ID; no deletion of uploaded source files or cached exports |
| Recovery | Durable local receipts and cached export verification | No upstream cancel or automatic ambiguous-request resubmission |

The MCP does not yet cover every Uthana API capability. Library browsing, similarity-to-motion search, general scene editing, bulk operations, source-file/cache deletion, billing administration, and raw API execution are outside this surface; `get_capabilities` reports each as planned or not offered. A price entry or public API example does not imply a corresponding execution tool.

The MCP runs two ways, and both call the same Uthana API with production as the default. The hosted server at `https://mcp.uthana.com/mcp` is Uthana's production service: clients connect over Streamable HTTP and sign in with OAuth, files arrive as `input_file` handles from the file portal or a supported attachment integration, and previews and exports return download links. It registers one additional tool, `get_artifact_download`, which renews a cached file's link without another export. The open-source connector runs locally over stdio on Linux, macOS, and Windows with an API key, reads selected files from `UTHANA_MCP_INPUT_DIR`, and saves exports on the machine running it. Server-prepared stitching works on both. See [hosted integration](hosting.md) and [local installation](installation.md). Tool results currently use flexible JSON objects; a versioned, field-specific output schema remains future work.
