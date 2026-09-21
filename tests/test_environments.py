import json
import os

import httpx
import pytest

from uthana_mcp.api import UthanaAPI
from uthana_mcp.config import Config
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.validation import PRODUCTION, TAR


def config(path=None, key=""):
    return Config(PRODUCTION, "/unused", None, key, str(path) if path else None)


def test_default_is_production_and_config_captures_environment(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    monkeypatch.setenv("UTHANA_API_KEY", "private-test-key")
    original = Config.from_env()
    monkeypatch.setenv("UTHANA_DOMAIN", "other.example.com")
    monkeypatch.setenv("UTHANA_API_KEY", "changed")
    assert original.domain == PRODUCTION
    assert original.api_key() == "private-test-key"
    assert "private-test-key" not in repr(original)
    assert Config.from_env().domain == "other.example.com"


def test_private_key_file_and_ambiguous_configuration(tmp_path):
    path = tmp_path / "key"
    path.write_text("private-test-key\n")
    path.chmod(0o600)
    assert config(path).api_key() == "private-test-key"
    with pytest.raises(ValueError, match="only one"):
        config(path, "other-key").api_key()


@pytest.mark.parametrize(
    "kind", ["missing", "directory", "symlink", "public", "fifo", "empty", "large", "binary", "multiline", "owner"]
)
def test_invalid_key_files_are_redacted_and_do_not_block(tmp_path, monkeypatch, kind):
    path = tmp_path / "private-filename"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = tmp_path / "target"
        target.write_text("secret")
        target.chmod(0o600)
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    elif kind != "missing":
        content = {"empty": b"", "large": b"x" * 8193, "binary": b"\xff", "multiline": b"key1\nkey2"}.get(
            kind, b"secret"
        )
        path.write_bytes(content)
        path.chmod(0o644 if kind == "public" else 0o600)
        if kind == "owner":
            monkeypatch.setattr(os, "geteuid", lambda: path.stat().st_uid + 1)
    with pytest.raises(ValueError) as exc:
        config(path).api_key()
    message = str(exc.value)
    assert "UTHANA_API_KEY_FILE" in message
    assert "private-filename" not in message and "Errno" not in message and "secret" not in message


async def test_receipts_and_artifacts_are_isolated_by_environment_and_key(tmp_path):
    calls = []

    def respond(request):
        calls.append(request.url.host)
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    apis = [
        UthanaAPI(key, domain, transport=httpx.MockTransport(respond))
        for key, domain in [("key-a", "other.example.com"), ("key-a", PRODUCTION), ("key-b", PRODUCTION)]
    ]
    try:
        ops = [Operations(api, tmp_path) for api in apis]
        assert len({op.store.directory for op in ops}) == 3
        for op in ops:
            assert op.store.get_request("same-id")["state"] == "not_found"
            result = await op.generate("same-id", "Walk", 4, TAR)
            assert not result["replayed"]
            assert (await op.generate("same-id", "Walk", 4, TAR))["replayed"]
        assert calls == ["other.example.com", PRODUCTION, PRODUCTION]
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

    api = UthanaAPI("fake", PRODUCTION, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.generate("Walk", 4, TAR)
        assert hosts == [PRODUCTION]
        assert "secret" not in str(exc.value)
        assert exc.value.outcome == ("rejected" if status in (401, 403) else "unknown")
    finally:
        await api.close()


async def test_upload_errors_do_not_forward_traceback_links():
    def respond(request):
        return httpx.Response(
            200,
            json={
                "data": {"create_character": None},
                "errors": [
                    {
                        "message": "private traceback",
                        "link": f"https://{PRODUCTION}/tb/{'a' * 12}",
                    }
                ],
            },
        )

    api = UthanaAPI("fake", PRODUCTION, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.upload_character("rig.glb", b"fixture", "Rig", False)
        details = json.dumps(exc.value.details())
        assert "support_reference" not in details
        assert "/tb/" not in details
        assert "private traceback" not in details
    finally:
        await api.close()


async def test_key_file_not_read_for_discovery_and_configuration_stays_fixed(monkeypatch, tmp_path):
    from uthana_mcp.server import create_server

    monkeypatch.setenv("UTHANA_DOMAIN", PRODUCTION)
    monkeypatch.setenv("UTHANA_API_KEY", "")
    monkeypatch.setenv("UTHANA_API_KEY_FILE", str(tmp_path / "missing"))
    server = create_server()
    monkeypatch.setenv("UTHANA_DOMAIN", "other.example.com")
    monkeypatch.setenv("UTHANA_API_KEY", "must-not-be-used")
    assert PRODUCTION in server._mcp_server.instructions
    assert len(await server.list_tools()) == 22
    with pytest.raises(Exception, match="UTHANA_API_KEY_FILE"):
        await server._tool_manager.get_tool("get_usage").run({})


async def test_overridden_domain_routes_through_sdk_and_reports_origin(monkeypatch):
    from uthana_mcp.server import create_server

    seen = []
    domain = "other.example.com"

    def respond(request):
        seen.append((request.url.scheme, request.url.host))
        return httpx.Response(200, json={"data": {"create_text_to_motion_job": {"job": {"id": "job1"}}}})

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    production = UthanaAPI("fake", PRODUCTION, transport=httpx.MockTransport(respond))
    try:
        assert api.scope != production.scope
        assert str(api.client.base_url) == f"https://{domain}"
        assert str(api.catalog_client.base_url) == f"https://{domain}"
        await api.generate("Walk", 4, TAR)
        assert seen == [("https", domain)]
        monkeypatch.setenv("UTHANA_DOMAIN", domain)
        monkeypatch.delenv("UTHANA_API_KEY", raising=False)
        monkeypatch.delenv("UTHANA_API_KEY_FILE", raising=False)
        server = create_server()
        assert domain in server._mcp_server.instructions
        assert len(await server.list_tools()) == 22
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
    monkeypatch.setenv("UTHANA_DOMAIN", PRODUCTION)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=from-env.example.com\n")
    (tmp_path / ".env.local").write_text("UTHANA_DOMAIN=from-local.example.com\n")
    assert Config.from_env().domain == PRODUCTION


def test_dotenv_in_unrelated_cwd_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.git_root", lambda: tmp_path / "checkout")
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / "checkout").mkdir()
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=other.example.com\n")
    monkeypatch.chdir(tmp_path)
    assert Config.from_env().domain == PRODUCTION
