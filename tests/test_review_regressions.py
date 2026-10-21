"""Regression coverage for pre-release review."""

import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path

import httpx
import pytest
from fakes import FakeAPI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image
from platform_support import symlink_or_skip
from test_stitch import clip

import uthana_mcp
import uthana_mcp.server as server_module
from uthana_mcp.api import UthanaAPI
from uthana_mcp.errors import APIError, graphql_error
from uthana_mcp.operations import Operations
from uthana_mcp.server import with_progress


async def test_large_catalog_filter_pagination_and_separate_read_cap(tmp_path):
    rows = [{"id": f"c{i}", "name": "Other" + "x" * 180} for i in range(16000)]
    rows.extend([{"id": "hero1", "name": "Rigged Hero"}, {"id": "hero2", "name": "RIGGED Hero Two"}])
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"characters": rows}})

    api = UthanaAPI("fake", transport=httpx.MockTransport(respond))
    try:
        ops = Operations(api, tmp_path)
        result = await ops.characters(limit=1, query="rigged hero")
        assert result["characters"] == [{"character_id": "hero1", "name": "Rigged Hero"}]
        assert result["scanned_count"] == 16002 and result["pagination"] == "local_bounded_catalog"
        assert result["next_offset"] == 1
        assert (await ops.characters(offset=1, limit=1, query="rigged hero"))["next_offset"] is None
        assert (await ops.characters(query="absent"))["characters"] == []
        assert len(calls) == 3
        # Increasing the catalog ceiling must not enlarge normal metadata/mutation responses.
        with pytest.raises(APIError, match="size limit") as caught:
            await api.usage()
        assert caught.value.category == "response_too_large"
    finally:
        await api.close()


async def test_catalog_over_16_mib_has_actionable_error(tmp_path):
    api = UthanaAPI(
        "fake", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * (16 * 1024 * 1024 + 1)))
    )
    try:
        with pytest.raises(APIError, match="smaller limit values cannot reduce") as caught:
            await Operations(api, tmp_path).characters(limit=1)
        assert caught.value.category == "catalog_too_large"
        assert caught.value.outcome == "not_applicable"
    finally:
        await api.close()


@pytest.mark.parametrize(
    "resource,kind,message",
    [
        ("motion", "UserAccessRequired", "This resource requires user access."),
        ("job", "TypeError", "'nonetype' object is not subscriptable."),
        ("job", "NotFound", "Missing"),
    ],
)
async def test_observed_missing_resource_errors_are_not_outages(resource, kind, message):
    response = {"data": {resource: None}, "errors": [{"type": kind, "message": message, "stack": ["private-path"]}]}
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)))
    try:
        with pytest.raises(APIError) as caught:
            await getattr(api, resource)("missing1")
        assert caught.value.category == "not_found" and caught.value.outcome == "not_applicable"
        assert "private-path" not in str(caught.value)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "resource,kind,message,expected",
    [
        ("job", "TypeError", "another bug", "graphql_error"),
        ("job", "LoginRequired", "login", "authentication"),
        ("motion", "LoginRequired", "login", "authentication"),
        ("job", "UserAccessRequired", "permission", "permission"),
    ],
)
def test_other_resource_failures_keep_their_category(resource, kind, message, expected):
    error = graphql_error(
        {"data": {resource: None}, "errors": [{"type": kind, "message": message}]}, read_only=True, resource=resource
    )
    assert error.category == expected


async def test_preview_http_404_is_not_found():
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda r: httpx.Response(404, text="private raw error")))
    try:
        with pytest.raises(APIError) as caught:
            await api.preview("missing1", "character1", "apng")
        assert caught.value.category == "not_found"
        assert "private raw error" not in str(caught.value)
    finally:
        await api.close()


@pytest.mark.parametrize(
    "message,category",
    [
        ("No rig found in scene /private/secret", "character_rig"),
        ("Essential joints missing: /private/secret", "character_rig"),
        ("Auto-rigging failed /private/secret", "character_rig"),
        ("Maximum number of characters /private/secret", "character_limit"),
        ("Provided file is too large /private/secret", "character_file"),
        ("unknown failure /private/secret", "character_processing"),
    ],
)
async def test_upload_failure_keeps_safe_diagnostic_and_inspection(tmp_path, message, category):
    source = tmp_path / "selected.glb"
    source.write_bytes(b"fixture")
    response = {
        "data": {"create_character": None},
        "errors": [{"message": message, "stack": ["secret"]}],
    }
    api = FakeAPI()

    async def failed(*args):
        raise graphql_error(response, "create_character")

    api.upload_character = failed
    ops = Operations(api, tmp_path / "state", tmp_path)
    with pytest.raises(RuntimeError, match="Inspect list_characters"):
        await ops.upload_character("upload1", str(source), "Selected character", False)
    receipt = ops.recover_request("upload1")
    assert receipt["state"] == "unknown" and not receipt["error"]["safe_to_resubmit"]
    assert receipt["error"]["category"] == category
    assert "secret" not in json.dumps(receipt)
    assert receipt["inspection"] == {
        "tool": "list_characters",
        "arguments": {"query": "Selected character", "limit": 50},
    }
    with pytest.raises(ValueError, match="unresolved"):
        await ops.upload_character("upload1", str(source), "Selected character", False)


async def test_old_unknown_upload_receipt_gets_guidance_without_changing_state(tmp_path):
    ops = Operations(FakeAPI(), tmp_path)
    with ops.store.connect() as db:
        db.execute(
            "INSERT INTO requests(id,operation,fingerprint,state,result,updated) VALUES(?,?,?,?,?,?)",
            ("legacy", "upload_character", "old", "unknown", None, 1),
        )
    result = ops.recover_request("legacy")
    assert result["state"] == "unknown" and result["inspection"]["tool"] == "list_characters"
    assert "original upload name" in result["next_action"]
    assert ops.store.get_request("legacy")["state"] == "unknown"


@pytest.mark.parametrize("failure", ["missing", "denied", "symlink"])
def test_file_errors_are_actionable_without_errno_or_private_path(tmp_path, monkeypatch, failure):
    ops = Operations(FakeAPI(), tmp_path / "state", tmp_path)
    source = tmp_path / "secret.glb"
    if failure == "denied":
        source.write_bytes(b"fixture")

        def denied(*args, **kwargs):
            raise PermissionError(13, "private error", str(source))

        monkeypatch.setattr("uthana_mcp.operations.os.open", denied)
    elif failure == "symlink":
        symlink_or_skip(source, source)
    with pytest.raises(ValueError, match="on the MCP server") as caught:
        ops.read_input(str(source), {".glb"})
    assert str(tmp_path) not in str(caught.value) and "Errno" not in str(caught.value)


class ProgressContext:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    async def report_progress(self, **event):
        if self.fail:
            raise ConnectionError("host disconnected")
        self.events.append(event)


async def test_progress_activity_is_monotonic_and_stops_on_completion(monkeypatch):
    monkeypatch.setattr(server_module, "PROGRESS_INTERVAL_SECONDS", 0.005)
    ctx = ProgressContext()

    async def work():
        await asyncio.sleep(0.025)
        return {"motion_id": "done"}

    assert await with_progress(ctx, work(), "test") == {"motion_id": "done"}
    assert len(ctx.events) >= 3
    assert [e["progress"] for e in ctx.events] == list(range(len(ctx.events)))
    assert ctx.events[-1]["message"].endswith("completed")
    count = len(ctx.events)
    await asyncio.sleep(0.015)
    assert len(ctx.events) == count
    assert await with_progress(ProgressContext(fail=True), work(), "test") == {"motion_id": "done"}


async def test_progress_cancellation_finishes_receipt_cleanup(tmp_path):
    source = tmp_path / "chosen.glb"
    source.write_bytes(b"fixture")
    entered = asyncio.Event()
    stopped = asyncio.Event()
    api = FakeAPI()

    async def long_upload(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    api.upload_character = long_upload
    ops = Operations(api, tmp_path / "state", tmp_path)
    task = asyncio.create_task(
        with_progress(ProgressContext(), ops.upload_character("cancelled", str(source), "Chosen", False), "upload")
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert ops.recover_request("cancelled")["state"] == "unknown"
    assert ops.recover_request("cancelled")["inspection"]["arguments"]["query"] == "Chosen"


def assert_descriptions(schema):
    if isinstance(schema, dict):
        for name, value in schema.get("properties", {}).items():
            assert value.get("description"), (name, value)
        for value in schema.values():
            assert_descriptions(value)
    elif isinstance(schema, list):
        for value in schema:
            assert_descriptions(value)


async def test_wire_schemas_and_progress_for_all_four_long_tools(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    character = inputs / "chosen.glb"
    character.write_bytes(b"fixture")
    reference = inputs / "reference.png"
    Image.new("RGB", (8, 8), "blue").save(reference)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("stdio_fixture.py")), str(tmp_path)],
        env={"PYTHONPATH": str(Path(uthana_mcp.__file__).resolve().parent.parent)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.version == version("uthana-mcp")
            assert "three" not in initialized.instructions
            for tool in (await client.list_tools()).tools:
                assert_descriptions(tool.inputSchema)
                assert "ctx" not in tool.inputSchema["properties"]
                assert "\ufffd" not in tool.description and "\n        " not in tool.description
            calls = [
                ("upload_character", {"request_id": "up", "file_path": str(character), "name": "Chosen"}),
                ("create_character_from_image", {"request_id": "img", "file_path": str(reference), "name": "Hero"}),
                ("create_looped_motion", {"request_id": "loop", "motion_id": "motion1"}),
                ("create_stitched_motion", {"request_id": "join", "prefix": clip(), "suffix": clip("motion2")}),
            ]
            for name, arguments in calls:
                events = []

                async def progress(value, total, message):
                    events.append((value, total, message))

                result = await client.call_tool(name, arguments, progress_callback=progress)
                assert not result.isError, result
                assert len(events) >= 2
                assert events[0][2] == f"{name}: started" and events[-1][2] == f"{name}: completed"
                assert all(total is None for _, total, _ in events)
                assert [value for value, _, _ in events] == sorted(set(value for value, _, _ in events))


async def test_not_found_category_reaches_tool_error(tmp_path):
    api = UthanaAPI("fake", transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    try:
        server = server_module.create_server(Operations(api, tmp_path))
        with pytest.raises(Exception, match='"category": "not_found"'):
            await server.call_tool("get_motion", {"motion_id": "missing1"})
    finally:
        await api.close()
