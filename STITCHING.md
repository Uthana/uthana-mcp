# Stitching integration contract

`create_stitched_motion` joins exactly two selected clips and returns a separate
native motion. The upstream [enhanced stitching API](https://uthana.com/docs/api/capabilities/stitch-loop-motions)
is a preview; its contract can change. This MCP does not use the deprecated
ID-only `create_stitched_motion` GraphQL mutation despite the similar tool name.
The shared client calls `create_enhanced_stitched_motion`.

## Prepare real pose samples

Both clips must be evaluated on the chosen target character using a motion loader
such as the host's GLTF engine. Place the characters in the same world scene so
the leading clip's end and trailing clip's start have the intended spatial gap
and facing. Evaluate the animations at zero and the selected start/end times,
then update world matrices before reading transforms. Root and pelvis are distinct;
do not substitute one for the other. For facing yaw, derive the forward direction
from the hip bones as described in the API documentation.

A coding host may obtain animation assets through existing download tools, but
must preserve animation timing and avoid export-only in-place/speed/torso effects
that would make samples disagree with the native motion. A preview image cannot
supply world transforms. The MCP does not download/evaluate/align animations for
this call; no loader or automatic pose-preparation skill is bundled here.

## Tool inputs

| Field | Contract |
| --- | --- |
| `request_id` | Durable request ID, reused only with identical arguments |
| `character_id` | Target rig for both samples; defaults to Tar |
| `prefix`, `suffix` | Complete clip objects described below; prefix plays first |
| `stitch_duration` | Transition seconds, 0.1–3 inclusive; default 2 |
| `prompt` | Optional transition prompt, at most 1000 characters; default empty |

Each clip contains:

| Field | Contract |
| --- | --- |
| `motion_id` | Selected existing motion |
| `sampled_character_id` | Character used when evaluating the poses; must match the target |
| `source_bundle_id`, `source_bundle_sha256` | Native identity from `get_motion` before sampling; checked against current metadata |
| `start_seconds`, `end_seconds` | Sampled trim interval; ordered and within the final native sample, spanning at least one frame interval |
| `root_node_world_pos` | World-space root position `{x, y, z}` in meters; Y up, x/z horizontal |
| `root_node_world_rot` | Root world rotation `{x, y, z, w}`, approximately unit length |
| `at_zero_time`, `at_lower_trim_time`, `at_upper_trim_time` | Pelvis states sampled at zero/start/end respectively |

Each pelvis state contains `pelvis_world_pos` (the same vector shape),
`pelvis_world_rot` (the same quaternion shape), and
`hips_forward_facing_world_yaw` in radians. Extra fields, nonfinite numbers,
booleans in numeric fields, and invalid quaternion lengths are rejected. Position
and yaw values are bounded to ±1,000,000 in the pilot. There are no pose defaults.
Native duration and trim fractions are computed by the MCP, not supplied by the
host. For the prefix, the API recommends sampling its upper trim slightly before
the clip boundary; it gives `duration - 0.051` seconds as an example.

Once the host has actual validated clip dictionaries, the MCP request is:

```python
await session.call_tool("create_stitched_motion", {
    "request_id": request_id,
    "character_id": target_character_id,
    "prefix": sampled_prefix,
    "suffix": sampled_suffix,
    "stitch_duration": 2.0,
    "prompt": "",
})
```

The variables above are prepared inputs, not a built-in sampling function. The
receipt labels poses as `host_supplied_not_independently_verified`: schema checks
and a matching bundle hash cannot prove that a host sampled poses correctly.

## Recovery, pricing, and review

The SDK request allows 360-second HTTP phase limits and 15 seconds to connect.
Set the host deadline to at least 420 seconds, longer for slow transfers. This
is a synchronous API mutation; there is no job ID to poll. Its result ID is saved
before native verification reads, including failures reading either source.
Both source bundles must remain unchanged, and the result must use a separate
motion ID and bundle. Completed replay checks the full original clip arguments
locally; it does not contact Uthana or revalidate visuals. `get_request_status`
recovers the IDs without requiring pose files.

A confirmed rejection permits an explicit corrected same-ID/same-argument retry.
Pending or uncertain outcomes block submission; changing an ID is not recovery.
When correcting the actual intended inputs after a confirmed rejection, use a
new intentional request only after reconciling the old outcome. No automatic
paid retries or multi-clip loops are performed.

Estimate `stitch-loop-2.0` using expected generated output seconds and the current
published model rate. Transition duration alone is not the full output duration.
Actual debit stays unknown until measured; there is no added MCP/API fee.
Inspect native timing, playback through the join, contact, floor height, facing,
and travel before accepting the result. Model output quality and real host
sampling remain live acceptance work.
