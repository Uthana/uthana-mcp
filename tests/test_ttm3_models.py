import json

import httpx
import pytest
from fakes import FakeAPI
from mcp.server.fastmcp.exceptions import ToolError

from uthana_mcp.api import UthanaAPI
from uthana_mcp.billing import estimate_cost
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server
from uthana_mcp.validation import TAR, TTM3_MODELS


@pytest.mark.parametrize("model", TTM3_MODELS)
@pytest.mark.parametrize("is_fast", [False, True])
async def test_sdk_forwards_models_duration_and_fast_independently(model, is_fast):
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        result = await api.generate("Wave", 6, TAR, model=model, fast=is_fast)
    finally:
        await api.close()
    assert seen[0]["variables"]["model"] == model
    assert seen[0]["variables"]["fast"] is is_fast
    assert seen[0]["variables"]["length"] == 6
    assert "variant" not in seen[0]["variables"]
    assert result["model"] == model


@pytest.mark.parametrize("model", TTM3_MODELS)
@pytest.mark.parametrize("duration", [None, 6])
async def test_tool_defaults_receipts_and_replays_follow_model(tmp_path, model, duration):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    server = create_server(ops)
    arguments = {"request_id": "selected", "prompt": "Wave", "model": model, "fast": True}
    if duration is not None:
        arguments["duration_seconds"] = duration
    await server.call_tool("generate_motion", arguments)
    result = ops.recover_request("selected")["result"]
    default_duration = 4 if model == "text-to-motion-3.0" else 5
    expected_duration = default_duration if duration is None else duration
    assert api.calls[0][1]["duration_seconds"] == expected_duration
    assert api.calls[0][1]["fast"] is True
    assert api.calls[0][1].get("model", "text-to-motion-3.0") == model
    assert result["billing"]["model"] == model
    await server.call_tool("generate_motion", arguments)
    assert len(api.calls) == 1
    changed = {
        **arguments,
        "model": "text-to-motion-3.0-mini" if model != "text-to-motion-3.0-mini" else "text-to-motion-3.0-lite",
    }
    with pytest.raises(ToolError, match="different arguments"):
        await server.call_tool("generate_motion", changed)
    with pytest.raises(ToolError, match="different arguments"):
        await server.call_tool("generate_motion", {**arguments, "fast": False})
    assert len(api.calls) == 1


@pytest.mark.parametrize("model", ["text-to-motion-3.0-lite", "text-to-motion-3.0-mini"])
@pytest.mark.parametrize("duration", [4, 5.5, 11, True])
async def test_invalid_variant_duration_never_submits_or_creates_receipt(tmp_path, model, duration):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    server = create_server(ops)
    with pytest.raises(ToolError):
        await server.call_tool(
            "generate_motion", {"request_id": "invalid", "prompt": "Wave", "model": model, "duration_seconds": duration}
        )
    assert api.calls == []
    assert ops.recover_request("invalid")["state"] == "not_found"


@pytest.mark.parametrize("fields", [{"model": "text-to-motion-3.0-light"}, {"fast": "true"}, {"fast": 1}])
async def test_invalid_tool_options_never_submit(tmp_path, fields):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ToolError):
        await create_server(ops).call_tool("generate_motion", {"request_id": "invalid", "prompt": "Wave", **fields})
    assert api.calls == []


async def test_regular_defaults_replay_pre_model_receipt(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    previous_args = {"prompt": "Wave", "duration_seconds": 4, "character_id": TAR}
    await ops.store.mutation("old", "generate", previous_args, lambda: api.generate(**previous_args))
    assert (await ops.generate("old", "Wave"))["replayed"]
    assert (await ops.generate("old", "Wave", 4, model="text-to-motion-3.0", fast=False))["replayed"]
    assert len(api.calls) == 1


@pytest.mark.parametrize("model", TTM3_MODELS)
async def test_tool_schema_exposes_model_options_without_new_tools(tmp_path, model):
    tools = {tool.name: tool for tool in await create_server(Operations(FakeAPI(), tmp_path)).list_tools()}
    schema = tools["generate_motion"].inputSchema["properties"]
    assert model in schema["model"]["enum"]
    assert schema["fast"]["default"] is False
    assert model in tools["estimate_model_cost"].inputSchema["properties"]["model"]["enum"]


@pytest.mark.parametrize("model", ["text-to-motion-3.0-lite", "text-to-motion-3.0-mini"])
def test_new_model_cost_uses_returned_rate(model):
    rates = [{"model_key": model, "billing_unit": "second", "unit_price": "0.123"}]
    assert estimate_cost(rates, model, 2)["estimated_cost_usd"] == "0.2460"


async def test_direct_generation_checks_model_and_fast_before_submission(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    for fields in ({"model": "unknown"}, {"fast": 1}):
        with pytest.raises(ValueError):
            await ops.generate("invalid", "Wave", **fields)
    assert api.calls == []
