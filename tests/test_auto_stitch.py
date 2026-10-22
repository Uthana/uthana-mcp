import json
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI, native
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import uthana_mcp
from uthana_mcp.api import UthanaAPI
from uthana_mcp.operations import Operations
from uthana_mcp.validation import TAR

OPTIONS = dict(character_id=TAR, prefix_motion_id="motion1", suffix_motion_id="motion2")


async def test_server_preparation_recovery_and_placement_identity(tmp_path):
    api = FakeAPI()

    async def stitch(options):
        api.calls.append(options)
        api.motions["stitched1"] = native("stitched1", 179, 20)
        return {"motion_id": "stitched1", "preparation": {"pose_samples_source": "server_sampled"}}

    api.stitch_auto = stitch
    result = await Operations(api, tmp_path).stitch_auto("auto1", OPTIONS)
    assert result["verification_status"] == "verified_metadata"
    assert result["pose_samples_source"] == "server_sampled"
    assert result["billing"]["model"] == "stitch-loop-2.0"
    recovered = await Operations(api, tmp_path).stitch_auto("auto1", OPTIONS)
    assert recovered["replayed"] and len(api.calls) == 1
    with pytest.raises(ValueError, match="different arguments"):
        await Operations(api, tmp_path).stitch_auto("auto1", {**OPTIONS, "placement": {"forward_m": 0.0}})
    assert Operations(api, tmp_path).recover_request("auto1")["state"] == "complete"


async def test_real_client_auto_serialization_and_no_retry():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "data": {
                    "create_enhanced_stitched_motion": {
                        "motion": {"id": "stitched1"},
                        "preparation": {"stitch_duration": 1.0},
                    }
                }
            },
        )

    api = UthanaAPI("test", transport=httpx.MockTransport(handler))
    result = await api.stitch_auto(OPTIONS)
    assert result["motion_id"] == "stitched1"
    assert calls[0]["variables"] == {"auto_input": OPTIONS}
    assert len(calls) == 1
    await api.close()


@pytest.mark.parametrize(
    "bad", [{"stitch_duration": True}, {"placement": {"forward_m": float("nan")}}, {"prefix_end_seconds": 999.0}]
)
async def test_invalid_input_never_submits(tmp_path, bad):
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).stitch_auto("bad", {**OPTIONS, **bad})
    assert not api.calls


async def test_actual_stdio_simple_tool_schema_and_recovery(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as client:
            await client.initialize()
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert set(tools["stitch_motions"].inputSchema["required"]) == {
                "request_id",
                "prefix_motion_id",
                "suffix_motion_id",
            }
            args = {"request_id": "stdio-auto", **OPTIONS, "placement": {"forward_m": 2.0, "facing_degrees": 90.0}}
            result = await client.call_tool("stitch_motions", args)
            assert not result.isError
            replay = await client.call_tool("stitch_motions", args)
            assert replay.structuredContent["replayed"]
