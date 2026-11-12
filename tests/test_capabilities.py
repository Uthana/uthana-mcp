"""The capability catalog stays in step with registered tools and never creates work."""

import json
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeAPI
from starlette.testclient import TestClient
from test_hosted import ORIGIN, app_for, tool

from uthana_mcp.billing import PUBLISHED_MODELS
from uthana_mcp.capabilities import OPERATIONS, STATUSES
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server

HOSTED_ONLY = {"get_artifact_download"}


def local_server(tmp_path: Path, api: Any = None) -> Any:
    return create_server(Operations(api or FakeAPI(), tmp_path / "data", tmp_path / "input"))


def test_catalog_rows_are_well_formed() -> None:
    ids = [row["id"] for row in OPERATIONS]
    assert len(ids) == len(set(ids))
    for row in OPERATIONS:
        assert row["status"] in STATUSES
        assert set(row["models"]) <= set(PUBLISHED_MODELS), row["id"]
        assert bool(row["tools"]) == (row["status"] == "available"), row["id"]
        assert row["docs"] is None or row["docs"].startswith("https://uthana.com/docs/api")


async def test_every_local_tool_is_cataloged_and_every_cataloged_tool_exists(tmp_path: Path) -> None:
    server = local_server(tmp_path)
    registered = {registered.name for registered in await server.list_tools()}
    cataloged = {name for row in OPERATIONS for name in row["tools"]}
    assert registered <= cataloged
    assert cataloged - registered == HOSTED_ONLY


async def test_get_capabilities_reads_account_without_creating_work(tmp_path: Path) -> None:
    api = FakeAPI()
    server = local_server(tmp_path, api)
    result = await server._tool_manager.get_tool("get_capabilities").run({})
    assert api.calls == [("usage", {})]
    deployment = result["deployment"]
    assert deployment["transport"] == "local_stdio" and deployment["environment"]
    assert "get_capabilities" in deployment["tools"] and "get_artifact_download" not in deployment["tools"]
    rows = {row["id"]: row for row in result["operations"]}
    assert rows["text_to_motion_3"]["available_here"] is True
    assert rows["hosted_artifacts"]["available_here"] is False
    assert rows["text_to_motion_1"]["status"] == "platform_only" and not rows["text_to_motion_1"]["tools"]
    account = result["account"]
    assert account["payg_enabled"] is False
    assert account["models"]["text-to-motion-3.0"] == {
        "rate_listed": False,
        "unit_price_usd": None,
        "billing_unit": None,
    }
    assert account["monthly_downloads"]["remaining"] == 15


async def test_get_capabilities_can_skip_the_account_read(tmp_path: Path) -> None:
    api = FakeAPI()
    result = (
        await local_server(tmp_path, api)._tool_manager.get_tool("get_capabilities").run({"include_account": False})
    )
    assert api.calls == [] and "account" not in result


async def test_catalog_works_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTHANA_API_KEY", "")
    server = create_server()
    result = await server._tool_manager.get_tool("get_capabilities").run({})
    assert result["account"]["checked_at"] is None and "UTHANA_API_KEY" in result["account"]["error"]
    resource = json.loads((await server.read_resource("uthana://capabilities"))[0].content)
    assert resource["schema_version"] == 1 and "account" not in resource


def test_hosted_catalog_reports_hosted_tools_for_read_only_users(tmp_path: Path) -> None:
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        result = tool(client, "get_capabilities", {"include_account": False}, user="read-only")
        assert not result.get("isError"), result
        catalog = result["structuredContent"]
        assert catalog["deployment"]["transport"] == "hosted"
        rows = {row["id"]: row for row in catalog["operations"]}
        assert rows["hosted_artifacts"]["available_here"] is True
