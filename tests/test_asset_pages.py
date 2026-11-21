"""MCP browsing delegates ordering and cursors to the published SDK and keeps asset metadata."""

import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI

from uthana_mcp.api import UthanaAPI
from uthana_mcp.catalog import MAX_CURSOR_LENGTH, asset_page
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server


@pytest.mark.parametrize("kind", ["character", "motion"])
@pytest.mark.parametrize("order", ["created_desc", "created_asc", "name_asc", "name_desc"])
async def test_sdk_page_order_filters_dates_and_older_history(tmp_path: Path, kind: str, order: str) -> None:
    calls = []
    cursor = "opaque+cursor/position=="
    rows = [
        {
            "id": "new1",
            "org_id": "org1",
            "name": "Walk",
            "created": "2026-11-20T12:00:00Z",
            "updated": None,
            "tags": {"Method": "TextToMotion"},
        },
        {
            "id": "old1001",
            "org_id": "org1",
            "name": "Walk",
            "created": "2020-01-01T00:00:00Z",
            "updated": "2020-02-01T00:00:00Z",
        },
    ]
    field = kind + "s_paged"

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert field in body["query"] and "mutation" not in body["query"]
        assert "id name org_id created updated" in body["query"]
        variables = body["variables"]
        expected = {"query": "walk", "source": "mine", "order": order, "limit": 1}
        if kind == "motion":
            expected["method"] = "TextToMotion"
        if len(calls) == 2:
            expected["cursor"] = cursor
        assert variables == expected
        index = len(calls) - 1
        return httpx.Response(
            200, json={"data": {field: {"items": [rows[index]], "next_cursor": cursor if index == 0 else None}}}
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path)
        browse = ops.characters if kind == "character" else ops.motions
        options = {"query": "walk", "source": "mine", "order": order, "limit": 1}
        if kind == "motion":
            options["method"] = "TextToMotion"
        first = await browse(**options)
        second = await browse(**options, cursor=first["next_cursor"])
        for page, row in [(first, rows[0]), (second, rows[1])]:
            item = page[kind + "s"][0]
            assert item[kind + "_id"] == row["id"]
            assert item["name"] == "Walk" and item["created"] == row["created"]
            assert item["updated"] == row["updated"] and item["org_id"] == "org1"
        assert first["next_cursor"] == cursor and second["next_cursor"] is None
        assert len(calls) == 2  # One SDK request per page; no full catalog or organization lookup.
    finally:
        await api.close()


@pytest.mark.parametrize("kind", ["character", "motion"])
@pytest.mark.parametrize("source", ["all", "mine", "uthana"])
async def test_browse_defaults_and_sources(tmp_path: Path, kind: str, source: str) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    browse = ops.characters if kind == "character" else ops.motions
    await browse(source=source)
    name, options = api.calls[-1]
    assert name == ("characters" if kind == "character" else "motions_page")
    assert options["source"] == source and options["order"] == "created_desc"
    assert options["limit"] == 20 and options["cursor"] is None


@pytest.mark.parametrize("kind", ["character", "motion"])
async def test_tool_schema_read_only_cursor_and_strict_inputs(tmp_path: Path, kind: str) -> None:
    api = FakeAPI()
    server = create_server(Operations(api, tmp_path))
    tool = server._tool_manager.get_tool("list_" + kind + "s")
    assert tool.annotations.readOnlyHint is True
    listed = {item.name: item for item in await server.list_tools()}
    properties = listed["list_" + kind + "s"].inputSchema["properties"]
    assert "offset" not in properties
    assert properties["source"]["enum"] == ["all", "mine", "uthana"]
    assert properties["order"]["default"] == "created_desc"
    for options in [
        {"limit": True},
        {"limit": "1"},
        {"limit": 0},
        {"limit": 101},
        {"cursor": ""},
        {"cursor": False},
        {"cursor": "x" * (MAX_CURSOR_LENGTH + 1)},
        {"source": "organization"},
        {"order": "updated_desc"},
        {"query": "x" * 201},
    ]:
        with pytest.raises(Exception):
            await tool.run(options)
    assert api.calls == []
    result = await tool.run({"source": "mine", "limit": 1})
    assert result[kind + "s"][0]["created"] == "2026-11-20T12:00:00Z"


@pytest.mark.parametrize("kind", ["character", "motion"])
@pytest.mark.parametrize(
    "options",
    [
        {"limit": False},
        {"limit": 0},
        {"limit": 101},
        {"source": "examples"},
        {"order": "updated_desc"},
        {"cursor": ""},
        {"query": 1},
    ],
)
async def test_direct_operation_validation_precedes_network(tmp_path: Path, kind: str, options: dict) -> None:
    api = FakeAPI()
    ops = Operations(api, tmp_path)
    with pytest.raises(ValueError):
        await (ops.characters if kind == "character" else ops.motions)(**options)
    assert api.calls == []


async def test_empty_method_is_rejected_before_network(tmp_path: Path) -> None:
    api = FakeAPI()
    with pytest.raises(ValueError, match="method"):
        await Operations(api, tmp_path).motions(method="  ")
    assert api.calls == []


@pytest.mark.parametrize("kind", ["character", "motion"])
@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"items": []},
        {"items": {}, "next_cursor": None},
        {"items": [], "next_cursor": 1},
        {"items": [], "next_cursor": ""},
        {"items": [None], "next_cursor": None},
        {"items": [{"id": "bad/id"}], "next_cursor": None},
        {"items": [{"id": "a", "name": False}], "next_cursor": None},
        {"items": [{"id": "a", "created": {}}], "next_cursor": None},
        {"items": [{"id": "a", "org_id": []}], "next_cursor": None},
        {"items": [{"id": "a"}, {"id": "b"}], "next_cursor": None},
    ],
)
def test_malformed_pages_are_read_failures(kind: str, data: object) -> None:
    with pytest.raises(APIError) as error:
        asset_page(data, kind=kind, limit=1)
    assert error.value.outcome == "not_applicable"


@pytest.mark.parametrize("kind", ["character", "motion"])
def test_empty_page_and_nullable_dates_are_preserved_without_mutation(kind: str) -> None:
    assert asset_page({"items": [], "next_cursor": None}, kind=kind, limit=1) == {kind + "s": [], "next_cursor": None}
    data = {
        "items": [{"id": "a", "name": None, "created": None, "tags": {"Method": "Upload"}, "private_debug": "omit"}],
        "next_cursor": "next",
    }
    before = deepcopy(data)
    result = asset_page(data, kind=kind, limit=1)
    assert data == before
    item = result[kind + "s"][0]
    assert item["name"] is None and item["created"] is None and item["updated"] is None
    assert "private_debug" not in item and result["next_cursor"] == "next"
    if kind == "motion":
        assert item["method"] == "Upload"


@pytest.mark.parametrize("kind", ["character", "motion"])
@pytest.mark.parametrize("failure", ["invalid_cursor", "oversized_page"])
async def test_paging_failures_do_not_fall_back_to_catalogs(tmp_path: Path, kind: str, failure: str) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert kind + "s_paged" in body["query"] and "mutation" not in body["query"]
        if failure == "oversized_page":
            return httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
        return httpx.Response(
            200, json={"data": None, "errors": [{"type": "ValueError", "message": "private-provider-detail"}]}
        )

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path)
        browse = ops.characters if kind == "character" else ops.motions
        with pytest.raises(APIError) as error:
            await browse(limit=1, cursor="stale-cursor")
        assert error.value.outcome == "not_applicable"
        assert error.value.category == ("response_too_large" if failure == "oversized_page" else "graphql_error")
        assert "private-provider-detail" not in str(error.value)
        assert len(calls) == 1
    finally:
        await api.close()
