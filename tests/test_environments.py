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


def test_default_stays_staging_and_settings_capture_environment(monkeypatch):
    monkeypatch.delenv("UTHANA_DOMAIN", raising=False)
    monkeypatch.setenv("UTHANA_API_KEY", "private-test-key")
    original = Settings.from_env()
    monkeypatch.setenv("UTHANA_DOMAIN", PRODUCTION)
    monkeypatch.setenv("UTHANA_API_KEY", "changed")
    assert original.domain == STAGING
    assert original.api_key() == "private-test-key"
    assert "private-test-key" not in repr(original)
    assert Settings.from_env().domain == PRODUCTION


@pytest.mark.parametrize(
    "domain", ["", "https://uthana.com", "uthana.com/", "uthana.com:443", "uthana.com.evil", "UTHANA.COM"]
)
def test_invalid_environment_rejected_before_network(monkeypatch, domain):
    monkeypatch.setenv("UTHANA_DOMAIN", domain)
    with pytest.raises(ValueError, match="UTHANA_DOMAIN"):
        Settings.from_env()
    with pytest.raises(ValueError, match="UTHANA_DOMAIN"):
        UthanaAPI("secret", domain)


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
async def test_production_support_reference_matches_selected_origin(link_domain, expected):
    def respond(request):
        assert request.url.host == PRODUCTION
        return httpx.Response(
            200,
            json={
                "data": {"create_character": None},
                "errors": [{"message": "private traceback", "link": f"https://{link_domain}/tb/{'a' * 12}"}],
            },
        )

    api = UthanaAPI("fake", PRODUCTION, transport=httpx.MockTransport(respond))
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
