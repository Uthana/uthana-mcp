"""Two-source stitch validation and recovery with synthetic sampled motion poses."""

import asyncio
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from uthana.graphql import q

import uthana_mcp
from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.stitching import StitchClip, api_clip
from uthana_mcp.validation import TAR


def clip(motion_id="motion1"):
    pose = {
        "pelvis_world_pos": {"x": 1, "y": 0.9, "z": 2},
        "pelvis_world_rot": {"x": 0, "y": 0, "z": 0, "w": 1},
        "hips_forward_facing_world_yaw": 0.2,
    }
    return {
        "motion_id": motion_id,
        "sampled_character_id": TAR,
        "source_bundle_id": "bundle_" + motion_id,
        "source_bundle_sha256": "a" * 64,
        "start_seconds": 0.5,
        "end_seconds": 3.5,
        "root_node_world_pos": {"x": 1, "y": 0, "z": 2},
        "root_node_world_rot": {"x": 0, "y": 0, "z": 0, "w": 1},
        "at_zero_time": copy.deepcopy(pose),
        "at_lower_trim_time": copy.deepcopy(pose),
        "at_upper_trim_time": copy.deepcopy(pose),
    }


async def test_stitch_uses_native_timing_preserves_sources_and_replays_locally(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    prefix, suffix = clip(), clip("motion2")
    result = await ops.stitch("join1", prefix, suffix)
    assert result["motion_id"] == "stitched1" and result["source_motion_ids"] == ["motion1", "motion2"]
    assert result["verification_status"] == "verified_metadata" and len(result["sources"]) == 2
    assert result["billing"]["model"] == "stitch-loop-2.0" and result["billing"]["actual_cost_usd"] is None
    assert result["credits_used"] is None and result["review_status"] == "unreviewed"
    assert result["pose_samples_source"] == "host_supplied_not_independently_verified"
    params = api.calls[0][1]
    assert params["prefix"]["motion_lower_trim_fraction"] == 0.125
    assert params["suffix"]["motion_upper_trim_fraction"] == 0.875
    assert params["prefix"]["motion_duration"] == 4 and not params["prefix"]["stitch_loop"]
    assert params["suffix"]["stitch_duration"] == 2 and params["suffix"]["prompt"] == ""

    async def unavailable(motion_id):
        raise RuntimeError("Metadata unavailable")

    api.motion = unavailable
    suffix["root_node_world_pos"]["x"] = 1.0
    suffix["source_bundle_sha256"] = "A" * 64
    replay = await Operations(api, tmp_path).stitch("join1", prefix, suffix, stitch_duration=2)
    assert replay["replayed"] and replay["verification_status"] == "not_rechecked"
    assert len(api.calls) == 1
    changed = copy.deepcopy(suffix)
    changed["at_upper_trim_time"]["pelvis_world_pos"]["z"] += 0.1
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("join1", prefix, changed)
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("join1", suffix, prefix)
    assert ops.recover_request("join1")["result"]["source_motion_ids"] == ["motion1", "motion2"]


@pytest.mark.parametrize(
    "failure", ["returned_prefix", "returned_suffix", "suffix_changed", "reused_bundle", "metadata"]
)
async def test_stitch_preservation_failure_keeps_completed_id(tmp_path, failure):
    api = FakeAPI()
    original = api.stitch

    async def stitch(*args):
        result = await original(*args)
        if failure == "returned_prefix":
            result["motion_id"] = "motion1"
        elif failure == "returned_suffix":
            result["motion_id"] = "motion2"
        elif failure == "suffix_changed":
            api.motions["motion2"]["bundle_sha256"] = "b" * 64
        elif failure == "reused_bundle":
            api.motions["stitched1"]["bundle_id"] = "bundle_motion2"
        else:
            api.fail_verification = True
        return result

    api.stitch = stitch
    ops = Operations(api, tmp_path)
    result = await ops.stitch("join1", clip(), clip("motion2"))
    assert result["verification_status"] == ("unverified" if failure == "metadata" else "failed")
    recovered = ops.recover_request("join1")
    assert recovered["state"] == "complete" and recovered["result"]["motion_id"] == result["motion_id"]
    assert (await ops.stitch("join1", clip(), clip("motion2")))["replayed"]
    assert len(api.calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("sampled_character_id", "other"),
        ("source_bundle_id", "old_bundle"),
        ("source_bundle_sha256", "b" * 64),
        ("end_seconds", 4),
        ("start_seconds", True),
        ("start_seconds", "0.5"),
        ("end_seconds", 0.5),
        ("end_seconds", 0.501),
        ("root_node_world_pos", {"x": 1, "y": 2, "z": float("nan")}),
        ("root_node_world_rot", {"x": 0, "y": 0, "z": 0, "w": 0}),
        ("at_zero_time", {}),
        ("extra", "unsupported"),
    ],
)
async def test_invalid_stitch_is_rejected_before_write(tmp_path, field, value):
    api = FakeAPI()
    bad = clip("motion2")
    bad[field] = value
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError):
        await ops.stitch("bad1", clip(), bad)
    assert not api.calls and ops.recover_request("bad1")["state"] == "not_found"


@pytest.mark.parametrize("outcome", ["rejected", "unknown", "cancelled"])
async def test_stitch_retries_only_confirmed_rejection(tmp_path, outcome):
    api = FakeAPI()
    original = api.stitch
    writes = []

    async def failure(*args):
        writes.append(args)
        if outcome == "cancelled":
            raise asyncio.CancelledError()
        raise APIError("Synthetic failure", outcome=outcome)

    api.stitch = failure
    ops = Operations(api, tmp_path)
    with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else RuntimeError):
        await ops.stitch("join1", clip(), clip("motion2"))
    status = ops.recover_request("join1")
    assert status["state"] == ("rejected" if outcome == "rejected" else "unknown")
    api.stitch = original
    resumed = Operations(api, tmp_path)
    if outcome == "rejected":
        assert (await resumed.stitch("join1", clip(), clip("motion2")))["motion_id"] == "stitched1"
    else:
        with pytest.raises(ValueError, match="pending or unresolved"):
            await resumed.stitch("join1", clip(), clip("motion2"))
        assert not api.calls
    assert len(writes) == 1


async def test_pending_stitch_cannot_be_submitted_concurrently(tmp_path):
    api = FakeAPI()
    entered, release = asyncio.Event(), asyncio.Event()
    original = api.stitch

    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    api.stitch = delayed
    first = asyncio.create_task(Operations(api, tmp_path).stitch("join1", clip(), clip("motion2")))
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="pending or unresolved"):
            await Operations(api, tmp_path).stitch("join1", clip(), clip("motion2"))
    finally:
        release.set()
        await first
    assert len(api.calls) == 1


async def test_real_client_stitch_serialization_timeout_and_rejection():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json={"data": {"create_enhanced_stitched_motion": {"motion": {"id": "joined1"}}}}
            )
        return httpx.Response(
            200,
            json={
                "data": None,
                "errors": [
                    {
                        "type": "InsufficientBalance",
                        "path": ["create_enhanced_stitched_motion"],
                        "message": "Private details",
                    }
                ],
            },
        )

    api = UthanaAPI("synthetic", transport=httpx.MockTransport(handler))
    source = FakeAPI().motions["motion1"]
    params = api_clip(StitchClip.model_validate(clip()).model_dump(), source, TAR, 1.5, "Turn smoothly")
    result = await api.stitch(TAR, params, params)
    assert result == {"motion_id": "joined1", "character_id": TAR}
    payload = json.loads(calls[0].content)
    assert payload["query"] == q.CREATE_ENHANCED_STITCHED_MOTION
    assert payload["variables"]["stitch_input"] == {"character_id": TAR, "prefix": params, "suffix": params}
    assert calls[0].extensions["timeout"]["read"] == 360 and calls[0].extensions["timeout"]["connect"] == 15
    with pytest.raises(APIError) as caught:
        await api.stitch(TAR, params, params)
    assert caught.value.outcome == "rejected" and "Private details" not in str(caught.value)
    await api.close()


async def test_real_stdio_stitch_recovery_and_strict_pose_inputs(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = {t.name: t for t in (await client.list_tools()).tools}
            tool = tools["create_stitched_motion"]
            assert not tool.annotations.readOnlyHint and not tool.annotations.idempotentHint
            assert {"prefix", "suffix"} <= set(tool.inputSchema["required"])
            bad = clip()
            bad["at_lower_trim_time"]["pelvis_world_pos"]["x"] = True
            invalid = await client.call_tool(
                "create_stitched_motion", {"request_id": "invalid", "prefix": bad, "suffix": clip("motion2")}
            )
            assert invalid.isError
            args = {"request_id": "joined", "prefix": clip(), "suffix": clip("motion2")}
            result = await client.call_tool("create_stitched_motion", args)
            assert not result.isError
            assert result.structuredContent["source_motion_ids"] == ["motion1", "motion2"]
            assert result.structuredContent["verification_status"] == "verified_metadata"
            replay = await client.call_tool("create_stitched_motion", {**args, "stitch_duration": 2.0})
            assert replay.structuredContent["replayed"]
            recovered = await client.call_tool("get_request_status", {"request_id": "joined"})
            assert recovered.structuredContent["result"]["motion_id"] == "stitched1"
