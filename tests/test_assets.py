"""Asset lifecycle: ownership, name confirmation, idempotent outcomes, and the API contract."""

import json

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.assets import AssetLifecycle
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations


@pytest.fixture
def ops(tmp_path):
    return Operations(FakeAPI(), tmp_path / "state", tmp_path / "inputs")


def changes(ops):
    return [call for call in ops.api.calls if call[0] == "update_asset"]


@pytest.mark.parametrize("kind,asset_id", [("character", "mixamo1"), ("motion", "motion1")])
async def test_delete_then_restore_reports_each_state_once(ops, kind, asset_id):
    name = ops.api.assets[asset_id]["name"]

    deleted = await ops.assets.delete(kind, asset_id, name)
    assert deleted["outcome"] == "deleted" and deleted["changed"] is True
    assert deleted["restorable"] is True and deleted["restore_tool"] == f"restore_{kind}"
    assert deleted["deleted_at"] and deleted["kept"]
    again = await ops.assets.delete(kind, asset_id, name)
    assert again["outcome"] == "not_found_or_already_deleted" and again["changed"] is False

    restored = await ops.assets.restore(kind, asset_id)
    assert restored == {"kind": kind, "asset_id": asset_id, "name": name, "outcome": "restored", "changed": True}
    assert (await ops.assets.restore(kind, asset_id))["outcome"] == "already_active"
    assert [call[1]["action"] for call in changes(ops)] == ["delete", "restore"]


async def test_character_delete_keeps_motions(ops):
    result = await ops.assets.delete("character", "mixamo1", "First")
    assert any("every motion is kept" in line for line in result["kept"])
    assert ops.api.assets["motion1"]["deleted"] is None


@pytest.mark.parametrize("action", ["rename", "delete", "restore"])
async def test_built_in_and_foreign_assets_are_refused_without_writing(ops, action):
    for asset_id, kind in (("tar1", "character"), ("example1", "motion")):
        name = ops.api.assets[asset_id]["name"]
        call = {
            "rename": lambda: ops.assets.rename(kind, asset_id, "Mine now"),
            "delete": lambda: ops.assets.delete(kind, asset_id, name),
            "restore": lambda: ops.assets.restore(kind, asset_id),
        }[action]
        with pytest.raises(APIError) as error:
            await call()
        assert error.value.category == "not_owned" and error.value.outcome == "rejected"
    assert changes(ops) == []


async def test_name_mismatch_refuses_delete(ops):
    with pytest.raises(APIError) as error:
        await ops.assets.delete("motion", "motion1", "Walking")
    assert error.value.category == "name_mismatch"
    assert "Walking slowly" in str(error.value)
    assert changes(ops) == []


async def test_rename_reports_previous_name_and_repeat_is_unchanged(ops):
    renamed = await ops.assets.rename("motion", "motion1", "Stroll")
    assert renamed["outcome"] == "renamed" and renamed["previous_name"] == "Walking slowly"
    repeat = await ops.assets.rename("motion", "motion1", "Stroll")
    assert repeat["outcome"] == "unchanged" and repeat["changed"] is False
    assert len(changes(ops)) == 1


async def test_rename_of_missing_asset_is_rejected(ops):
    with pytest.raises(APIError) as error:
        await ops.assets.rename("character", "missing1", "Name")
    assert error.value.category == "not_found" and error.value.outcome == "rejected"


async def test_restore_of_foreign_deleted_asset_is_refused_unchanged(ops):
    # The backend refuses another organization's asset (admins included), so nothing is restored or undone.
    ops.api.assets["foreign1"]["deleted"] = "2026-11-01T00:00:00"
    for _ in range(2):
        with pytest.raises(APIError) as error:
            await ops.assets.restore("character", "foreign1")
        assert error.value.category == "not_found" and error.value.outcome == "rejected"
        assert "Nothing was changed" in str(error.value)
        assert ops.api.assets["foreign1"]["deleted"] is not None
    assert [call[1]["action"] for call in changes(ops)] == ["restore", "restore"]


async def test_restore_without_write_access_is_not_found(ops):
    with pytest.raises(APIError) as error:
        await ops.assets.restore("motion", "missing1")
    assert error.value.category == "not_found" and error.value.outcome == "rejected"


async def test_download_character_saves_model_artifact(ops):
    result = await ops.download_character("mixamo1", "glb")
    data, metadata = ops.store.read_artifact(result["artifact_id"])
    assert data.startswith(b"glTF") and metadata["asset_kind"] == "character_model"
    assert metadata["billing"]["cost_status"] == "free_by_policy"
    with pytest.raises(ValueError):
        await ops.download_character("mixamo1", "bvh")


async def test_api_lifecycle_documents_and_owner_check_inputs():
    seen = []
    record = {"id": "c1", "name": "Knight", "org_id": "o1", "created": None, "updated": None, "deleted": None}

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        if "update_character" in body["query"]:
            deleted = "2026-11-04T00:00:00" if body["variables"].get("deleted") else None
            return httpx.Response(
                200, json={"data": {"update_character": {"character": {**record, "deleted": deleted}}}}
            )
        if "character(id:" in body["query"]:
            return httpx.Response(200, json={"data": {"character": record}})
        return httpx.Response(200, json={"data": {"org": {"id": "o1", "name": "Org"}}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        assert await api.org_id() == "o1"
        assert await api.org_id() == "o1"
        assert (await api.asset("character", "c1"))["org_id"] == "o1"
        assert (await api.update_asset("character", "c1", "delete"))["deleted"]
        assert (await api.update_asset("character", "c1", "restore"))["deleted"] is None
    finally:
        await api.close()
    assert sum("motion_download_secs_per_month" in body["query"] for body in seen) == 1
    assert all("own_org_only: $own_org_only" in body["query"] for body in seen[-2:])
    assert [body["variables"] for body in seen[-2:]] == [
        {"character_id": "c1", "deleted": True, "own_org_only": True},
        {"character_id": "c1", "deleted": False, "own_org_only": True},
    ]


@pytest.mark.parametrize("kind", ["character", "motion"])
async def test_api_restore_refused_by_backend_is_not_found_and_not_undone(kind):
    # An admin account restoring another organization's asset: the backend refuses it with no change.
    seen = []

    def respond(request):
        body = json.loads(request.content)
        seen.append(body)
        error = {
            "message": f"{kind.capitalize()} x1 does not belong to your organization. Nothing was changed.",
            "type": "UserAccessRequired",
            "path": [f"update_{kind}"],
        }
        return httpx.Response(200, json={"data": None, "errors": [error]})

    class MissingThenRestore(UthanaAPI):
        async def asset(self, kind, asset_id):
            raise APIError("Motion, character, or job not found.", category="not_found", outcome="not_applicable")

    api = MissingThenRestore("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as error:
            await AssetLifecycle(api).restore(kind, "x1")
    finally:
        await api.close()
    assert error.value.category == "not_found" and error.value.outcome == "rejected"
    assert [body["variables"] for body in seen] == [{f"{kind}_id": "x1", "deleted": False, "own_org_only": True}]
