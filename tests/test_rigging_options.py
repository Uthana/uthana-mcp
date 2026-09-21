"""Coverage for exposed rigging options: front_facing, include_fingers, rerig_target."""

import json

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.billing import receipt_billing
from uthana_mcp.operations import Operations


def make_inputs(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected = inputs / "rig.fbx"
    selected.write_bytes(b"offline fixture")
    return inputs, selected


async def test_rigging_options_reach_the_api(tmp_path):
    inputs, selected = make_inputs(tmp_path)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    await ops.upload_character(
        "upload-options",
        str(selected),
        "Rig",
        auto_rig=True,
        front_facing=False,
        include_fingers=False,
        rerig_target="r15",
    )
    call = next(args for name, args in api.calls if name == "upload_character")
    assert call["auto_rig"] is True
    assert call["front_facing"] is False
    assert call["include_fingers"] is False
    assert call["rerig_target"] == "r15"


async def test_default_options_reach_the_api_unchanged(tmp_path):
    inputs, selected = make_inputs(tmp_path)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    await ops.upload_character("upload-defaults", str(selected), "Rig")
    call = next(args for name, args in api.calls if name == "upload_character")
    assert call["front_facing"] is True
    assert call["include_fingers"] is True
    assert call["rerig_target"] is None


async def test_invalid_rerig_target_rejected_before_upload(tmp_path):
    inputs, selected = make_inputs(tmp_path)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    with pytest.raises(ValueError, match="rerig_target"):
        await ops.upload_character("upload-bad-target", str(selected), "Rig", rerig_target="r6")
    assert not any(name == "upload_character" for name, _ in api.calls)


async def test_pre_expansion_receipt_replays_with_explicit_defaults(tmp_path):
    """A receipt recorded before these options existed must replay when the
    caller now passes the explicit defaults, and must reject changed options."""
    inputs, selected = make_inputs(tmp_path)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    original = await ops.upload_character("upload-legacy", str(selected), "Rig")

    restarted = Operations(api, tmp_path / "state", inputs)
    replay = await restarted.upload_character(
        "upload-legacy", str(selected), "Rig", auto_rig=False, front_facing=True, include_fingers=True
    )
    assert replay["replayed"] and replay["character_id"] == original["character_id"]
    assert sum(name == "upload_character" for name, _ in api.calls) == 1

    with pytest.raises(ValueError):
        await restarted.upload_character("upload-legacy", str(selected), "Rig", rerig_target="ue5")


async def test_rerig_target_forwarded_in_mutation(tmp_path):
    inputs, selected = make_inputs(tmp_path)
    bodies = []

    def respond(request):
        # The upload is a multipart form; keep the raw bytes for inspection.
        bodies.append(request.content.decode("latin-1"))
        return httpx.Response(
            200,
            json={"data": {"create_character": {"character": {"id": "character9"}, "message": ""}}},
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path / "state", inputs)
        await ops.upload_character("upload-wire", str(selected), "Rig", rerig_target="ue5")
    finally:
        await api.close()
    payload = "".join(bodies)
    assert "ue5" in payload
    assert "include_fingers" in payload or "includeFingers" in payload


def test_rerig_upload_cost_is_not_asserted_free():
    rerig = receipt_billing("upload_character", {"auto_rig": False, "rerig_target": "r15"})
    assert rerig["cost_status"] == "unmeasured" and rerig["actual_cost_usd"] is None
    plain = receipt_billing("upload_character", {"auto_rig": False})
    assert plain["cost_status"] == "free_by_policy"


async def test_schema_documents_every_rigging_option():
    from uthana_mcp.server import create_server

    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}
    properties = tools["upload_character"].inputSchema["properties"]
    for field in ("front_facing", "include_fingers", "rerig_target"):
        assert properties[field].get("description"), field
    rerig = json.dumps(properties["rerig_target"])
    assert "r15" in rerig and "ue5" in rerig
