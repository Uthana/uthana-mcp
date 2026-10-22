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


def test_rerig_billing_policy():
    # Converting an already-rigged character is priced as auto-rig.
    rerig = receipt_billing("upload_character", {"auto_rig": False, "rerig_target": "r15"})
    assert rerig["model"] == "autorig" and rerig["cost_status"] == "unmeasured"
    # Choosing a target during initial auto-rig stays a single auto-rig charge.
    both = receipt_billing("upload_character", {"auto_rig": True, "rerig_target": "ue5"})
    assert both["model"] == "autorig" and both["cost_status"] == "unmeasured"
    # A plain rigged upload remains free.
    plain = receipt_billing("upload_character", {"auto_rig": False})
    assert plain["cost_status"] == "free_by_policy" and plain["model"] is None


async def test_character_upload_rejects_files_over_30_mib(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected = inputs / "big.glb"
    selected.write_bytes(b"\0" * (30 * 1024 * 1024 + 1))
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    with pytest.raises(ValueError, match="30 MiB"):
        await ops.upload_character("upload-too-big", str(selected), "Rig")
    assert not any(name == "upload_character" for name, _ in api.calls)


async def test_image_character_include_fingers_choice(tmp_path):
    from PIL import Image

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected = inputs / "ref.png"
    Image.new("RGB", (64, 64)).save(selected)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    await ops.create_character_from_image("image-no-fingers", str(selected), "Snapshot", include_fingers=False)
    call = next(args for name, args in api.calls if name == "finalize_image")
    assert call["include_fingers"] is False

    # A pre-expansion receipt replays with explicit default fingers and rejects a change.
    await ops.create_character_from_image("image-default", str(selected), "Snapshot")
    replay = await ops.create_character_from_image("image-default", str(selected), "Snapshot", include_fingers=True)
    assert replay["replayed"]
    with pytest.raises(ValueError):
        await ops.create_character_from_image("image-default", str(selected), "Snapshot", include_fingers=False)


async def test_schema_documents_every_rigging_option():
    from uthana_mcp.server import create_server

    server = create_server()
    tools = {tool.name: tool for tool in await server.list_tools()}
    properties = tools["upload_character"].inputSchema["properties"]
    for field in ("front_facing", "include_fingers", "rerig_target"):
        assert properties[field].get("description"), field
    rerig = json.dumps(properties["rerig_target"])
    assert "r15" in rerig and "ue5" in rerig
    image = tools["create_character_from_image"].inputSchema["properties"]
    assert image["include_fingers"].get("description")
    assert image["include_fingers"].get("default") is True
