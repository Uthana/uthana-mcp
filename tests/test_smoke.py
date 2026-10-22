import asyncio
import os
import subprocess
import sys

import pytest

from uthana_mcp.smoke import SmokeFailure, main, step


def test_protocol_smoke_without_credentials(tmp_path):
    env = os.environ.copy()
    env.pop("UTHANA_API_KEY", None)
    env.pop("UTHANA_API_KEY_FILE", None)
    result = subprocess.run(
        [sys.executable, "-m", "uthana_mcp.smoke", "--timeout", "10"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "protocol and workflow" in result.stdout


def test_api_read_requires_explicit_credential(tmp_path):
    env = os.environ.copy()
    env.pop("UTHANA_API_KEY", None)
    env.pop("UTHANA_API_KEY_FILE", None)
    result = subprocess.run(
        [sys.executable, "-m", "uthana_mcp.smoke", "--api-read"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "authentication configuration" in result.stderr


async def test_step_timeout_is_a_safe_category():
    async def hang():
        await asyncio.sleep(5)

    with pytest.raises(SmokeFailure, match="tool discovery"):
        await step("tool discovery", hang(), 0.01)


def test_main_rejects_timeout_outside_bounds(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-smoke", "--timeout", "0"])
    with pytest.raises(SystemExit):
        main()


def test_main_reports_only_the_failure_category(monkeypatch, capsys):
    async def fail(api_read, timeout):
        raise SmokeFailure("workflow resource")

    monkeypatch.setattr("uthana_mcp.smoke.check", fail)
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-smoke", "--api-read"])
    assert main() == 1
    error = capsys.readouterr().err
    assert "workflow resource" in error
    assert "Traceback" not in error


def test_main_hides_unexpected_exception_text(monkeypatch, capsys):
    async def fail(api_read, timeout):
        raise RuntimeError("secret-provider-detail")

    monkeypatch.setattr("uthana_mcp.smoke.check", fail)
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-smoke"])
    assert main() == 1
    error = capsys.readouterr().err
    assert "server startup or shutdown" in error
    assert "secret-provider-detail" not in error


def test_main_unwraps_a_grouped_smoke_failure(monkeypatch, capsys):
    async def fail(api_read, timeout):
        raise ExceptionGroup("wrapped", [SmokeFailure("account read")])

    monkeypatch.setattr("uthana_mcp.smoke.check", fail)
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-smoke"])
    assert main() == 1
    assert "account read" in capsys.readouterr().err


def test_main_success_mentions_account_read_when_requested(monkeypatch, capsys):
    async def ok(api_read, timeout):
        assert api_read is True

    monkeypatch.setattr("uthana_mcp.smoke.check", ok)
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-smoke", "--api-read"])
    assert main() == 0
    assert "account read" in capsys.readouterr().out
