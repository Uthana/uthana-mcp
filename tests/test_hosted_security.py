"""Adversarial tests for the public hosted adapter's trust boundaries."""

import asyncio
import socket

import httpx
import pytest
from fakes import FakeAPI, apng
from starlette.testclient import TestClient
from test_hosted import HEADERS, ORIGIN, app_for

import uthana_mcp.hosted_files as hosted_files
from uthana_mcp.hosted import _CURRENT, Files, HostedMCP, Identity, InputFile, Runtime, create_app
from uthana_mcp.operations import Operations


@pytest.mark.parametrize("path", ["/files", "/health", "/.well-known/oauth-protected-resource"])
def test_all_hosted_routes_reject_foreign_host(tmp_path, path):
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        response = client.get(path, headers={**HEADERS, "Host": "foreign.example"})
        assert response.status_code == 400


@pytest.mark.parametrize(
    "origin",
    [
        "https://@mcp.example.test",
        "https://mcp.example.test:bad",
        "https://mcp.example.test?",
        "https://mcp.example.test\\evil",
    ],
)
def test_ambiguous_hosted_origins_rejected(tmp_path, origin):
    with pytest.raises(ValueError, match="HTTPS origin"):
        create_app(
            origin=origin, directory=tmp_path, authenticate=None, api_factory=None, issuer="https://issuer.example.test"
        )


async def test_unannotated_tools_require_write_permission(tmp_path):
    operations = Operations(FakeAPI(), tmp_path)
    runtime = Runtime(Identity("reader", "org", frozenset({"mcp:read"})), operations, Files(operations, ORIGIN))
    server = HostedMCP()
    calls = []

    async def unclassified():
        calls.append(True)
        return "changed"

    server.add_tool(unclassified)
    token = _CURRENT.set(runtime)
    try:
        result = await server.call_tool("unclassified", {})
        assert not calls
        assert result.isError
        assert "mcp:write" in (await server.list_tools())[0].securitySchemes[0]["scopes"]
    finally:
        _CURRENT.reset(token)


async def test_attachment_connects_only_to_checked_address(tmp_path, monkeypatch):
    original = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "files.oaiusercontent.com"
        assert request.extensions["sni_hostname"] == "files.oaiusercontent.com"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=apng())

    monkeypatch.setattr(
        hosted_files.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(
        hosted_files.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    await files.resolve(InputFile(file_id="external", download_url="https://files.oaiusercontent.com/photo.png"))
    assert len(calls) == 1


def test_authenticated_responses_not_cacheable(tmp_path):
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        response = client.get("/files", headers=HEADERS)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize(
    "addresses",
    [
        [],
        ["127.0.0.1"],
        ["169.254.169.254"],
        ["10.0.0.1"],
        ["::1"],
        ["fe80::1"],
        ["::ffff:127.0.0.1"],
        ["93.184.216.34", "127.0.0.1"],
    ],
)
async def test_attachment_rejects_nonpublic_dns_without_connecting(tmp_path, monkeypatch, addresses):
    monkeypatch.setattr(
        hosted_files.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses],
    )

    def unexpected_client(**kwargs):
        pytest.fail("Private or mixed DNS responses must not reach the HTTP client")

    monkeypatch.setattr(hosted_files.httpx, "AsyncClient", unexpected_client)
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="public addresses"):
        await files.resolve(InputFile(file_id="external", download_url="https://files.oaiusercontent.com/photo.png"))


@pytest.mark.parametrize(
    "url",
    [
        "https://@files.oaiusercontent.com/a.png",
        "https://files.oaiusercontent.com:bad/a.png",
        "https://files.oaiusercontent.com:444/a.png",
        "https://files.oaiusercontent.com/a\nb.png",
        "https://files.oaiusercontent.com\\@127.0.0.1/a.png",
        "https://files.oaiusercontent.com.evil.example/a.png",
        "https://files.oaiusercontent.com%2f.evil.example/a.png",
    ],
)
async def test_ambiguous_attachment_urls_never_resolve_dns(tmp_path, monkeypatch, url):
    def unexpected_lookup(*args, **kwargs):
        pytest.fail("An invalid URL must be rejected before DNS lookup")

    monkeypatch.setattr(hosted_files.socket, "getaddrinfo", unexpected_lookup)
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="supported HTTPS attachment"):
        await files.resolve(InputFile(file_id="external", download_url=url))


@pytest.mark.parametrize("status", [302, 401, 500])
async def test_attachment_failures_do_not_follow_redirects_or_cache(tmp_path, monkeypatch, status):
    original = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://127.0.0.1/private"})

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(hosted_files.httpx, "AsyncClient", client)
    monkeypatch.setattr(
        hosted_files.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="download failed"):
        await files.resolve(InputFile(file_id="external", download_url="https://files.oaiusercontent.com/photo.png"))
    assert len(calls) == 1
    assert not list(files.directory.iterdir())


async def test_attachment_dns_failure_is_redacted(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("private resolver details")

    monkeypatch.setattr(hosted_files.socket, "getaddrinfo", fail)
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="could not be completed") as error:
        await files.resolve(
            InputFile(file_id="external", download_url="https://files.oaiusercontent.com/photo.png?secret=value")
        )
    assert "private resolver" not in str(error.value)
    assert "secret" not in str(error.value)


def test_issuer_with_path_remains_supported(tmp_path):
    app = create_app(
        origin=ORIGIN,
        directory=tmp_path,
        issuer="https://issuer.example.test/realm",
        authenticate=None,
        api_factory=None,
    )
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.get("/.well-known/oauth-protected-resource")
        assert response.json()["authorization_servers"] == ["https://issuer.example.test/realm"]


async def test_concurrency_limit_recovers_after_requests_complete(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def authenticate(request):
        return Identity("user", "org", frozenset({"mcp:read"}))

    async def api_factory(request, identity):
        nonlocal count
        count += 1
        if count == 4:
            started.set()
        await release.wait()
        return FakeAPI()

    app = create_app(
        origin=ORIGIN,
        directory=tmp_path,
        issuer="https://issuer.example.test",
        authenticate=authenticate,
        api_factory=api_factory,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            active = [asyncio.create_task(client.get("/files")) for _ in range(4)]
            try:
                await asyncio.wait_for(started.wait(), 5)
                assert (await client.get("/files")).status_code == 429
                assert count == 4
            finally:
                release.set()
                responses = await asyncio.gather(*active)
            assert all(response.status_code == 200 for response in responses)
            assert (await client.get("/files")).status_code == 200


def test_deep_anonymous_json_cannot_bypass_authentication(tmp_path):
    with TestClient(app_for(tmp_path, {}), base_url=ORIGIN) as client:
        response = client.post(
            "/mcp", headers={**HEADERS, "Authorization": "Bearer anonymous"}, content="[" * 2000 + "0" + "]" * 2000
        )
        assert response.status_code == 401


async def test_attachment_dns_deadline_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(hosted_files, "ATTACHMENT_TOTAL_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(hosted_files.socket, "getaddrinfo", lambda *args, **kwargs: [])
    files = Files(Operations(FakeAPI(), tmp_path), ORIGIN)
    with pytest.raises(ValueError, match="could not be completed"):
        await files.resolve(InputFile(file_id="external", download_url="https://files.oaiusercontent.com/photo.png"))
