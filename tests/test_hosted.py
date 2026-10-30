"""Actual HTTP transport, identity isolation and owned file access without paid services."""

import asyncio
import io
import json
import socket

import httpx
import pytest
from fakes import FakeAPI, apng
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image
from starlette.testclient import TestClient

import uthana_mcp.hosted_files as hosted_files
from uthana_mcp.hosted import Files, Identity, InputFile, create_app
from uthana_mcp.operations import Operations

ORIGIN = "https://mcp.example.test"
HEADERS = {"Authorization": "Bearer user1", "Accept": "application/json, text/event-stream"}


def app_for(directory, apis):
    async def authenticate(request):
        key = request.headers.get("Authorization", "").removeprefix("Bearer ")
        key = {"user1-rotated": "user1"}.get(key, key)
        if key not in {"user1", "user2", "read-only"}:
            return None
        return Identity(key, "org1", frozenset({"mcp:read"} if key == "read-only" else {"mcp:read", "mcp:write"}))

    async def api_factory(request, identity):
        api = apis.setdefault(identity.subject, FakeAPI())
        api.scope = identity.scope
        return api

    return create_app(
        origin=ORIGIN,
        directory=directory,
        issuer="https://issuer.example.test",
        authenticate=authenticate,
        api_factory=api_factory,
    )


def rpc(client, method, params=None, *, user="user1"):
    return client.post(
        "/mcp",
        headers={**HEADERS, "Authorization": "Bearer " + user},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def tool(client, name, args, *, user="user1"):
    response = rpc(client, "tools/call", {"name": name, "arguments": args}, user=user)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_discovery_auth_origin_and_remote_schema(tmp_path):
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"] == ORIGIN + "/mcp"
        assert client.post("/mcp").status_code == 401
        denied = client.post("/mcp", headers={**HEADERS, "Origin": "https://evil.test"})
        assert denied.status_code == 403
        result = rpc(client, "tools/list").json()
        tools = {row["name"]: row for row in result["result"]["tools"]}
        assert len(tools) == 24
        for name in ["generate_motion_from_video", "upload_character", "create_character_from_image", "save_motion"]:
            assert "input_file" in tools[name]["inputSchema"]["properties"]
            assert "file_path" not in tools[name]["inputSchema"]["properties"]
            assert tools[name]["_meta"]["openai/fileParams"] == ["input_file"]


def test_http_replay_survives_token_context_and_app_restart(tmp_path):
    apis = {}
    args = {"request_id": "job-once", "prompt": "walk", "duration_seconds": 4}
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:
        first = tool(client, "generate_motion", args)
        assert not first.get("isError"), first
        replay = tool(client, "generate_motion", args, user="user1-rotated")
        assert replay["structuredContent"]["replayed"]
        other = tool(client, "get_request_status", {"request_id": "job-once"}, user="user2")
        assert other["structuredContent"]["state"] == "not_found"
        denied = tool(client, "generate_motion", args, user="read-only")
        assert denied["isError"]
        assert not apis["read-only"].calls
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:
        assert tool(client, "generate_motion", args)["structuredContent"]["replayed"]
    assert len(apis["user1"].calls) == 1


def test_uploads_downloads_and_foreign_handles(tmp_path):
    apis = {}
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:
        response = client.post("/files", content=apng(), headers={**HEADERS, "X-Filename": "photo.png"})
        assert response.status_code == 201
        descriptor = response.json()
        path = "/files/inputs/" + descriptor["file_id"]
        assert client.get(path, headers=HEADERS).content == apng()
        assert client.get(path, headers={**HEADERS, "Authorization": "Bearer user2"}).status_code == 404
        assert client.get("/files/inputs/../requests.sqlite", headers=HEADERS).status_code == 404
        result = tool(
            client,
            "create_character_from_image",
            {"request_id": "image1", "input_file": descriptor, "name": "Pilot"},
            user="user2",
        )
        assert result["isError"]
        assert not apis["user2"].calls
        assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "https://169.254.169.254/latest/meta-data",
        "https://oaiusercontent.com.evil.test/file.png",
        "https://user:password@files.oaiusercontent.com/file.png",
    ],
)
async def test_untrusted_attachment_urls_rejected_without_fetch(tmp_path, url):
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="supported HTTPS attachment"):
        await files.resolve(InputFile(file_id="external", download_url=url, file_name="file.png"))


def test_anonymous_tool_metadata_and_linking_challenge(tmp_path):
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        tools = rpc(client, "tools/list", user="anonymous").json()["result"]["tools"]
        assert all(tool["securitySchemes"][0]["type"] == "oauth2" for tool in tools)
        upload = next(tool for tool in tools if tool["name"] == "upload_character")
        definition = upload["inputSchema"]["$defs"]["InputFile"]
        assert set(definition["properties"]) == {"file_id", "download_url", "file_name", "mime_type"}
        assert set(definition["required"]) == {"file_id", "download_url"}
        challenge = tool(client, "get_usage", {}, user="anonymous")
        assert challenge["isError"]
        assert "mcp/www_authenticate" in challenge["_meta"]


def test_owned_export_link_and_replay_does_not_regenerate(tmp_path):
    apis = {}
    args = {"request_id": "export-once", "motion_id": "motion1", "format": "glb"}
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:
        exported = tool(client, "download_motion", args)
        assert not exported.get("isError"), exported
        result = exported["structuredContent"]
        assert "local_path" not in result
        assert result["download_url"].startswith(ORIGIN + "/files/artifacts/")
        file_response = client.get(result["download_url"], headers=HEADERS)
        assert file_response.status_code == 200
        assert (
            client.get(result["download_url"], headers={**HEADERS, "Authorization": "Bearer user2"}).status_code == 404
        )
        replay = tool(client, "download_motion", args)["structuredContent"]
        assert replay["replayed"]
        assert replay["download_url"] == result["download_url"]
        assert sum(call[0] == "download" for call in apis["user1"].calls) == 1


async def test_attachment_import_is_cached_for_recovery_after_url_expiry(tmp_path, monkeypatch):
    calls = []
    original = httpx.AsyncClient

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=apng())

    def client(**kwargs):
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(hosted_files.httpx, "AsyncClient", client)
    monkeypatch.setattr(
        hosted_files.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    descriptor = InputFile(file_id="provider-file", download_url="https://files.oaiusercontent.com/opaque?sig=private")
    first = await files.resolve(descriptor)
    second = await files.resolve(
        InputFile(file_id="provider-file", download_url="https://files.oaiusercontent.com/opaque?expired=true")
    )
    assert first == second
    assert len(calls) == 1
    assert "authorization" not in calls[0].headers
    assert files.input_path(files.save(apng(), "same.png")["file_id"]).read_bytes() == apng()


def test_upload_content_and_storage_limits(tmp_path, monkeypatch):
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    for name in [
        "invalid.png",
        "invalid.glb",
        "invalid.fbx",
        "invalid.mp4",
        "invalid.webm",
        "invalid.gltf",
        "invalid.exe",
    ]:
        with pytest.raises(ValueError):
            files.save(b"not the named format", name)
    monkeypatch.setattr(hosted_files, "MAX_STORED_INPUT_BYTES", 1)
    with pytest.raises(ValueError, match="storage is full"):
        files.save(apng(), "image.png")


async def test_native_mcp_http_client_discovery_and_replay(tmp_path):
    apis = {}
    app = app_for(tmp_path, apis)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), headers={"Authorization": "Bearer user1"}
        ) as http:
            async with streamable_http_client(ORIGIN + "/mcp", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    assert len((await session.list_tools()).tools) == 24
                    args = {"request_id": "native-http-once", "prompt": "walk", "duration_seconds": 4}
                    first = await session.call_tool("generate_motion", args)
                    second = await session.call_tool("generate_motion", args)
                    assert not first.isError and second.structuredContent["replayed"]
    assert len(apis["user1"].calls) == 1


async def test_concurrent_duplicate_cannot_submit_twice(tmp_path):
    apis = {}
    started, release = asyncio.Event(), asyncio.Event()
    api = FakeAPI()
    original = api.generate

    async def generate(**kwargs):
        started.set()
        await release.wait()
        return await original(**kwargs)

    api.generate = generate
    apis["user1"] = api
    app = app_for(tmp_path, apis)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "generate_motion",
            "arguments": {"request_id": "concurrent", "prompt": "walk", "duration_seconds": 4},
        },
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers=HEADERS
        ) as client:
            first = asyncio.create_task(client.post("/mcp", json=payload))
            await asyncio.wait_for(started.wait(), 10)
            try:
                duplicate = await client.post("/mcp", json=payload)
                assert duplicate.json()["result"]["isError"]
                assert not api.calls
            finally:
                release.set()
                await first
    assert len(api.calls) == 1


def test_http_upload_generation_preview_edit_and_export_workflows(tmp_path):
    apis = {}
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:

        def call(name, arguments):
            result = tool(client, name, arguments)
            assert not result.get("isError"), (name, result)
            assert str(tmp_path) not in json.dumps(result)
            return result

        def upload(name, content):
            response = client.post("/files", content=content, headers={**HEADERS, "X-Filename": name})
            assert response.status_code == 201, response.text
            return response.json()

        image_bytes = io.BytesIO()
        Image.new("RGB", (64, 96), "orange").save(image_bytes, format="PNG")
        image = upload("pilot.png", image_bytes.getvalue())
        character = upload("pilot.fbx", b"Kaydara FBX Binary  \x00offline-fixture")
        video = upload("pilot.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20)
        edited = upload(
            "edited.gltf", json.dumps({"asset": {"version": "2.0"}, "animations": [{"name": "Fixture"}]}).encode()
        )
        call("upload_character", {"request_id": "upload", "input_file": character, "name": "Pilot"})
        call("create_character_from_image", {"request_id": "image", "input_file": image, "name": "Pilot"})
        call("generate_motion_from_video", {"request_id": "video", "input_file": video, "name": "Video"})
        call("generate_motion", {"request_id": "v3", "prompt": "walk"})
        call("generate_motion_v2", {"request_id": "v2", "prompt": "walk"})
        call("generate_locomotion", {"request_id": "locomotion"})
        for name, arguments in [
            ("get_job", {"job_id": "job1"}),
            ("get_motion", {"motion_id": "motion1"}),
            ("get_usage", {}),
            ("list_characters", {}),
            ("list_motions", {}),
            ("list_locomotion_styles", {}),
            ("estimate_model_cost", {"model": "text-to-motion-3.0", "quantity": 4}),
            ("check_download_allowed", {"motion_id": "motion1"}),
            ("get_request_status", {"request_id": "v3"}),
        ]:
            call(name, arguments)
        preview = call("get_preview", {"motion_id": "motion1"})["structuredContent"]
        call("get_preview_frame", {"artifact_id": preview["artifact_id"], "frame_index": 0})
        assert client.get(preview["download_url"], headers=HEADERS).status_code == 200
        call(
            "trim_motion",
            {"request_id": "trim", "motion_id": "motion1", "start_seconds": 0, "end_seconds": 2, "name": "Trim"},
        )
        call("create_looped_motion", {"request_id": "loop", "motion_id": "motion1"})
        call(
            "stitch",
            {
                "request_id": "stitch",
                "character_id": "mixamo1",
                "steps": [
                    {"motion_id": "motion1"},
                    {"motion_id": "motion2", "placement": {"forward_m": 2, "turn_degrees": 45}},
                ],
            },
        )
        call(
            "save_motion",
            {
                "request_id": "save",
                "input_file": edited,
                "source_motion_id": "motion1",
                "character_id": "mixamo1",
                "name": "Edited",
            },
        )
        call("preview_character_from_prompt", {"request_id": "candidates", "prompt": "a pilot"})
        call(
            "create_character_from_prompt",
            {"request_id": "chosen", "preview_request_id": "candidates", "preview_index": 0, "name": "Pilot"},
        )
        exported = call("download_motion", {"request_id": "export", "motion_id": "motion1"})["structuredContent"]
        assert client.get(exported["download_url"], headers=HEADERS).status_code == 200


async def test_disconnect_preserves_unknown_receipt_without_resubmission(tmp_path):
    started = asyncio.Event()
    api = FakeAPI()

    async def interrupted(**kwargs):
        api.calls.append(("generate", kwargs))
        started.set()
        await asyncio.Event().wait()

    api.generate = interrupted
    apis = {"user1": api}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "generate_motion", "arguments": {"request_id": "disconnect", "prompt": "walk"}},
    }
    app = app_for(tmp_path, apis)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, headers=HEADERS
        ) as client:
            pending = asyncio.create_task(client.post("/mcp", json=payload))
            await asyncio.wait_for(started.wait(), 10)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
    with TestClient(app_for(tmp_path, apis), base_url=ORIGIN) as client:
        status = tool(client, "get_request_status", {"request_id": "disconnect"})["structuredContent"]
        assert status["state"] == "unknown"
        assert tool(client, "generate_motion", payload["params"]["arguments"])["isError"]
    assert len(api.calls) == 1
