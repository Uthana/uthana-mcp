# Release checklist

Use this for every PyPI release and every hosted deployment that changes the connector. The goal is that a visitor arriving from PyPI, GitHub, the website, or the API docs gets the same recommended route, sign-in requirements, and status.

Roles: the **release owner** is the engineer who opens the version-bump PR. The **website owner** maintains the uthana.com marketing pages. The **hosted owner** updates the hosted deployment pin in the Uthana service repository. One person can hold several roles.

## Before merging the version bump (release owner)

- [ ] Run `uv version --no-sync X.Y.Z` and commit `pyproject.toml` and `uv.lock`.
- [ ] Update every `https://github.com/Uthana/uthana-mcp/blob/vX.Y.Z/` link in `README.md` and `[project.urls]` to the new version. `tests/test_package_metadata.py` fails if a README link is relative or points at another release.
- [ ] Remove any temporary `[tool.uv.sources]` client pin (the release workflow also refuses it).
- [ ] Confirm the README's "Status and versions" section, tool table, and hosted-only tools match this release, and that `docs/api-coverage.md` states the local and hosted tool counts.
- [ ] Confirm no file shipped in the package description calls the hosted service a preview or local-only.

## After the release workflow finishes (release owner)

- [ ] `https://pypi.org/project/uthana-mcp/` shows the new version and the new description.
- [ ] From the PyPI page, open every link in the description and the sidebar ("Documentation", "Hosted MCP reference", "Local installation", "API documentation", "Repository", "Issues", "Changelog"). Each opens the intended page; none returns 404. The `vX.Y.Z` tag links resolve once the workflow has pushed the tag.
- [ ] The GitHub release `vX.Y.Z` exists and its notes summarize user-facing changes.
- [ ] On a clean machine or fresh shell, the installer installs the new version, `uv tool list` shows it, and `uthana-mcp-smoke` passes. The smoke check proves installation and protocol only, not account access.

## When the hosted deployment changes (hosted owner)

- [ ] After a hosted dependency refresh, list the running tools and compare them with the release documentation; document any hosted-only or local-only tools.
- [ ] `https://mcp.uthana.com/` redirects to `https://uthana.com/mcp`, and `https://mcp.uthana.com/files` opens the Uthana sign-in.
- [ ] The hosted MCP reference (`https://uthana.com/docs/api/capabilities/hosted-mcp`) matches the deployed behavior.

## Public pages (website owner, after any change to status, routes, sign-in, or tools)

- [ ] `https://uthana.com/mcp`, `https://uthana.com/mcp/setup`, and `https://uthana.com/developers` agree with the README on: hosted is the recommended production route with account sign-in and no API key; local is supported with an API key; and any hosted-only tools.
- [ ] Links from those pages to GitHub docs resolve.

## Record

Add a note to the release's tracking issue or PR with the date, the released version, the hosted package version, and the URLs checked.
