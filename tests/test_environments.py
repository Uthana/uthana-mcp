import json
import os

import httpx
import pytest

from uthana_mcp.api import UthanaAPI
from uthana_mcp.config import Settings
from uthana_mcp.errors import APIError
from uthana_mcp.operations import Operations
from uthana_mcp.validation import PRODUCTION, STAGING, TAR


def settings(path=None, key=""):
    return Settings(PRODUCTION, "/unused", None, key, str(path) if path else None)


def test_default_is_production_and_settings_capture_environment(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.checkout_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    monkeypatch.setenv("UTHANA_API_KEY", "private-test-key")
    original = Settings.from_env()
    monkeypatch.setenv("UTHANA_DOMAIN", STAGING)
    monkeypatch.setenv("UTHANA_API_KEY", "changed")
    assert original.domain == PRODUCTION
    assert original.api_key() == "private-test-key"
    assert "private-test-key" not in repr(original)
    assert Settings.from_env().domain == STAGING


@pytest.mark.parametrize(
    "domain",
    ["", "https://uthana.com", "uthana.com/", "uthana.com:443", "user@uthana.com", "uthana.com?x=1", "uthana.com#frag"],
)
def test_malformed_environment_rejected_before_network(monkeypatch, domain):
    monkeypatch.setenv("UTHANA_DOMAIN", domain)
    with pytest.raises(ValueError, match="UTHANA_DOMAIN"):
        Settings.from_env()
    with pytest.raises(ValueError, match="UTHANA_DOMAIN"):
        UthanaAPI("secret", domain)


@pytest.mark.parametrize("domain", ["uthana.com.evil", "example.com", "UTHANA.COM", "localhost", "127.0.0.1"])
async def test_arbitrary_hostnames_are_accepted(domain):
    api = UthanaAPI("secret", domain)
    try:
        assert api.domain == domain
        assert str(api.client.base_url) == f"https://{domain}"
    finally:
        await api.close()


def test_private_key_file_and_ambiguous_configuration(tmp_path):
    path = tmp_path / "key"
    path.write_text("private-test-key\n")
    path.chmod(0o600)
    assert settings(path).api_key() == "private-test-key"
    with pytest.raises(ValueError, match="only one"):
        settings(path, "other-key").api_key()


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
        settings(path).api_key()
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
        for key, domain in [("key-a", STAGING), ("key-a", PRODUCTION), ("key-b", PRODUCTION)]
    ]
    try:
        ops = [Operations(api, tmp_path) for api in apis]
        assert len({op.store.directory for op in ops}) == 3
        for op in ops:
            assert op.store.get_request("same-id")["state"] == "not_found"
            result = await op.generate("same-id", "Walk", 4, TAR)
            assert not result["replayed"]
            assert (await op.generate("same-id", "Walk", 4, TAR))["replayed"]
        assert calls == [STAGING, PRODUCTION, PRODUCTION]
        # A restarted process recovers its own receipt without another provider call.
        restarted = Operations(apis[1], tmp_path)
        assert (await restarted.generate("same-id", "Walk", 4, TAR))["replayed"]
        assert len(calls) == 3
    finally:
        for api in apis:
            await api.close()


@pytest.mark.parametrize("status", [401, 403, 302])
async def test_production_errors_never_fall_back_or_leak(status):
    hosts = []

    def respond(request):
        hosts.append(request.url.host)
        return httpx.Response(status, text="secret", headers={"location": "https://staging.uthana.com/graphql"})

    api = UthanaAPI("fake", PRODUCTION, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.generate("Walk", 4, TAR)
        assert hosts == [PRODUCTION]
        assert "secret" not in str(exc.value) and "staging" not in str(exc.value)
        assert exc.value.outcome == ("rejected" if status in (401, 403) else "unknown")
    finally:
        await api.close()


@pytest.mark.parametrize("link_domain,expected", [(PRODUCTION, "a" * 12), (STAGING, None), ("uthana.com.evil", None)])
@pytest.mark.parametrize("domain", [PRODUCTION, "devbox.uthana.dev"])
async def test_support_reference_matches_selected_origin(link_domain, expected, domain):
    def respond(request):
        assert request.url.host == domain
        return httpx.Response(
            200,
            json={
                "data": {"create_character": None},
                "errors": [
                    {
                        "message": "private traceback",
                        "link": f"https://{domain if link_domain == PRODUCTION else link_domain}/tb/{'a' * 12}",
                    }
                ],
            },
        )

    api = UthanaAPI("fake", domain, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError) as exc:
            await api.upload_character("rig.glb", b"fixture", "Rig", False)
        assert exc.value.support_reference == expected
        assert "private traceback" not in json.dumps(exc.value.details())
    finally:
        await api.close()


async def test_key_file_not_read_for_discovery_and_configuration_stays_fixed(monkeypatch, tmp_path):
    from uthana_mcp.server import create_server

    monkeypatch.setenv("UTHANA_DOMAIN", PRODUCTION)
    monkeypatch.setenv("UTHANA_API_KEY", "")
    monkeypatch.setenv("UTHANA_API_KEY_FILE", str(tmp_path / "missing"))
    server = create_server()
    monkeypatch.setenv("UTHANA_DOMAIN", STAGING)
    monkeypatch.setenv("UTHANA_API_KEY", "must-not-be-used")
    assert PRODUCTION in server._mcp_server.instructions
    # Discovery does not read the nonexistent key file.
    assert len(await server.list_tools()) == 22
    with pytest.raises(Exception, match="UTHANA_API_KEY_FILE"):
        await server._tool_manager.get_tool("get_usage").run({})


@pytest.mark.parametrize("domain", ["devbox.uthana.dev", "test-2.uthana.dev"])
async def test_developer_environment_routes_through_sdk_and_reports_origin(monkeypatch, tmp_path, domain):
    from uthana_mcp.server import create_server

    seen = []

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


@pytest.mark.parametrize(
    "domain",
    [
        "devbox.uthana.dev:443",
        "devbox.uthana.dev/path",
        "user@devbox.uthana.dev",
        "devbox.uthana.dev?x=y",
        "-dev.uthana.dev",
        "dev-.uthana.dev",
        "https://devbox.uthana.dev",
        "x" * 64 + ".uthana.dev",
        "dev_box.uthana.dev",
        "devbox.uthana.dev\n",
        None,
        [],
    ],
)
def test_malformed_hostname_rejected(domain):
    with pytest.raises(ValueError, match="UTHANA_DOMAIN"):
        UthanaAPI("secret", domain)


@pytest.mark.parametrize("status", [401, 403, 302, 307])
async def test_developer_errors_do_not_redirect_credentials_or_fall_back(status):
    seen = []

    def respond(request):
        seen.append(request.url.host)
        return httpx.Response(status, text="private", headers={"location": "https://uthana.com/graphql"})

    api = UthanaAPI("secret", "devbox.uthana.dev", transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(APIError):
            await api.generate("Walk", 4, TAR)
        assert seen == ["devbox.uthana.dev"]
    finally:
        await api.close()


def test_checkout_dotenv_sets_domain_when_process_env_is_unset(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.checkout_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=staging.uthana.com\n")
    assert Settings.from_env().domain == STAGING


def test_env_local_overrides_env_file(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.checkout_root", lambda: tmp_path)
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=staging.uthana.com\n")
    (tmp_path / ".env.local").write_text("UTHANA_DOMAIN=devbox.uthana.dev\n")
    assert Settings.from_env().domain == "devbox.uthana.dev"


def test_process_env_wins_over_checkout_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.checkout_root", lambda: tmp_path)
    monkeypatch.setenv("UTHANA_DOMAIN", PRODUCTION)
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=staging.uthana.com\n")
    (tmp_path / ".env.local").write_text("UTHANA_DOMAIN=devbox.uthana.dev\n")
    assert Settings.from_env().domain == PRODUCTION


def test_dotenv_in_unrelated_cwd_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr("uthana_mcp.config.checkout_root", lambda: tmp_path / "checkout")
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    (tmp_path / "checkout").mkdir()
    (tmp_path / ".env").write_text("UTHANA_DOMAIN=staging.uthana.com\n")
    monkeypatch.chdir(tmp_path)
    assert Settings.from_env().domain == PRODUCTION
