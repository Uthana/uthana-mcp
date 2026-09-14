# MCP API coverage

The staging pilot exposes 19 tools. It is a focused adapter, not full API parity.
This inventory reflects the source contracts reviewed at main commit
`5cc7d8a9df1134be2ecba748741949acd37d1668`. Live staging and host acceptance are
separate; see [ACCEPTANCE.md](ACCEPTANCE.md).

| Capability | Available through this MCP | Still outside this pilot |
| --- | --- | --- |
| Text generation | TTM V2 and V3, bounded duration, prompt/character; locomotion styles, strides, speed, direction | TTM1, advanced V2 controls, prompt enhancement |
| Jobs and recovery | Poll a known job; recover local request receipts | Organization job-history listing |
| Motion discovery | Name search, method/source filters, pages within the API's recent organization window and supplied examples | Semantic/full shared-library search, history beyond the backend's 1000-motion window; removed label-search endpoint is not used |
| Native motion edits | Trim with looping off; register already-edited animated GLTF | Loop, stitch, saved in-place editing, arm adjustment |
| Review | APNG/WebM previews and model-visible frames with timing when available; evidence-based review guidance | Custom cameras or an automatic motion-quality evaluator |
| Video | Selected video upload and V2M 2.0/2.1 job | Preserve original FPS/resolution options and target character at submission |
| Characters | Upload rigged FBX/GLB or request basic auto-rig; list available characters | Text/image character generation, rerig targets, facing/finger options |
| Export and retarget | FBX/GLB/BVH, 24/30/60 FPS, mesh, speed, torso-only, in-place, supported Roblox FBX | Minimal mesh mode, Unitree CSV, standalone character download; actual destination import remains acceptance |
| Usage | Read organization PAYG USD balance/rates, separate monthly allowances, specific download eligibility; published-capability USD estimates, free-operation receipts | Per-request measured model cost, ledger/download-history tools, spending enforcement, billing/subscription mutations |
| Asset organization | Read motion identity and basic listing | Rename/delete, labels, favorites, ratings, sharing |
| Host access | Local stdio server and bundled workflow; optional Context7 guidance | Authenticated remote hosting, production mode, public package release |

Speed, torso-only, and in-place are export effects. They do not create a saved
native revision and are absent from native APNG previews. Torso-only uses the
backend's rig-dependent pelvis/leg mask; it is not an arm editor.

Context7 retrieves API documentation. It does not expand the installed tool set.
Admin/internal APIs and payment-changing operations are not automatically exposed
for the sake of coverage.

Agent routing is guidance in `uthana://workflow`: V2 for simple actions, V3 for
compound actions or major choreography changes, and locomotion for loopable
travel. Local corrections favor capable editing skills. This is not a new
server-side reasoning engine or a claim that the prototype app has adopted it.

Published pricing is authoritative; unlisted operations are free. Auto-rigging,
model-based stitching/looping, and character generation remain priced capabilities.
No API/MCP surcharge or Uthana agent-token charge is implemented. Model estimates
use live backend rates and explicit units; actual per-job debit remains unknown.
