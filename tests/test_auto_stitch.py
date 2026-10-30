"""Shared contracts, real SDK wire requests, and stdio schema/recovery."""

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_stitch import options

import uthana_mcp
from uthana_mcp.api import UthanaAPI
from uthana_mcp.operations import Operations
from uthana_mcp.stitching import StitchInput

FIXTURES = json.loads((Path(__file__).parent / "fixtures/stitch_contract.json").read_text())


@pytest.mark.parametrize("case", FIXTURES["valid"], ids=lambda c: c["name"])
def test_shared_valid_contract(case):
    result = StitchInput.model_validate(case["input"]).model_dump(exclude_none=True)
    assert result == case["normalized"]
    assert (
        result["steps"][0]["transition"]["duration_seconds"]
        == case["normalized"]["steps"][0]["transition"]["duration_seconds"]
    )


@pytest.mark.parametrize("case", FIXTURES["invalid"], ids=lambda c: c["name"])
async def test_shared_invalid_contract_never_submits(tmp_path, case):
    api = FakeAPI()
    with pytest.raises(ValueError):
        await Operations(api, tmp_path).stitch("bad", case["input"])
    assert not api.calls


async def test_recovery_placement_identity_and_legacy_receipt(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    result = await ops.stitch("join1", options())
    assert result["motion"]["id"] == result["motion_id"] == "stitched1"
    assert result["verification_status"] == "verified_metadata"
    assert result["billing"]["model"] == "stitch-loop-2.0"
    replay = await Operations(api, tmp_path).stitch("join1", options())
    assert replay["replayed"] and len(api.calls) == 1
    changed = copy.deepcopy(options())
    changed["steps"][1]["placement"] = {}
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("join1", changed)
    # Historical fingerprints are recoverable, but cannot be resubmitted under the new contract.
    args = {"prefix": {"motion_id": "motion1"}, "suffix": {"motion_id": "motion2"}}

    async def historical():
        return {"motion_id": "old-result", "source_motion_ids": ["motion1", "motion2"]}

    await ops.store.mutation("historical", "stitch", args, historical)
    assert ops.recover_request("historical")["result"]["motion_id"] == "old-result"
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("historical", options())
    assert len(api.calls) == 1


async def test_real_client_serialization_and_no_retry():
    calls = []
    expected = StitchInput.model_validate(options()).model_dump(exclude_none=True)

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"data": {"stitch": {"motion": {"id": "stitched1"}, "resolved_steps": expected["steps"]}}}
        )

    api = UthanaAPI("test", transport=httpx.MockTransport(handler))
    result = await api.stitch(expected)
    assert result["motion_id"] == "stitched1"
    assert calls[0]["variables"] == {"input": expected}
    assert len(calls) == 1
    await api.close()


async def test_out_of_source_range_never_submits(tmp_path):
    api = FakeAPI()
    request = options()
    request["steps"][0]["range"] = {"end_frame": 999}
    with pytest.raises(ValueError, match="native"):
        await Operations(api, tmp_path).stitch("bad", request)
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
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert "stitch_motions" not in tools and "create_stitched_motion" not in tools
            assert set(tools["stitch"].inputSchema["required"]) == {"request_id", "character_id", "steps"}
            args = {"request_id": "stdio-join", **options()}
            result = await client.call_tool("stitch", args)
            assert not result.isError
            replay = await client.call_tool("stitch", args)
            assert replay.structuredContent["replayed"]


async def test_default_and_final_transition_replay_identity(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    await ops.stitch("same", options())
    for first in ({}, {"duration_seconds": 1}, {"duration_seconds": 1.0}):
        request = options()
        request["steps"][0]["transition"] = first
        request["steps"][1]["transition"] = {"duration_seconds": -999}
        original = copy.deepcopy(request)
        assert (await ops.stitch("same", request))["replayed"]
        assert request == original
    changed = options()
    changed["steps"][0]["transition"] = {"duration_seconds": 2}
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("same", changed)
    assert len(api.calls) == 1


async def test_old_typed_receipt_recovers_but_cannot_replay(tmp_path):
    ops = Operations(FakeAPI(), tmp_path)

    async def historical():
        return {"motion_id": "old", "source_motion_ids": ["motion1", "motion2"]}

    args = {"contract": "typed_steps", **StitchInput.model_validate(options()).model_dump(exclude_none=True)}
    await ops.store.mutation("old", "stitch", args, historical)
    assert ops.recover_request("old")["result"]["motion_id"] == "old"
    with pytest.raises(ValueError, match="different arguments"):
        await ops.stitch("old", options())
