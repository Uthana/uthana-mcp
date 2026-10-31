import asyncio
import io
import json
from pathlib import Path

import pytest
from fakes import FakeAPI
from PIL import Image
from platform_support import is_private, symlink_or_skip

from uthana_mcp.operations import Operations
from uthana_mcp.store import Store


@pytest.fixture
def setup(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    api = FakeAPI()
    return api, Operations(api, tmp_path / "state", inputs), inputs


async def test_generate_restart_replay_and_changed_intent(setup, tmp_path):
    api, ops, _ = setup
    original = await ops.generate("req1", "Run and jump")
    restarted = Operations(api, tmp_path / "state")
    replay = await restarted.generate("req1", "Run and jump")
    assert replay["job_id"] == original["job_id"] and replay["replayed"]
    assert api.calls == [
        ("generate", {"prompt": "Run and jump", "duration_seconds": 4, "character_id": "cXi2eAP19XwQ"})
    ]
    with pytest.raises(ValueError, match="different arguments"):
        await restarted.generate("req1", "Wave")


async def test_concurrent_receipt_claims_one_submission(tmp_path):
    first, second = Store(tmp_path, "same"), Store(tmp_path, "same")
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def invoke():
        calls.append(True)
        entered.set()
        await release.wait()
        return {"job_id": "one"}

    pending = asyncio.create_task(first.mutation("req", "generate", {}, invoke))
    await entered.wait()
    with pytest.raises(ValueError, match="pending or unresolved"):
        await second.mutation("req", "generate", {}, invoke)
    release.set()
    await pending
    assert len(calls) == 1


async def test_unknown_outcome_is_not_resubmitted(setup):
    api, ops, _ = setup

    async def fail(**args):
        api.calls.append(("accepted-before-timeout", args))
        raise TimeoutError("Do not expose an upstream secret")

    api.generate = fail
    with pytest.raises(RuntimeError, match="unconfirmed"):
        await ops.generate("unknown", "jump")
    with pytest.raises(ValueError, match="pending or unresolved"):
        await ops.generate("unknown", "jump")
    assert len(api.calls) == 1
    assert ops.store.get_request("unknown")["state"] == "unknown"


async def test_state_is_not_shared_between_credentials(tmp_path):
    first, second = Store(tmp_path, "account1"), Store(tmp_path, "account2")

    async def invoke():
        return {"job_id": "private_job"}

    await first.mutation("req", "generate", {}, invoke)
    assert second.get_request("req")["state"] == "not_found"
    assert is_private(first.directory)
    assert is_private(first.path)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), True, 3, 11])
async def test_invalid_generation_never_submits(setup, duration):
    api, ops, _ = setup
    with pytest.raises(ValueError):
        await ops.generate("req", "jump", duration)
    assert not api.calls


async def test_trim_uses_native_duration_and_keeps_source(setup):
    api, ops, _ = setup
    # Source is eight seconds even though generation defaults to four.
    api.motions["motion1"].update(frame_count=240, duration_seconds=8)
    result = await ops.trim("trim1", "motion1", 1, 3, "Middle")
    assert api.calls[0][1]["start"] == 0.125
    assert api.calls[0][1]["end"] == 0.375
    assert result["native_frame_interval"] == [30, 90]
    assert result["saved"]["frame_count"] == 61
    assert result["saved"]["duration_seconds"] == 61 / 30
    assert result["frame_interval_end_inclusive"] is True
    assert result["saved"]["bundle_id"] != result["source"]["bundle_id"]
    assert result["verification_status"] == "verified_metadata"
    assert result["review_status"] == "unreviewed"
    assert api.motions["motion1"]["frame_count"] == 240
    await ops.trim("trim1", "motion1", 1, 3, "Middle")
    assert len(api.calls) == 1


@pytest.mark.parametrize("start,end", [(3, 1), (0, 5), (0, 0), (0, float("nan")), (0, 0.001)])
async def test_invalid_trim_never_submits(setup, start, end):
    api, ops, _ = setup
    with pytest.raises(ValueError):
        await ops.trim("req", "motion1", start, end, "Trim")
    assert not api.calls


async def test_trim_preserves_new_id_when_verification_fails(setup):
    api, ops, _ = setup
    api.fail_verification = True
    result = await ops.trim("trim1", "motion1", 1, 3, "Middle")
    assert result["verification_status"] == "unverified"
    assert ops.store.get_request("trim1")["result"]["motion_id"] == "trimmed1"
    api.fail_verification = False
    result = await ops.trim("trim1", "motion1", 1, 3, "Middle")
    assert result["verification_status"] == "not_rechecked"
    assert (await ops.verify_saved(result))["verification_status"] == "verified_metadata"
    assert len(api.calls) == 1


async def test_preview_decodes_timestamps_and_actual_image(setup):
    _, ops, _ = setup
    preview = await ops.preview("motion1")
    assert preview["credits_used"] == 0 and preview["billing"]["cost_status"] == "free_by_policy"
    assert preview["animated"] and preview["frame_times_seconds"] == [0, 0.1, 0.3]
    image, metadata = ops.preview_frame(preview["artifact_id"], 1)
    assert metadata["time_seconds"] == 0.1
    assert Image.open(io.BytesIO(image)).getpixel((0, 0)) == (0, 0, 255, 255)
    with pytest.raises(ValueError):
        ops.preview_frame(preview["artifact_id"], 3)


async def test_export_options_replay_and_missing_cached_file(setup):
    api, ops, _ = setup
    kwargs = dict(
        character_id="roblox1", format="fbx", fps=30, include_mesh=True, in_place=True, roblox_compatible=True
    )
    result = await ops.download("export1", "motion1", **kwargs)
    replay = await ops.download("export1", "motion1", **kwargs)
    assert replay["artifact_id"] == result["artifact_id"]
    assert replay["creates_new_motion"] is False
    assert api.calls == [("download", {"motion_id": "motion1", **kwargs})]
    Path(result["local_path"]).unlink()
    with pytest.raises(FileNotFoundError):
        await ops.download("export1", "motion1", **kwargs)
    assert len(api.calls) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fps": 25},
        {"format": "bvh"},
        {"roblox_compatible": True},
        {"format": "fbx", "roblox_compatible": True, "character_id": "mixamo1"},
    ],
)
async def test_unsupported_exports_do_not_download(setup, kwargs):
    api, ops, _ = setup
    with pytest.raises(ValueError):
        await ops.download("req", "motion1", **kwargs)
    assert not api.calls


@pytest.mark.parametrize("model", ["video-to-motion-2.0", "video-to-motion-2.1", "video-to-motion-3.0"])
async def test_video_upload_and_two_mixamo_retargets(setup, model):
    api, ops, inputs = setup
    video = inputs / "walk.mp4"
    video.write_bytes(b"fixture-video")
    result = await ops.video("video1", str(video), "Walk", model)
    assert result["job_id"] == "videojob1"
    await ops.video("video1", str(video), "Walk", model)
    for index in (1, 2):
        character = inputs / f"character{index}.fbx"
        character.write_bytes(f"rigged-fixture-{index}".encode())
        upload = await ops.upload_character(f"upload{index}", str(character), f"Character {index}")
        assert upload["character_id"] == f"mixamo{index}"
        await ops.download(f"export{index}", "motion1", character_id=upload["character_id"], format="fbx")
    assert len([c for c in api.calls if c[0] == "video"]) == 1
    assert [c[1]["character_id"] for c in api.calls if c[0] == "download"] == ["mixamo1", "mixamo2"]
    assert all(c[1]["auto_rig"] is False for c in api.calls if c[0] == "upload_character")


async def test_upload_scope_symlinks_and_changed_file(setup, tmp_path):
    api, ops, inputs = setup
    outside = tmp_path / "private.fbx"
    outside.write_bytes(b"private")
    link = inputs / "link.fbx"
    symlink_or_skip(link, outside)
    with pytest.raises(ValueError):
        await ops.upload_character("req", str(link), "Character")
    inside = inputs / "character.fbx"
    inside.write_bytes(b"first")
    await ops.upload_character("req", str(inside), "Character")
    inside.write_bytes(b"changed")
    with pytest.raises(ValueError, match="different arguments"):
        await ops.upload_character("req", str(inside), "Character")
    assert len(api.calls) == 1


async def test_save_existing_gltf_keeps_lineage(setup):
    api, ops, inputs = setup
    file = inputs / "edited.gltf"
    file.write_text(
        json.dumps(
            {
                "asset": {"version": "2.0"},
                "animations": [{"name": "Fixture"}],
                "buffers": [{"uri": "data:application/octet-stream;base64,AAAA"}],
            }
        )
    )
    result = await ops.save("save1", str(file), "motion1", "mixamo1", "Adjusted")
    assert result["motion_id"] == "saved1"
    assert result["source_motion_id"] == "motion1"
    assert result["verification_status"] == "verified_metadata"
    assert api.calls[0][1]["character"] == "mixamo1"
    await ops.save("save1", str(file), "motion1", "mixamo1", "Adjusted")
    assert len(api.calls) == 1


async def test_save_rejects_external_gltf_dependencies(setup):
    api, ops, inputs = setup
    file = inputs / "edited.gltf"
    file.write_text(
        json.dumps({"asset": {"version": "2.0"}, "animations": [{}], "buffers": [{"uri": "../secret.bin"}]})
    )
    with pytest.raises(ValueError, match="embed"):
        await ops.save("req", str(file), "motion1", "mixamo1", "Adjusted")
    assert not api.calls


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {},
        {"asset": {"version": "1.0"}, "animations": [{}]},
        {"asset": {"version": "2.0"}},
        {"asset": {"version": "2.0"}, "animations": []},
        {"asset": None, "animations": [{}]},
        {"asset": [], "animations": [{}]},
        {"asset": {"version": "2.0"}, "animations": "invalid"},
        {"asset": {"version": "2.0"}, "animations": [None]},
    ],
)
async def test_save_rejects_invalid_gltf_structure_before_submission(setup, document):
    api, ops, inputs = setup
    file = inputs / "invalid.gltf"
    file.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="animated GLTF 2.0"):
        await ops.save("invalid", str(file), "motion1", "mixamo1", "Edited")
    assert not api.calls
    assert ops.store.get_request("invalid")["state"] == "not_found"


async def test_whole_clip_trim_clamps_inclusive_end_to_final_frame(setup):
    _, ops, _ = setup
    result = await ops.trim("whole", "motion1", 0, 4, "Whole")
    assert result["native_frame_interval"] == [0, 119]
    assert result["saved"]["frame_count"] == 120
    assert result["verification_status"] == "verified_metadata"


async def test_saved_result_with_reused_source_bundle_fails_verification(setup):
    api, ops, _ = setup
    original_trim = api.trim

    async def reused(*args):
        result = await original_trim(*args)
        api.motions[result["motion_id"]]["bundle_id"] = api.motions["motion1"]["bundle_id"]
        return result

    api.trim = reused
    result = await ops.trim("bad-bundle", "motion1", 1, 3, "Middle")
    assert result["verification_status"] == "failed"
    assert "Result does not have its own bundle" in result["verification_errors"]
    assert ops.store.get_request("bad-bundle")["result"]["motion_id"] == "trimmed1"


async def test_export_speed_torso_options_and_changed_intent(setup):
    api, ops, _ = setup
    result = await ops.download("effects", "motion1", speed_multiplier=0.5, torso_only=True, in_place=True)
    assert result["speed_multiplier"] == 0.5 and result["torso_only"] is True
    assert result["fps"] == 30 and result["effective_in_place"] is False
    assert result["creates_new_motion"] is False and result["review_status"] == "unreviewed"
    replay = await ops.download("effects", "motion1", speed_multiplier=0.5, torso_only=True, in_place=True)
    assert replay["artifact_id"] == result["artifact_id"] and len(api.calls) == 1
    for change in ({"speed_multiplier": 2, "torso_only": True}, {"speed_multiplier": 0.5, "torso_only": False}):
        with pytest.raises(ValueError, match="different arguments"):
            await ops.download("effects", "motion1", in_place=True, **change)
    assert len(api.calls) == 1


async def test_default_options_recover_pre_expansion_export_receipt(setup):
    api, ops, _ = setup
    old_args = dict(
        motion_id="motion1",
        character_id="cXi2eAP19XwQ",
        format="glb",
        fps=30,
        include_mesh=True,
        in_place=False,
        roblox_compatible=False,
    )

    async def old_invoke():
        return ops.store.artifact(b"old-export", ".glb", old_args)

    previous = await ops.store.mutation("old", "download", old_args, old_invoke)
    result = await ops.download("old", "motion1", speed_multiplier=1, torso_only=False)
    assert result["replayed"] and result["artifact_id"] == previous["artifact_id"]
    assert api.calls == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"speed_multiplier": 0},
        {"speed_multiplier": -1},
        {"speed_multiplier": 2.01},
        {"speed_multiplier": float("nan")},
        {"speed_multiplier": float("inf")},
        {"speed_multiplier": True},
        {"torso_only": "false"},
    ],
)
async def test_invalid_new_export_options_never_download(setup, kwargs):
    api, ops, _ = setup
    with pytest.raises(ValueError):
        await ops.download("invalid", "motion1", **kwargs)
    assert api.calls == []
    assert ops.store.get_request("invalid")["state"] == "not_found"


@pytest.mark.parametrize("operation", ["trim", "save"])
@pytest.mark.parametrize("outcome", ["verified_metadata", "failed", "unverified", "source_id"])
async def test_saved_verification_history_survives_restart_and_metadata_outage(setup, tmp_path, operation, outcome):
    api, ops, inputs = setup
    source_file = inputs / "edited.gltf"
    source_file.write_text(json.dumps({"asset": {"version": "2.0"}, "animations": [{"name": "Fixture"}]}))
    original = getattr(api, operation)

    async def submit(*args):
        result = await original(*args)
        if outcome == "failed":
            api.motions[result["motion_id"]]["bundle_id"] = api.motions["motion1"]["bundle_id"]
        if outcome == "source_id":
            return {"motion_id": "motion1"}
        return result

    setattr(api, operation, submit)
    api.fail_verification = outcome == "unverified"

    async def invoke(instance):
        if operation == "trim":
            return await instance.trim("history", "motion1", 1, 3, "Result")
        return await instance.save("history", str(source_file), "motion1", "mixamo1", "Result")

    result = await invoke(ops)
    expected_status = "failed" if outcome == "source_id" else outcome
    assert result["verification_status"] == expected_status
    previous = result["previous_verification"]
    assert previous["status"] == expected_status and previous["checked_at_unix"] > 0
    if outcome == "failed":
        assert previous["errors"] == ["Result does not have its own bundle"]
    elif outcome == "source_id":
        assert previous["error"] == "Source ID was returned as result"
    elif outcome == "unverified":
        assert "Metadata unavailable" in previous["error"]
    else:
        assert previous["errors"] == []
    assert result["last_verification_attempt"] == previous
    with ops.store.connect() as db:
        identity = db.execute("SELECT operation,fingerprint,state,updated FROM requests WHERE id='history'").fetchone()
    original_receipt = ops.store.get_request("history")["result"]

    async def forbidden(*args):
        raise AssertionError("Completed recovery must not call Uthana")

    api.motion = forbidden
    setattr(api, operation, forbidden)
    restarted = Operations(api, tmp_path / "state", inputs)
    replay = await invoke(restarted)
    recovered = restarted.recover_request("history")["result"]
    for historical in (replay, recovered):
        assert historical["verification_status"] == "not_rechecked"
        assert historical["previous_verification"] == previous
        assert historical["last_verification_attempt"] == previous
    assert len(api.calls) == 1

    # A deliberate metadata recheck can fail without changing known prior findings.
    unavailable = await restarted.verify_saved(recovered)
    assert unavailable["verification_status"] == ("failed" if outcome == "source_id" else "unverified")
    if outcome in {"failed", "verified_metadata"}:
        assert unavailable["previous_verification"] == previous
        assert unavailable["last_verification_attempt"]["status"] == "unverified"
    assert "verification_note" not in unavailable and "saved" not in unavailable
    again = Operations(api, tmp_path / "state").recover_request("history")["result"]
    assert again["previous_verification"] == unavailable["previous_verification"]
    assert again["last_verification_attempt"] == unavailable["last_verification_attempt"]
    assert again["last_verification_attempt"]["checked_at_unix"] >= previous["checked_at_unix"]
    with restarted.store.connect() as db:
        assert (
            db.execute("SELECT operation,fingerprint,state,updated FROM requests WHERE id='history'").fetchone()
            == identity
        )
    current_receipt = restarted.store.get_request("history")["result"]
    for key in ("previous_verification", "last_verification_attempt"):
        original_receipt.pop(key)
        current_receipt.pop(key)
    assert current_receipt == original_receipt
    assert len(api.calls) == 1
