# Live staging acceptance — September 14, 2026

The coding assistant completed a small live workflow through the real local stdio
MCP server: V2 walk, compound V3 action, locomotion walk, native trim, preview,
retargeted GLB export, and request recovery. Actual generation debits totaled
**$0.5705**. The tested free operations added no debit. The export review found a
prompt mismatch and identified three improvements; none was executed.

This is evidence for these cases on staging, not full API coverage, universal
motion quality, native host installation, or a production release.

## Host, scope, and provenance

- Host: this Codex desktop coding assistant, using an assistant-operated MCP
  `ClientSession`/stdio bridge; MCP SDK 1.30.0, Python 3.12, Linux.
- Environment: `staging.uthana.com`; target character Tar, `cXi2eAP19XwQ`.
- Generation/trim/export code: PR commit `0fecdec7eda40fd754c37172b23d06f58f4a1de1`.
  The APNG timing correction discovered during this run is included in this PR
  and was checked against the same cached live media after installation.
- The host chose the tools from the bundled workflow. No second reasoning model
  or automatic server-side prompt classifier made these choices.
- A private staging key initially failed authentication. After replacement,
  account access succeeded. The authentication message was verified against the
  real failure. No secret, account balance, or unrelated ledger entry is included here.
- The account has pay-as-you-go (PAYG) enabled and an admin role. Its export-eligibility result
  used the admin exemption; legacy quota and non-admin denial cases remain untested.

The original requests were preserved before viewing outputs:

| Case | Request | Tool and settings | Native result |
| --- | --- | --- | --- |
| Simple walk | A person walks forward at a relaxed, steady pace with natural alternating arm swings. | `generate_motion_v2`, 4 seconds | `mvjFD47DNcQ5`; 119 frames / 30 FPS = 3.9666667 s |
| Compound action | A person takes a short run forward, jumps once with both feet leaving the ground, then lands on both feet and holds a stable balanced landing pose. | `generate_motion`, 4 seconds | Job `JBE2BKRbRG3S`; motion `mLKoAPJkeFB9`; 97 frames / 24 FPS = 4.0416667 s |
| Loopable walk | Forward neutral walk with two stride pairs and a smooth loop seam | `generate_locomotion`, `strides=2`, `move_speed=1.2`, `style_id=neutral_male_a`, `travel_angle=0` | `maU9518ngxsJ`; 71 frames / 30 FPS = 2.3666667 s |

Durable request IDs were `accept-20260914-v2-walk`,
`accept-20260914-v3-compound`, and `accept-20260914-locomotion-walk`.
V2/locomotion returned motion IDs directly. V3 returned a job, which was polled to
completion. Fresh server processes recovered the original receipts without another
generation. V3's historical submission status remains distinct from its fresh job status.

## Preview evidence and the timing fix

The assistant inspected APNG samples for all three motions and the saved trim.
The two walking clips show alternating leg poses; locomotion's first/last sampled
poses are close. These 96×96 front previews do not establish precise contacts,
forward travel, continuous loop velocity, or artifact-free retargeting.

The actual V2 APNG has 40 frames and all encoded frame delays are zero. V3 also
has 40 frames; locomotion has 24 and the trim has 38. The previous adapter therefore
reported every timestamp and total duration as zero. The encoded files themselves contain zero delays. Assuming a renderer frame rate would not establish timing for an individual cached APNG.

The adapter now reports `timing_status=unavailable`, null timestamps, and null
preview duration when delays are missing, zero, or unusable. Frame indexes remain
available. `get_preview_frame` recalculates timing from hash-verified bytes, so old
cached zero-time metadata is corrected too. Valid encoded delays still work.
This was verified on the original live V3 cache without another media request.
The agent's review guidance now cites frame indexes when timestamps are unavailable.

## Native trim, export, and recovery

`trim_motion` request `accept-20260914-v3-trim` kept the requested 0.25–4.0 s
interval from `mLKoAPJkeFB9` with looping disabled. The backend's fractional floor
and inclusive-end behavior selected native frames **5–95**, producing new motion
`mBSW1MJKCY1S`: 91 frames / 24 FPS = 3.7916667 s. Actual frame bounds are reported;
requested decimal seconds do not imply exact sample alignment.

The new bundle is distinct and source identity remained unchanged. Metadata
verification passed, and its historical result survived recovery without a new
metadata call. The trim's APNG was inspected separately.

| Result | Bundle ID | SHA-256 |
| --- | --- | --- |
| V2 walk | `AntrgPeLhFE7` | `e54b90405f3e0dec85b896a8d61ca7d3ff23ddd16cd9259df72a79130e3b15da` |
| V3 source | `AojPuZfa8CDa` | `040c100d0abbce44509943c48841af5ad32df9e040be25d4738c71313127d197` |
| Locomotion | `AjUjYAoLmJjv` | `a9073b02e9d62dcc5d640d53dc5bcccabe355077921f1ff5f36db5e685ca7893` |
| Saved trim | `A9KmKguZteLV` | `6cb2f7e7b84c6fb2f837401eb2b419a7cc99c249631b022091ca1436d54d142b` |

Two exports used the saved trim, Tar, GLB, 30 FPS, mesh enabled, unchanged speed,
and torso-only/Roblox disabled. They differed only in `in_place`:

| Export | Request ID | SHA-256 |
| --- | --- | --- |
| Reference travel | `accept-20260914-export-travel` | `33d681acedb98f28184e1859049ce90b1d3de3549694a3a88a2a3713f014056a` |
| In-place | `accept-20260914-export-in-place` | `b80a4821c89458cf8f28a96c0e18e64219aa3464806b1469af48ca50093f5215` |

The actual files were parsed and loaded in an isolated Three.js viewer using
local assets only. Both contain one mesh, one skin with 79 joints, and one
animation with 55 rotation tracks plus pelvis translation. There are 113 animation
keys at approximately 1/30-second intervals; the final key is 3.733333588 s.
That key span is distinct from the native count/FPS duration; export resampling
rounds the endpoint.

Mesh attributes/indices, mesh and skin definitions, channel times, and all 55
rotation tracks match. In glTF asset coordinates, reference pelvis ranges are
X=0.030768655 m, Y=0.858932215 m, Z=0.949722053 m. In-place X/Z ranges are zero;
vertical motion differs by at most 1.77×10⁻⁷ m across exported keys. Front/side
visuals retain the airborne jump and landing. This checks the actual export,
not an unchanged native APNG. No new native motion is created by either export.

Repeating the identical in-place request in a fresh server process returned the
same artifact and SHA-256 with `replayed=true`, without an HTTP download.

## Three visual improvement suggestions

These times refer to the **trimmed export**, not APNG timestamps. Front and side
views were inspected at 0, 0.5, 1, 1.5, 2, 2.5, 3, and 3.733333588 seconds.

1. **Align the running travel with the character's facing, 0–1 s.** The reference
   side view shows the run traveling backward. Pelvis displacement is about
   0.50 m opposite the standing foot-to-ball facing estimate. That facing estimate
   is a geometric approximation, corroborated visually. The requested forward
   run is therefore not fully satisfied in this sample.
2. **Smooth the run-to-jump transition, 1.5–2 s.** The run visibly settles into a
   separate deep two-foot crouch before the jump. A more continuous transition
   would make the compound action read as one motion.
3. **Make the final landing hold clearer and longer, 3–3.733 s.** The bent-knee
   landing straightens toward neutral by the endpoint. A deliberate pause in the
   chosen final pose would communicate the requested hold more clearly. The
   prompt did not explicitly require holding the crouch itself.

The run, airborne jump, and landing are visible, but prompt-quality acceptance is
mixed. These findings do not establish an MCP malfunction or a universal model
failure. No correction, regeneration, or other suggested change was executed.
Sparse sampling is not a complete contact, collision, or deformation assessment.

## Published rates, estimates, and actual debits

All nine live `payg_prices` entries mapped by the MCP match the current
[official pricing page](https://uthana.com/pricing), checked September 14, 2026:
Text-to-motion (TTM) 1/2/3 = $0.02/$0.03/$0.10 per output second; video-to-motion (V2M) 2.0/2.1 = $0.05/s;
locomotion = $0.02/s; stitching/looping = $0.01/s; auto-rig = $0.15/rig;
character generation = $0.75/character. The page supplies no character-generation
version or numeric credits-to-USD conversion; `1.0` is the backend/MCP mapping.

| Model | Estimate before submission | Actual native seconds | Rate / second | Estimate using actual duration | Measured debit |
| --- | --- | ---: | ---: | ---: | ---: |
| TTM V2 | $0.1200 for requested 4 s | 3.9666667 | $0.03 | $0.1190 | $0.1190 |
| TTM V3 | $0.4000 for requested 4 s | 4.0416667 | $0.10 | $0.4042 | $0.4042 |
| Locomotion | No duration quote; stride-based request | 2.3666667 | $0.02 | $0.0473 | $0.0473 |
| **Total** | | | | **$0.5705** | **$0.5705** |

Read-only GraphQL ledger snapshots before/after the demo contained exactly three
new debit entries, each linked by `ref=motion:<generated motion ID>`. Their sum
matches the account balance decrease exactly. Ledger quantities round native
seconds to four decimal places. No other new entry or charge appeared for the
trim, APNG/WebM previews, two exports, eligibility/metadata/usage reads, or cached
replay. A final snapshot after the duration-based estimates was unchanged.

This ledger audit used the same credential through a separate read-only API
query; it is not a new MCP billing tool. MCP generation receipts correctly retain
unmeasured actual cost, and estimates remain estimates. No billing settings or
recharges were changed. Zero additional API/MCP/agent-token fees and free unlisted
platform operations follow the user's explicit product policy.

## Remaining limits

- No real video upload, two-Mixamo-character upload/retarget workflow, Roblox Studio
  import, host-edited GLTF save, auto-rig, or other priced model execution was tested.
- Free save and already-rigged upload have policy/offline coverage, not measured
  live debit evidence from this run. Non-admin and legacy allowance behavior remain
  separate acceptance cases.
- No precise continuous loop/contact guarantee is made from the walking previews.
- Native Codex/Claude Code configuration installation, authenticated remote hosting,
  public package/docs publication, and production rollout remain outside this run.
- Raw ledger data, credentials, generated binary assets, screenshots, and local
  measurement helpers remain outside Git. The operator retains private receipts
  and visual evidence; this document is the sanitized record for review.
