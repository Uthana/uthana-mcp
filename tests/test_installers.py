"""Exercise installer orchestration without downloads, credentials, or real installs."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("fail_install", [False, True])
def test_native_installer(tmp_path, fail_install):
    bin_dir = tmp_path / "tool bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.jsonl"
    fake = tmp_path / "fake.py"
    fake.write_text(
        "import json, os, sys\n"
        "with open(os.environ['MCP_INSTALL_TEST_CALLS'], 'a') as out:\n"
        "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:] == ['tool', 'dir', '--bin']:\n"
        "    print(os.environ['MCP_INSTALL_TEST_BIN'])\n"
        "if sys.argv[1:3] == ['tool', 'install'] and os.environ['MCP_INSTALL_TEST_FAIL'] == '1':\n"
        "    sys.exit(2)\n"
    )
    env = dict(os.environ)
    env.update(
        MCP_INSTALL_TEST_CALLS=str(calls),
        MCP_INSTALL_TEST_BIN=str(bin_dir),
        MCP_INSTALL_TEST_FAIL=str(int(fail_install)),
    )
    if os.name == "nt":
        shell = shutil.which("powershell.exe") or shutil.which("pwsh")
        assert shell, "Windows installer tests require PowerShell"
        (bin_dir / "uv.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n')
        wrapper = tmp_path / "run.ps1"
        quoted_bin = str(bin_dir).replace("'", "''")
        quoted_installer = str(ROOT / "install.ps1").replace("'", "''")
        wrapper.write_text(f"$env:PATH = '{quoted_bin};' + $env:PATH\n" f"& '{quoted_installer}'\n")
        command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)]
    else:
        for name in ("uv",):
            path = bin_dir / name
            path.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(fake))} "$@"\n')
            path.chmod(0o755)
        env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
        command = ["sh", str(ROOT / "install.sh")]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    recorded = [json.loads(line) for line in calls.read_text().splitlines()]
    assert ["tool", "install", "--python", "3.12", "uthana-mcp"] in recorded
    if fail_install:
        assert result.returncode != 0
        assert ["tool", "dir", "--bin"] not in recorded
    else:
        assert result.returncode == 0, result.stderr
        assert ["tool", "dir", "--bin"] in recorded
        assert "UTHANA_API_KEY" in result.stdout
        assert str(bin_dir) in result.stdout
