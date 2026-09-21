"""Real MCP server process with an offline provider. Never reads API credentials."""

import sys
from pathlib import Path

from fakes import FakeAPI

from uthana_mcp.operations import Operations
from uthana_mcp.server import create_server

if __name__ == "__main__":
    directory = Path(sys.argv[1])
    create_server(Operations(FakeAPI(), directory / "state", directory / "inputs")).run(transport="stdio")
