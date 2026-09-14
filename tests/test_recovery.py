import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.store import Store


@pytest.mark.parametrize("status,category", [(401, "authentication"), (403, "permission")])
async def test_rejected_http_request_persists_safe_cause_and_allows_explicit_retry(tmp_path, status, category):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["accept"] == "application/json"
        if len(calls) == 1:
            return httpx.Response(status, text="PRIVATE_PROVIDER_BODY")
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    ops = Operations(api, tmp_path)
    try:
        with pytest.raises(APIError, match="rejected"):
            await ops.generate("r", "Walk")
        restarted = Operations(api, tmp_path)
        rejected = restarted.recover_request("r")
        assert rejected["state"] == "rejected" and rejected["error"]["category"] == category
        assert rejected["error"]["safe_to_resubmit"] and "PRIVATE" not in json.dumps(rejected)
        assert len(calls) == 1
        with pytest.raises(ValueError, match="different arguments"):
            await restarted.generate("r", "Jump")
        assert len(calls) == 1
        result = await restarted.generate("r", "Walk")
        assert result["job_id"] == "job1" and len(calls) == 2
        assert restarted.recover_request("r")["error"] is None
        assert (await restarted.generate("r", "Walk"))["replayed"] and len(calls) == 2
    finally:
        await api.close()


@pytest.mark.parametrize("error_type", ["LoginRequired", "RoleRequired", "UserAccessRequired", "InsufficientBalance"])
async def test_root_graphql_rejections_are_actionable(tmp_path, error_type):
    body = {
        "data": {"create_text_to_motion_job": None},
        "errors": [
            {"type": error_type, "path": ["create_text_to_motion_job"], "message": "PRIVATE", "stack": "PRIVATE"},
        ],
    }
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    try:
        ops = Operations(api, tmp_path)
        with pytest.raises(APIError):
            await ops.generate("r", "Walk")
        record = ops.recover_request("r")
        assert record["state"] == "rejected" and "PRIVATE" not in json.dumps(record)
        assert record["error"]["category"] == (
            "balance"
            if error_type == "InsufficientBalance"
            else "authentication" if error_type == "LoginRequired" else "permission"
        )
    finally:
        await api.close()


@pytest.mark.parametrize(
    "case",
    ["nested", "mixed", "partial", "missing_path", "generic", "http_500", "http_429", "read_timeout", "malformed"],
)
async def test_ambiguous_failures_remain_unknown_without_resubmission(tmp_path, case):
    calls = []

    def respond(request):
        calls.append(request)
        if case == "read_timeout":
            raise httpx.ReadTimeout("PRIVATE", request=request)
        if case.startswith("http_"):
            return httpx.Response(int(case[5:]), text="PRIVATE")
        if case == "malformed":
            return httpx.Response(200, text="PRIVATE invalid json")
        error = {"type": "LoginRequired", "path": ["create_text_to_motion_job"], "message": "PRIVATE"}
        data = {"create_text_to_motion_job": None}
        errors = [error]
        if case == "nested":
            error["path"].append("job")
        if case == "missing_path":
            error.pop("path")
        if case == "generic":
            error["type"] = "Exception"
        if case == "mixed":
            errors.append({"type": "Exception", "path": ["create_text_to_motion_job"]})
        if case == "partial":
            data["create_text_to_motion_job"] = {"job": {"id": "accepted-job"}}
        return httpx.Response(200, json={"data": data, "errors": errors})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    ops = Operations(api, tmp_path)
    try:
        with pytest.raises(RuntimeError):
            await ops.generate("r", "Walk")
        status = ops.recover_request("r")
        assert status["state"] == "unknown" and not status["error"]["safe_to_resubmit"]
        assert "PRIVATE" not in json.dumps(status)
        with pytest.raises(ValueError, match="unresolved"):
            await ops.generate("r", "Walk")
        assert len(calls) == 1
    finally:
        await api.close()


async def test_connection_not_established_and_cancellation_are_distinct(tmp_path):
    def connect_fail(request):
        raise httpx.ConnectTimeout("PRIVATE", request=request)

    api = UthanaAPI("fake", transport=httpx.MockTransport(connect_fail))
    try:
        ops = Operations(api, tmp_path)
        with pytest.raises(APIError, match="no request was submitted"):
            await ops.generate("connect", "Walk")
        assert ops.recover_request("connect")["state"] == "rejected"
    finally:
        await api.close()
    fake = FakeAPI()

    async def cancel(**kwargs):
        raise asyncio.CancelledError()

    fake.generate = cancel
    ops = Operations(fake, tmp_path)
    with pytest.raises(asyncio.CancelledError):
        await ops.generate("cancel", "Walk")
    result = ops.recover_request("cancel")
    assert result["state"] == "unknown" and result["error"]["category"] == "interrupted"


async def test_completed_trim_and_export_replay_without_metadata(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    trimmed = await ops.trim("trim", "motion1", 1, 3, "Middle")
    exported = await ops.download("export", "trimmed1", character_id="roblox1", format="fbx", roblox_compatible=True)

    async def forbidden(*args, **kwargs):
        raise AssertionError("No network dependency is allowed on completed replay")

    api.motion = api.character_metadata = api.trim = api.download = forbidden
    replay = await ops.trim("trim", "motion1", 1, 3, "Middle")
    assert replay["motion_id"] == trimmed["motion_id"] and replay["verification_status"] == "not_rechecked"
    repeated = await ops.download("export", "trimmed1", character_id="roblox1", format="fbx", roblox_compatible=True)
    assert repeated["artifact_id"] == exported["artifact_id"] and repeated["sha256"] == exported["sha256"]
    for name in ["Changed"]:
        with pytest.raises(ValueError, match="different arguments"):
            await ops.trim("trim", "motion1", 1, 3, name)
    with pytest.raises(ValueError, match="different arguments"):
        await ops.download("export", "trimmed1", character_id="roblox1", format="fbx", roblox_compatible=True, fps=60)
    assert ops.recover_request("export")["artifact_status"] == "verified_local_bytes"
    Path(exported["local_path"]).unlink()
    status = ops.recover_request("export")
    assert status["artifact_status"] == "unavailable_or_changed" and status["result"]["motion_id"] == "trimmed1"


async def test_save_replay_and_recovery_when_original_file_is_gone(tmp_path):
    api = FakeAPI()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    source = inputs / "edited.gltf"
    original = json.dumps({"asset": {"version": "2.0"}, "animations": [{"name": "Motion"}]})
    source.write_text(original)
    ops = Operations(api, tmp_path / "state", inputs)
    saved = await ops.save("save", str(source), "motion1", "mixamo1", "Saved")

    async def forbidden(*args, **kwargs):
        raise AssertionError("No metadata read or save is allowed on replay")

    api.motion = api.save = forbidden
    replay = await ops.save("save", str(source), "motion1", "mixamo1", "Saved")
    assert replay["motion_id"] == saved["motion_id"] and replay["verification_status"] == "not_rechecked"
    with pytest.raises(ValueError, match="different arguments"):
        await ops.save("save", str(source), "motion1", "mixamo1", "Changed")
    source.write_text(original + " ")
    with pytest.raises(ValueError, match="different arguments"):
        await ops.save("save", str(source), "motion1", "mixamo1", "Saved")
    source.unlink()
    recovered = Operations(api, tmp_path / "state").recover_request("save")
    assert (
        recovered["result"]["motion_id"] == "saved1" and recovered["result"]["verification_status"] == "not_rechecked"
    )
    with pytest.raises(FileNotFoundError):
        await ops.save("save", str(source), "motion1", "mixamo1", "Saved")


async def test_legacy_database_migrates_without_changing_receipts(tmp_path):
    scope = tmp_path / "legacy"
    scope.mkdir()
    args = {"prompt": "Walk"}
    result = {"job_id": "old-job", "credits_used": None}
    with sqlite3.connect(scope / "requests.sqlite") as db:
        db.execute(
            "CREATE TABLE requests(id TEXT PRIMARY KEY,operation TEXT,fingerprint TEXT,state TEXT,result TEXT,updated REAL)"
        )
        db.execute(
            "INSERT INTO requests VALUES (?,?,?,?,?,?)",
            ("r", "generate", Store.fingerprint("generate", args), "complete", json.dumps(result), 1),
        )
    store = Store(tmp_path, "legacy")
    assert store.get_request("r")["result"] == result and store.get_request("r")["error"] is None
    assert store.replay("r", "generate", args)["job_id"] == "old-job"


async def test_rejected_retry_claim_remains_atomic(tmp_path):
    first, second = Store(tmp_path, "same"), Store(tmp_path, "same")

    async def reject():
        raise APIError("Rejected", category="permission", outcome="rejected")

    with pytest.raises(APIError):
        await first.mutation("r", "generate", {}, reject)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def invoke():
        calls.append(True)
        started.set()
        await release.wait()
        return {"job_id": "once"}

    task = asyncio.create_task(first.mutation("r", "generate", {}, invoke))
    await started.wait()
    try:
        with pytest.raises(ValueError, match="unresolved"):
            await second.mutation("r", "generate", {}, invoke)
    finally:
        release.set()
    await task
    assert calls == [True]
