"""Image-stage recovery, preview-loop contracts, and actual MCP invocation."""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image
from uthana.graphql import q

import uthana_mcp
from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.store import Store


def image_input(tmp_path):
    directory = tmp_path / "inputs"
    directory.mkdir(exist_ok=True)
    path = directory / "reference.png"
    Image.new("RGB", (8, 8), "blue").save(path)
    return path


async def test_image_success_replay_and_removed_input_recovery(tmp_path):
    path = image_input(tmp_path)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", path.parent)
    result = await ops.create_character_from_image("image1", str(path), "Hero")
    assert result["character_id"] == "imagechar1" and result["stage"] == "character_created"
    assert result["billing"]["model"] == "character-gen-1.0"
    assert result["billing"]["actual_cost_usd"] is None and result["credits_used"] is None
    assert (await ops.create_character_from_image("image1", str(path), "Hero"))["replayed"]
    assert [c[0] for c in api.calls] == ["prepare_image", "finalize_image"]
    with pytest.raises(ValueError, match="different arguments"):
        await ops.create_character_from_image("image1", str(path), "Changed name")
    path.unlink()
    recovered = Operations(api, tmp_path / "state").recover_request("image1")
    assert recovered["result"]["character_id"] == "imagechar1"
    assert recovered["progress"]["stage"] == "image_prepared"


async def test_finalization_rejection_reuses_prepared_image_after_restart(tmp_path):
    path = image_input(tmp_path)
    api = FakeAPI()
    original = api.finalize_character_image

    async def reject(prepared, name, include_fingers=True):
        raise APIError("Insufficient balance", outcome="rejected", category="balance")

    api.finalize_character_image = reject
    ops = Operations(api, tmp_path / "state", path.parent)
    with pytest.raises(APIError):
        await ops.create_character_from_image("image1", str(path), "Hero")
    status = ops.recover_request("image1")
    assert status["state"] == "rejected" and status["progress"]["character_id"] == "imagechar1"
    api.finalize_character_image = original
    restarted = Operations(api, tmp_path / "state", path.parent)
    result = await restarted.create_character_from_image("image1", str(path), "Hero")
    assert result["character_id"] == "imagechar1"
    assert [c[0] for c in api.calls] == ["prepare_image", "finalize_image"]


@pytest.mark.parametrize("cancelled", [False, True])
async def test_unknown_finalization_retains_progress_and_blocks_retry(tmp_path, cancelled):
    path = image_input(tmp_path)
    api = FakeAPI()

    async def uncertain(prepared, name, include_fingers=True):
        if cancelled:
            raise asyncio.CancelledError()
        raise APIError("Response lost")

    api.finalize_character_image = uncertain
    ops = Operations(api, tmp_path / "state", path.parent)
    with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
        await ops.create_character_from_image("image1", str(path), "Hero")
    status = ops.recover_request("image1")
    assert status["state"] == "unknown" and status["progress"]["character_id"] == "imagechar1"
    with pytest.raises(ValueError, match="pending or unresolved"):
        await Operations(api, tmp_path / "state", path.parent).create_character_from_image("image1", str(path), "Hero")
    assert len(api.calls) == 1


async def test_unknown_preparation_never_attempts_character_build(tmp_path):
    path = image_input(tmp_path)
    api = FakeAPI()

    async def uncertain(filename, content):
        raise APIError("Response lost")

    api.prepare_character_image = uncertain
    ops = Operations(api, tmp_path / "state", path.parent)
    with pytest.raises(RuntimeError):
        await ops.create_character_from_image("image1", str(path), "Hero")
    assert ops.recover_request("image1")["state"] == "unknown"
    assert not api.calls


@pytest.mark.parametrize("kind", ["corrupt", "animated", "wrong_format", "oversized"])
async def test_image_validation_happens_before_upstream_writes(tmp_path, kind):
    path = image_input(tmp_path)
    if kind == "corrupt":
        path.write_bytes(b"not-an-image")
    elif kind == "animated":
        frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
        frames[0].save(path, format="PNG", save_all=True, append_images=frames[1:], duration=100)
    elif kind == "wrong_format":
        Image.new("RGB", (8, 8)).save(path, format="JPEG")
    else:
        with path.open("wb") as file:
            file.truncate(16 * 1024 * 1024 + 1)
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state", path.parent)
    with pytest.raises(ValueError):
        await ops.create_character_from_image("bad", str(path), "Hero")
    assert not api.calls and ops.recover_request("bad")["state"] == "not_found"


async def test_loop_preserves_source_and_recovers_without_metadata(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    result = await ops.loop("loop1", "motion1")
    assert result["source_motion_id"] == "motion1" and result["motion_id"] == "looped1"
    assert result["verification_status"] == "verified_metadata"
    assert result["billing"]["model"] == "stitch-loop-2.0" and result["credits_used"] is None
    assert result["loop_mode"] == "closed" and result["review_status"] == "unreviewed"

    async def unavailable(motion_id):
        raise RuntimeError("Metadata unavailable")

    api.motion = unavailable
    replay = await Operations(api, tmp_path).loop("loop1", "motion1", trim_start_pct=0, trim_end_pct=1, zone_duration=2)
    assert replay["replayed"] and replay["verification_status"] == "not_rechecked"
    assert len(api.calls) == 1
    with pytest.raises(ValueError, match="different arguments"):
        await ops.loop("loop1", "motion1", loop_mode="open")


async def test_loop_metadata_failure_does_not_lose_saved_id(tmp_path):
    api = FakeAPI()
    api.fail_verification = True
    ops = Operations(api, tmp_path)
    result = await ops.loop(
        "loop1", "motion1", loop_mode="open", zone_mode="extend", zone_end_position={"x": 1, "y": 2}
    )
    assert result["verification_status"] == "unverified"
    assert ops.recover_request("loop1")["result"]["motion_id"] == "looped1"
    assert api.calls[0][1]["zone_end_position"] == {"x": 1, "y": 2}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trim_start_pct": True},
        {"trim_end_pct": 0},
        {"zone_duration": float("nan")},
        {"zone_duration": 4},
        {"loop_mode": "progressive"},
        {"zone_mode": "invalid"},
        {"zone_end_position": {"x": 1, "y": 0}},
        {"loop_mode": "open", "zone_end_position": {"x": 1, "y": True}},
        {"loop_mode": "open", "zone_end_position": {"x": 1, "y": 0, "extra": 2}},
    ],
)
async def test_loop_rejects_invalid_inputs_before_any_api_calls(tmp_path, kwargs):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError):
        await ops.loop("bad", "motion1", **kwargs)
    assert not api.calls and ops.recover_request("bad")["state"] == "not_found"


def test_old_receipt_schema_migrates_without_losing_rows(tmp_path):
    directory = tmp_path / "scope"
    directory.mkdir()
    with sqlite3.connect(directory / "requests.sqlite") as db:
        db.execute(
            "CREATE TABLE requests(id TEXT PRIMARY KEY, operation TEXT, fingerprint TEXT, state TEXT, result TEXT, updated REAL)"
        )
        db.execute("INSERT INTO requests VALUES ('old','generate','hash','complete','{\"job_id\":\"job1\"}',0)")
    status = Store(tmp_path, "scope").get_request("old")
    assert status["result"]["job_id"] == "job1" and status["state"] == "complete"


async def test_real_client_image_stages_and_loop_transport():
    calls = []

    def handler(request):
        calls.append(request)
        if "multipart/" in request.headers.get("content-type", ""):
            assert b"image-snapshot" in request.content
            assert request.extensions["timeout"]["read"] == 360
            return httpx.Response(
                200,
                json={
                    "data": {
                        "create_image_from_image": {
                            "character_id": "imagechar1",
                            "image": {"key": "imagechar1-front.png"},
                        }
                    }
                },
            )
        payload = json.loads(request.content)
        if payload["query"] == q.CREATE_CHARACTER_FROM_IMAGE:
            assert payload["variables"]["include_fingers"] is True
            assert request.extensions["timeout"]["read"] == 660
            return httpx.Response(
                200,
                json={
                    "data": {
                        "create_character_from_image": {
                            "character": {"id": "imagechar1"},
                            "auto_rig_confidence": 0.9,
                        }
                    }
                },
            )
        assert payload["query"] == q.CREATE_LOOPED_MOTION
        assert payload["variables"]["loop_mode"] == "open"
        assert payload["variables"]["zone_end_position"] == {"x": 1, "y": 2}
        assert request.extensions["timeout"]["read"] == 360
        return httpx.Response(200, json={"data": {"create_looped_motion": {"motion": {"id": "loop1"}}}})

    api = UthanaAPI("synthetic", transport=httpx.MockTransport(handler))
    prepared = await api.prepare_character_image("ref.png", b"image-snapshot")
    assert (await api.finalize_character_image(prepared, "Hero"))["character_id"] == "imagechar1"
    assert (await api.loop("motion1", "char1", 0, 1, 2, "open", "extend", {"x": 1, "y": 2}))["motion_id"] == "loop1"
    assert len(calls) == 3
    await api.close()


async def test_new_tools_through_real_stdio(tmp_path):
    path = image_input(tmp_path)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            catalog = {t.name: t for t in (await client.list_tools()).tools}
            for name in ("create_character_from_image", "create_looped_motion"):
                assert not catalog[name].annotations.readOnlyHint
            image = await client.call_tool(
                "create_character_from_image", {"request_id": "image1", "file_path": str(path), "name": "Hero"}
            )
            assert not image.isError and image.structuredContent["character_id"] == "imagechar1"
            loop = await client.call_tool(
                "create_looped_motion",
                {
                    "request_id": "loop1",
                    "motion_id": "motion1",
                    "loop_mode": "open",
                    "zone_end_position": {"x": 1, "y": 0},
                },
            )
            assert not loop.isError and loop.structuredContent["motion_id"] == "looped1"
            bad = await client.call_tool(
                "create_looped_motion",
                {
                    "request_id": "bad",
                    "motion_id": "motion1",
                    "loop_mode": "open",
                    "zone_end_position": {"x": True, "y": 0},
                },
            )
            assert bad.isError
