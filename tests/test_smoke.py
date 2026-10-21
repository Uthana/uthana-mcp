import os
import subprocess
import sys


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
