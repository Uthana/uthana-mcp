# Contributing

Development uses Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync --locked
uv run --locked bash ./test.sh
```

`test.sh` runs Ruff, Black, isort, Flake8, the offline pytest suite with coverage, and a package build. Coverage is measured for `uthana_mcp`, including subprocesses started by the tests, and must stay at or above 85 percent (`--cov-fail-under=85`). Platform-specific file and permission checks are exercised on their native operating systems in CI.

Live model calls are not part of this suite. They need an explicitly configured API key and spend account credits.

Do not commit API keys, `.env` files, or generated private state.

## Releasing

Like the Uthana Python client, releases start with a version bump in a PR. Use `uv version --no-sync 0.1.1` to update `pyproject.toml` and `uv.lock`, then commit both. This uses uv's built-in command instead of a separate version script.

On merge to `main`, `.github/workflows/release.yml` checks whether that version exists on PyPI, runs verification, builds a fresh sdist and wheel, publishes through PyPI Trusted Publishing (OIDC), and creates `vX.Y.Z` plus a GitHub release. Configure the trusted publisher for **uthana-mcp**, repository **Uthana/uthana-mcp**, workflow **release.yml**. An already-published version is skipped; a failed PyPI lookup stops the release.

The workflow also supports a manual run with `dry_run=true` (the default). A real manual publication creates the tag and GitHub release as well. Publish the required Uthana client and remove its temporary `[tool.uv.sources]` pin before any release build.

For a local package dry run:

```sh
uv build --clear
uv publish --check-url https://pypi.org/simple/ --dry-run
```

The clean build prevents old versions in `dist/` from being uploaded. Authorized local publication uses the same command without `--dry-run` and an API token supplied through `UV_PUBLISH_TOKEN`; GitHub publication uses OIDC instead.
