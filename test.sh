#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
MCP_PYTHON="${MCP_PYTHON:-python3}"

# Test this checkout, including the package used by stdio child processes.
export PYTHONPATH="$PWD/src"

"$MCP_PYTHON" -m ruff check src tests
"$MCP_PYTHON" -m black --check --line-length=120 src tests
"$MCP_PYTHON" -m isort --check-only --profile=black --line-length=120 src tests
"$MCP_PYTHON" -m flake8 src tests
"$MCP_PYTHON" -m pytest tests -q --cov=uthana_mcp --cov-report=term-missing --cov-fail-under=90 "$@"
"$MCP_PYTHON" -m build --no-isolation
