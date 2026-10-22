# Contributing

Development uses Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync --locked
uv run --locked bash ./test.sh
```

`test.sh` runs Ruff, Black, isort, Flake8, the offline pytest suite with coverage, and a package build. Coverage is measured for `uthana_mcp`, including subprocesses started by the tests, and must stay at or above 85 percent (`--cov-fail-under=85`). Platform-specific file and permission checks are exercised on their native operating systems in CI.

Live model calls are not part of this suite. They need an explicitly configured API key and spend account credits.

Do not commit API keys, `.env` files, or generated private state.
