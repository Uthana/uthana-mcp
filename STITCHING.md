# Stitching workflow

## Try the simple operation first

Use `stitch_motions` with `request_id`, `prefix_motion_id`, `suffix_motion_id`, and
`character_id`. Uthana samples both clips and aligns them on the server; no local
Blender, pose sampler, or installed skill is required. Default transition: one second.

Optional `placement` contains `forward_m`, `right_m`, and `facing_degrees`, relative
to the prefix ending pelvis and facing. Positive angles turn right. Omitting the
forward distance continues recent travel; explicit zero requests no forward gap.
Try automatic placement first, and specify offsets/facing for scene requirements.
Match transition duration to the requested distance and inspect playback.

Optional trim fields use seconds. Omit ends for safe defaults. The server snaps
trims inward, reserves prefix context, and returns effective trims and connection
poses in `preparation`. Transition duration snaps to 20 Hz model frames. Avoid
guessing pose values, repeatedly submitting an unresolved request, or treating a
saved motion as visually approved. Use the existing request-recovery tools.

Requires the automatic stitching backend and Python client 0.6.0. Deploy the
backend first, release the clients, then release this MCP. Older backends reject
the new input; do not silently fall back to invented samples or a second mutation.

## Advanced sampled-pose operation

`create_stitched_motion` joins exactly two selected clips and returns a separate
motion. The upstream [enhanced stitching API](https://uthana.com/docs/api/capabilities/stitch-loop-motions)
is a preview; its contract can change. This MCP does not use the deprecated
ID-only `create_stitched_motion` GraphQL mutation despite the similar tool name.
The shared client calls `create_enhanced_stitched_motion`.

## Prepare real pose samples

Both clips must be evaluated on the chosen target character using a motion loader
such as the host's GLTF engine. Place the characters in the same world scene so
the leading clip's end and trailing clip's start have the intended spatial gap
and facing. Evaluate the animations at zero and the selected start/end times,
then update world matrices before reading transforms. Root and pelvis are distinct;
do not substitute one for the other. Use the facing convention described below.

A coding host may obtain animation assets through existing download tools, but
must preserve animation timing and avoid export-only in-place/speed/torso effects
that would make samples disagree with the motion. A preview image cannot
supply world transforms. The MCP does not download/evaluate/align animations for
this call; no loader or automatic pose-preparation skill is bundled here.

## Tool inputs

| Field | Contract |
| --- | --- |
| `request_id` | Request key; recovery rules are in WORKFLOW.md |
| `character_id` | Target rig for both samples; defaults to Tar |
| `prefix`, `suffix` | Complete clip objects described below; prefix plays first |
| `stitch_duration` | Transition seconds, 0.1-3 inclusive; default 2 |
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
and yaw values are bounded to -1,000,000 to 1,000,000. There are no pose defaults.
Native duration and trim fractions are computed by the MCP, not supplied by the
host. For the prefix, the API recommends sampling its upper trim slightly before
the clip boundary; it gives `duration - 0.051` seconds as an example.

Once the host has validated clip dictionaries, the MCP request is:

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

## Scale and yaw integration traps

A sampler that reads bone translations without composing ancestor scales can return centimeter-sized numeric coordinates where the API expects meters. The schema accepts these plausible finite numbers, so type validation will not catch the error. Do not treat any one export's root scale as a universal conversion constant.

A correct loader composes the full transform hierarchy, including root and ancestor translation, rotation, and scale, before extracting world positions. Checking character height and pelvis height in meters provides a useful unit check. This repository does not include a pose sampler or silently rescale supplied coordinates.

The backend convention is `forward = (left_hip - right_hip) cross up`, then `atan2(forward.x, forward.z)` (zero toward +Z, positive toward +X). Calibrate the selected hip joints against known forward facing before using it.

## Execution and verification

The host deadline is at least 420 seconds, longer for slow transfers. This synchronous operation reports MCP activity when given a progress token; it has no job ID. The result ID is saved before native verification reads. Both sources must remain unchanged, and the result must use a separate motion ID and source file.

Request recovery, output-second pricing, and review rules are defined in [WORKFLOW.md](src/uthana_mcp/WORKFLOW.md).
