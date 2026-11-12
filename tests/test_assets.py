"""Asset lifecycle: ownership, ID selection, idempotent outcomes, and the API contract."""

import json
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.assets import AssetLifecycle
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.validation import asset_record


@pytest.fixture
def ops(tmp_path: Path) -> Operations:
    return Operations(FakeAPI(), tmp_path / "state", tmp_path / "inputs")


def changes(ops: Operations) -> list:
    return [call for call in ops.api.calls if call[0] == "update_asset"]


@pytest.mark.parametrize("kind,asset_id", [("character", "mixamo1"), ("motion", "motion1")])
async def test_delete_then_restore_reports_each_state_once(ops: Operations, kind: str, asset_id: str) -> None:
    name = ops.api.assets[asset_id]["name"]

    deleted = await ops.assets.delete(kind, asset_id)
    assert deleted["outcome"] == "deleted" and deleted["changed"] is True
    assert deleted["restorable"] is True and deleted["restore_tool"] == f"restore_{kind}"
    assert deleted["deleted_at"] and deleted["kept"]
    again = await ops.assets.delete(kind, asset_id)
    assert again["outcome"] == "not_found_or_already_deleted" and again["changed"] is False

    restored = await ops.assets.restore(kind, asset_id)
    assert restored == {"kind": kind, "asset_id": asset_id, "name": name, "outcome": "restored", "changed": True}
    assert (await ops.assets.restore(kind, asset_id))["outcome"] == "already_active"
    assert [call[1]["action"] for call in changes(ops)] == ["delete", "restore"]


async def test_character_delete_keeps_motions(ops: Operations) -> None:
    result = await ops.assets.delete("character", "mixamo1")
    assert any("every motion is kept" in line for line in result["kept"])
    assert ops.api.assets["motion1"]["deleted"] is None


@pytest.mark.parametrize("action", ["rename", "delete", "restore"])
@pytest.mark.parametrize("kind,asset_id", [("character", "tar1"), ("motion", "example1")])
async def test_foreign_and_missing_assets_are_indistinguishable(
    ops: Operations, action: str, kind: str, asset_id: str
) -> None:
    async def invoke(selected: str) -> object:
        if action == "rename":
            return await ops.assets.rename(kind, selected, name="Mine now")
        return await getattr(ops.assets, action)(kind, selected)

    before = dict(ops.api.assets[asset_id])
    if action == "delete":
        foreign = await invoke(asset_id)
        missing = await invoke("missing1")
        assert {key: value for key, value in foreign.items() if key not in {"asset_id", "message"}} == {
            key: value for key, value in missing.items() if key not in {"asset_id", "message"}
        }
        assert changes(ops) == []
    else:
        with pytest.raises(APIError) as foreign:
            await invoke(asset_id)
        with pytest.raises(APIError) as missing:
            await invoke("missing1")
        assert foreign.value.category == missing.value.category == "not_found"
        assert foreign.value.outcome == missing.value.outcome == "rejected"
        if action == "rename":
            assert changes(ops) == []
        else:
            assert len(changes(ops)) == 2
    assert ops.api.assets[asset_id] == before


async def test_delete_reports_current_name_after_concurrent_rename(ops: Operations) -> None:
    original = ops.api.update_asset

    async def update(kind: str, asset_id: str, action: str, *, name: str | None = None) -> dict:
        if action == "delete":
            ops.api.assets[asset_id]["name"] = "Renamed while deleting"
        return await original(kind, asset_id, action, name=name)

    ops.api.update_asset = update
    result = await ops.assets.delete("motion", "motion1")
    assert result["outcome"] == "deleted"
    assert result["name"] == "Renamed while deleting"


@pytest.mark.parametrize("name", [None, "", "Named asset"])
@pytest.mark.parametrize("kind,asset_id", [("character", "mixamo1"), ("motion", "motion1")])
async def test_unnamed_assets_can_be_deleted_and_restored(
    ops: Operations, name: str | None, kind: str, asset_id: str
) -> None:
    ops.api.assets[asset_id]["name"] = name
    result = await ops.assets.delete(kind, asset_id)
    assert result["name"] == name
    restored = await ops.assets.restore(kind, asset_id)
    assert restored["name"] == name


@pytest.mark.parametrize("name", [None, "", "Named asset"])
def test_asset_record_preserves_nullable_names(name: str | None) -> None:
    assert asset_record({"id": "c1", "org_id": "o1", "name": name, "deleted": None})["name"] == name


async def test_rename_reports_previous_name_and_repeat_is_unchanged(ops: Operations) -> None:
    renamed = await ops.assets.rename("motion", "motion1", name="Stroll")
    assert renamed["outcome"] == "renamed" and renamed["previous_name"] == "Walking slowly"
    repeat = await ops.assets.rename("motion", "motion1", name="Stroll")
    assert repeat["outcome"] == "unchanged" and repeat["changed"] is False
    assert len(changes(ops)) == 1


async def test_rename_of_missing_asset_is_rejected(ops: Operations) -> None:
    with pytest.raises(APIError) as error:
        await ops.assets.rename("character", "missing1", name="Name")
    assert error.value.category == "not_found" and error.value.outcome == "rejected"


async def test_restore_of_foreign_deleted_asset_is_refused_unchanged(ops: Operations) -> None:
    # The backend refuses another organization's asset (admins included), so nothing is restored or undone.
    ops.api.assets["foreign1"]["deleted"] = "2026-11-01T00:00:00"
    for _ in range(2):
        with pytest.raises(APIError) as error:
            await ops.assets.restore("character", "foreign1")
        assert error.value.category == "not_found" and error.value.outcome == "rejected"
        assert ops.api.assets["foreign1"]["deleted"] is not None
    assert [call[1]["action"] for call in changes(ops)] == ["restore", "restore"]


async def test_restore_without_write_access_is_not_found(ops: Operations) -> None:
    with pytest.raises(APIError) as error:
        await ops.assets.restore("motion", "missing1")
    assert error.value.category == "not_found" and error.value.outcome == "rejected"


async def test_download_character_saves_model_artifact(ops: Operations) -> None:
    result = await ops.download_character("mixamo1", "glb")
    data, metadata = ops.store.read_artifact(result["artifact_id"])
    assert data.startswith(b"glTF") and metadata["asset_kind"] == "character_model"
    assert metadata["billing"]["cost_status"] == "free_by_policy"
    with pytest.raises(ValueError):
        await ops.download_character("mixamo1", "bvh")


async def test_api_lifecycle_documents_and_owner_check_inputs() -> None:
    seen = []
    record = {"id": "c1", "name": "Knight", "org_id": "o1", "created": None, "updated": None, "deleted": None}

    def respond(request: httpx.Request) -> httpx.Response:
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
        assert (await api.org())["id"] == "o1"
        assert await api.org_id() == "o1"
        assert await api.org_id() == "o1"
        assert (await api.asset("character", "c1"))["org_id"] == "o1"
        assert (await api.update_asset("character", "c1", action="delete"))["deleted"]
        assert (await api.update_asset("character", "c1", action="restore"))["deleted"] is None
    finally:
        await api.close()
    assert sum("motion_download_secs_per_month" in body["query"] for body in seen) == 3
    assert all("own_org_only" not in body["query"] for body in seen[-2:])
    assert [body["variables"] for body in seen[-2:]] == [
        {"character_id": "c1", "deleted": True},
        {"character_id": "c1", "deleted": False},
    ]


@pytest.mark.parametrize("kind", ["character", "motion"])
async def test_api_restore_refused_by_backend_is_not_found_and_not_undone(kind: str):
    # An admin account restoring another organization's asset -> Any: the backend refuses it with no change.
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        error = {
            "message": "Resource not found.",
            "type": "ResourceNotFound",
            "path": [f"update_{kind}"],
        }
        return httpx.Response(404, json={"data": None, "errors": [{**error, "path": [f"update_{kind}"]}]})

    class MissingThenRestore(UthanaAPI):
        async def asset(self, kind: str, asset_id: str) -> None:
            raise APIError("Motion, character, or job not found.", category="not_found", outcome="not_applicable")

    api = MissingThenRestore("fake", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as error:
            await AssetLifecycle(api).restore(kind, "x1")
    finally:
        await api.close()
    assert error.value.category == "not_found" and error.value.outcome == "rejected"
    assert [body["variables"] for body in seen] == [{f"{kind}_id": "x1", "deleted": False}]


@pytest.mark.parametrize(
    "record",
    [
        [],
        {},
        {"id": "o1", "name": 2},
        {"id": "o1", "motion_download_secs_per_month": True},
        {"id": "o1", "motion_download_secs_per_month_remaining": float("nan")},
    ],
)
async def test_invalid_org_records_are_read_errors(record: object) -> None:
    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"org": record}}))
    )
    try:
        with pytest.raises(APIError) as error:
            await api.org()
        assert error.value.outcome == "not_applicable"
    finally:
        await api.close()


async def test_org_id_reads_current_organization_without_a_cache() -> None:
    records = iter(
        [
            {"id": "o1", "name": None, "motion_download_secs_per_month": 0},
            {"id": "o2", "name": "New org", "motion_download_secs_per_month_remaining": None},
        ]
    )
    api = UthanaAPI(
        "fake",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"org": next(records)}})),
    )
    try:
        assert (await api.org())["motion_download_secs_per_month"] == 0
        assert await api.org_id() == "o2"
    finally:
        await api.close()
