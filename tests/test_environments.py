import httpx
import pytest

from uthana_mcp.api import UthanaAPI
from uthana_mcp.config import Config
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.validation import TAR, UTHANA_DOMAIN


def test_default_is_production_and_config_captures_environment(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    monkeypatch.setenv("UTHANA_API_KEY", "private-test-key")
    original = Config.from_env()
    monkeypatch.setenv("UTHANA_DOMAIN", "other.example.com")
    monkeypatch.setenv("UTHANA_API_KEY", "changed")
    assert original.domain == UTHANA_DOMAIN
    assert original._key == "private-test-key"
    assert "private-test-key" not in repr(original)
    assert Config.from_env().domain == "other.example.com"


async def test_receipts_and_artifacts_are_isolated_by_environment_and_key(tmp_path):
    calls = []

    def respond(request):
        calls.append(request.url.host)
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    apis = [
        UthanaAPI(key, domain, transport=httpx.MockTransport(respond))
        for key, domain in [("key-a", "other.example.com"), ("key-a", UTHANA_DOMAIN), ("key-b", UTHANA_DOMAIN)]
    ]
    try:
        ops = [Operations(api, tmp_path) for api in apis]
        assert len({op.store.directory for op in ops}) == 3
        for op in ops:
            assert op.store.get_request("same-id")["state"] == "not_found"
            result = await op.generate("same-id", "Walk", 4, TAR)
            assert not result["replayed"]
            assert (await op.generate("same-id", "Walk", 4, TAR))["replayed"]
        assert calls == ["other.example.com", UTHANA_DOMAIN, UTHANA_DOMAIN]
        restarted = Operations(apis[1], tmp_path)
        assert (await restarted.generate("same-id", "Walk", 4, TAR))["replayed"]
        assert len(calls) == 3
    finally:
        for api in apis:
            await api.close()


@pytest.mark.parametrize("status", [401, 403, 302])
async def test_errors_never_fall_back_or_leak(status):
    hosts = []

    def respond(request):
        hosts.append(request.url.host)
        return httpx.Response(status, text="secret", headers={"location": "https://other.example.com/graphql"})

    api = UthanaAPI("fake", UTHANA_DOMAIN, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.generate("Walk", 4, TAR)
        assert hosts == [UTHANA_DOMAIN]
        assert "secret" not in str(exc.value)
        assert exc.value.outcome == ("rejected" if status in (401, 403) else "unknown")
    finally:
        await api.close()


async def test_discovery_without_key_and_configuration_stays_fixed(monkeypatch, tmp_path):
    from uthana_mcp.server import create_server

    monkeypatch.setenv("UTHANA_DOMAIN", UTHANA_DOMAIN)
    monkeypatch.setenv("UTHANA_API_KEY", "")
    server = create_server()
    monkeypatch.setenv("UTHANA_DOMAIN", "other.example.com")
    monkeypatch.setenv("UTHANA_API_KEY", "must-not-be-used")
    assert UTHANA_DOMAIN in server._mcp_server.instructions
    assert len(await server.list_tools()) == 24
    with pytest.raises(Exception, match="UTHANA_API_KEY"):
        await server._tool_manager.get_tool("get_usage").run({})


async def test_overridden_domain_routes_through_sdk_and_reports_origin(monkeypatch):
    from uthana_mcp.server import create_server

    seen = []
    domain = "other.example.com"

    def respond(request):
        seen.append((request.url.scheme, request.url.host))
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    production = UthanaAPI("fake", UTHANA_DOMAIN, transport=httpx.MockTransport(respond))
    try:
        assert api.scope != production.scope
        assert str(api.client.base_url) == f"https://{domain}"
        assert str(api.catalog_client.base_url) == f"https://{domain}"
        await api.generate("Walk", 4, TAR)
        assert seen == [("https", domain)]
        monkeypatch.setenv("UTHANA_DOMAIN", domain)
        monkeypatch.delenv("UTHANA_API_KEY", raising=False)
        server = create_server()
        assert domain in server._mcp_server.instructions
        assert len(await server.list_tools()) == 24
        result = await server.read_resource("uthana://workflow")
        assert domain in str(result)
    finally:
        await api.close()
        await production.close()


def test_dotenv_sets_domain_when_process_env_is_unset(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=other.example.com\n")
    assert Config.from_env().domain == "other.example.com"


def test_env_local_overrides_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=from-env.example.com\n")
    (tmp_path / ".env.local").write_text("UTHANA_DOMAIN=from-local.example.com\n")
    assert Config.from_env().domain == "from-local.example.com"


def test_process_env_wins_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path)
    monkeypatch.setenv("UTHANA_DOMAIN", UTHANA_DOMAIN)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=from-env.example.com\n")
    (tmp_path / ".env.local").write_text("UTHANA_DOMAIN=from-local.example.com\n")
    assert Config.from_env().domain == UTHANA_DOMAIN


def test_dotenv_in_unrelated_cwd_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path / "checkout")
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / "checkout").mkdir()
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=other.example.com\n")
    monkeypatch.chdir(tmp_path)
    assert Config.from_env().domain == UTHANA_DOMAIN
