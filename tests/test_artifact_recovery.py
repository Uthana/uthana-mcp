import json
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import FakeAPI
from platform_support import mkfifo_or_skip

from uthana_mcp import artifact_io
from uthana_mcp.artifact_io import MAX_ARTIFACT_BYTES
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server


async def test_request_status_recovers_intact_export_without_upstream_calls(tmp_path):
    api = FakeAPI()
    ops = Operations(api, tmp_path / "state")
    original = await ops.download("export1", "motion1")
    before = list(api.calls)
    tool = create_server(ops)._tool_manager.get_tool("get_request_status")
    status = await tool.run({"request_id": "export1"})
    assert status["state"] == "complete"
    assert status["artifact_status"] == "verified_local_bytes"
    assert status["result"]["motion_id"] == "motion1"
    assert status["result"]["artifact_id"] == original["artifact_id"]
    assert status["result"]["replayed"] is True
    assert api.calls == before


@pytest.mark.parametrize("replacement", ["fifo", "oversized"])
async def test_request_status_reports_replaced_artifact_and_retains_ids_promptly(tmp_path, replacement):
    api = FakeAPI()
    state_directory = tmp_path / "state"
    ops = Operations(api, state_directory)
    original = await ops.download("export1", "motion1")
    path = Path(original["local_path"])
    path.unlink()
    if replacement == "fifo":
        mkfifo_or_skip(path)
    else:
        with path.open("wb") as stream:
            stream.truncate(MAX_ARTIFACT_BYTES + 1)

    # Exercise the actual tool and persisted receipt after a fresh process starts.
    # If recovery regresses to a blocking FIFO read, the parent kills this child.
    script = """
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server
class NoUpstream:
    scope = sys.argv[3]
    def __getattr__(self, name):
        raise AssertionError("Recovery attempted upstream access")
async def main():
    operations = Operations(NoUpstream(), Path(sys.argv[2]))
    tool = create_server(operations)._tool_manager.get_tool("get_request_status")
    print(json.dumps(await tool.run({"request_id": "export1"})))
asyncio.run(main())
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(Path(artifact_io.__file__).parents[1]),
            str(state_directory),
            api.scope,
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["state"] == "complete"
    assert status["artifact_status"] == "unavailable_or_changed"
    assert status["result"]["motion_id"] == "motion1"
    assert status["result"]["artifact_id"] == original["artifact_id"]
    assert status["result"]["character_id"] == original["character_id"]
    assert status["result"]["replayed"] is True
    assert "no replacement was downloaded" in status["next_action"]
    assert len(api.calls) == 1
