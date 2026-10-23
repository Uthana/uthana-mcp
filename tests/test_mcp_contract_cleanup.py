"""Regression coverage for backend input, upload timing, and compatibility contracts."""

import json

import httpx
import pytest
from fakes import FakeAPI
from mcp.server.fastmcp.exceptions import ToolError

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server
from uthana_mcp.validation import TAR


@pytest.mark.parametrize("duration", [4, 4.0, 5, 6.0, 10, 10.0])
async def test_v3_accepts_whole_seconds_and_ordinary_prompt_boundary(tmp_path, duration):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    result = await ops.generate("request", "x" * 1000, duration)
    assert result["job_id"] == "job1"
    assert api.calls == [("generate", {"prompt": "x" * 1000, "duration_seconds": duration, "character_id": TAR})]


@pytest.mark.parametrize(
    "prompt,duration,error",
    [
        ("x" * 1001, 4, "1000 characters"),
        ("x" * 2500, 4, "1000 characters"),
        ("x" * 8000, 4, "1000 characters"),
        ("Run, jump, and land", 4.1, "whole number"),
        ("Run, jump, and land", 5.5, "whole number"),
        ("Run, jump, and land", 9.9, "whole number"),
        ("Run, jump, and land", 4.0000000001, "whole number"),
    ],
)
async def test_v3_rejects_unsupported_inputs_before_receipt_claim_or_submission(tmp_path, prompt, duration, error):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError, match=error):
        await ops.generate("request", prompt, duration)
    assert api.calls == []
    assert ops.store.get_request("request")["state"] == "not_found"


@pytest.mark.parametrize("prompt,duration", [("x" * 1001, 4), ("Run and jump", 5.5), ("x" * 2500, 6.5)])
async def test_historical_completed_v3_recovers_after_input_contract_tightens(tmp_path, prompt, duration):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    historical_args = {"prompt": prompt, "duration_seconds": duration, "character_id": TAR}

    async def prior_success():
        return {"job_id": "historical_job", "character_id": TAR}

    original = await ops.store.mutation("legacy", "generate", historical_args, prior_success)
    restarted = Operations(api, tmp_path)
    recovered = restarted.recover_request("legacy")
    assert recovered["result"]["job_id"] == original["job_id"]
    assert recovered["result"]["replayed"]
    with pytest.raises(ValueError, match="1000 characters|whole number"):
        await restarted.generate("legacy", prompt, duration)
    assert restarted.recover_request("legacy")["result"] == recovered["result"]
    assert api.calls == []


async def test_old_rejected_v3_cannot_resubmit_now_unsupported_inputs(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    args = {"prompt": "x" * 1001, "duration_seconds": 4, "character_id": TAR}

    async def prior_rejection():
        raise APIError("Prior authentication rejection", outcome="rejected")

    with pytest.raises(APIError):
        await ops.store.mutation("legacy_rejected", "generate", args, prior_rejection)
    with pytest.raises(ValueError, match="1000 characters"):
        await ops.generate("legacy_rejected", args["prompt"], 4)
    assert ops.store.get_request("legacy_rejected")["state"] == "rejected"
    assert api.calls == []


async def test_discovered_v3_schema_and_local_execution_match_backend_contract(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    server = create_server(ops)
    tools = {tool.name: tool for tool in await server.list_tools()}
    schema = tools["generate_motion"].inputSchema["properties"]
    assert schema["prompt"]["maxLength"] == 1000
    assert schema["duration_seconds"]["minimum"] == 4
    assert schema["duration_seconds"]["maximum"] == 10
    assert schema["duration_seconds"]["multipleOf"] == 1
    for changes in ({"prompt": "x" * 1001}, {"duration_seconds": 5.5}, {"duration_seconds": True}):
        with pytest.raises(ToolError):
            await server.call_tool("generate_motion", {"request_id": "bad", "prompt": "Jump", **changes})
    assert api.calls == []
    assert ops.store.get_request("bad")["state"] == "not_found"
    await server.call_tool("generate_motion", {"request_id": "good", "prompt": "Jump", "duration_seconds": 4.0})
    assert len(api.calls) == 1
    assert "untrusted backend data" in tools["upload_character"].description


async def test_character_upload_alone_uses_360_second_timeout_and_requests_warning():
    seen = []
    warning = "Non-XYZ FBX pre-rotations may make downloaded motion incorrect."

    def respond(request):
        content = request.content.decode()
        seen.append(request.extensions["timeout"])
        if "create_character(" in content:
            assert "auto_rig_confidence" in content and "message" in content
            return httpx.Response(
                200,
                json={
                    "data": {
                        "create_character": {
                            "character": {"id": "character1", "name": "Rig"},
                            "auto_rig_confidence": 0.8,
                            "message": warning,
                            "private_debug": "never return this field",
                        }
                    }
                },
            )
        if "create_video_to_motion(" in content:
            return httpx.Response(200, json={"data": {"create_video_to_motion": {"job": {"id": "job1"}}}})
        assert "characters {" in json.loads(content)["query"]
        return httpx.Response(200, json={"data": {"characters": []}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        await api.characters()
        result = await api.upload_character("rig.fbx", b"offline fixture", "Rig", False)
        await api.video("walk.mp4", b"offline fixture", "Walk", "video-to-motion-2.0")
        await api.characters()
        assert [timeout["read"] for timeout in seen] == [180, 360, 180, 180]
        assert all(timeout["connect"] == 15 for timeout in seen)
        assert result == {
            "character_id": "character1",
            "auto_rig_confidence": 0.8,
            "compatibility_warning": warning,
            "compatibility_warning_truncated": False,
        }
    finally:
        await api.close()


@pytest.mark.parametrize(
    "message,expected,truncated",
    [
        (None, None, False),
        ("", None, False),
        ("  \n  ", None, False),
        ({"unexpected": "object"}, None, False),
        ("  Inspect FBX carefully.  ", "Inspect FBX carefully.", False),
        ("x" * 2001, "x" * 2000, True),
    ],
)
async def test_upload_warning_is_optional_bounded_success_data(message, expected, truncated):
    def respond(request):
        return httpx.Response(
            200,
            json={"data": {"create_character": {"character": {"id": "character1"}, "message": message}}},
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        result = await api.upload_character("rig.glb", b"offline fixture", "Rig", False)
        assert result["character_id"] == "character1"
        assert result["compatibility_warning"] == expected
        assert result["compatibility_warning_truncated"] is truncated
    finally:
        await api.close()


async def test_upload_graphql_errors_do_not_leak_warning_or_private_error_data():
    def respond(request):
        return httpx.Response(
            200,
            json={
                "data": {"create_character": {"character": {"id": "character1"}, "message": "private payload"}},
                "errors": [{"message": "private credential content", "path": ["create_character"]}],
            },
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as captured:
            await api.upload_character("rig.fbx", b"offline fixture", "Rig", False)
        assert "private" not in str(captured.value)
        assert captured.value.outcome == "unknown"
    finally:
        await api.close()


async def test_completed_upload_retains_warning_without_network_after_restart(tmp_path):
    calls = []
    warning = "FBX export may be incorrect for this rig; inspect its rotations."

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"data": {"create_character": {"character": {"id": "character1"}, "message": warning}}},
        )

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected = inputs / "rig.fbx"
    selected.write_bytes(b"offline fixture")
    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path / "state", inputs)
        original = await ops.upload_character("upload", str(selected), "Rig")
        restarted = Operations(api, tmp_path / "state", inputs)
        replay = await restarted.upload_character("upload", str(selected), "Rig")
        recovered = restarted.recover_request("upload")
        assert original["compatibility_warning"] == warning
        assert replay["compatibility_warning"] == warning and replay["replayed"]
        assert recovered["result"]["compatibility_warning"] == warning
        assert len(calls) == 1
    finally:
        await api.close()


async def test_legacy_completed_upload_without_warning_still_replays(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected = inputs / "rig.fbx"
    selected.write_bytes(b"offline fixture")
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", inputs)
    filename, _, digest = ops.read_input(str(selected), {".fbx"})
    historical_args = {"content_sha256": digest, "filename": filename, "name": "Rig", "auto_rig": False}

    async def prior_success():
        return {"character_id": "historical_character", "auto_rig_confidence": 1.0}

    await ops.store.mutation("legacy_upload", "upload_character", historical_args, prior_success)
    restarted = Operations(api, tmp_path / "state", inputs)
    replay = await restarted.upload_character("legacy_upload", str(selected), "Rig")
    assert replay["character_id"] == "historical_character" and replay["replayed"]
    assert "compatibility_warning" not in replay
    assert api.calls == []
