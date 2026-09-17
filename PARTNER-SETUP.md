# Local partner beta setup

This guide targets Linux and macOS with Codex or Claude Code. macOS and native host acceptance are pending; see [beta acceptance](BETA-ACCEPTANCE.md). The MCP runs locally and calls Uthana using your account. Choose your preferred model in your coding host; no Uthana-specific model subscription is bundled.

## Install the supplied version

You need Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use the approved repository/package and exact release revision supplied with your invitation. An unmerged development branch is a review candidate, not a published release. Do not install from a moving branch or request access to internal development repositories just to follow this guide.

In the supplied checkout:

```sh
uv sync --locked --no-dev
```

The shared client is temporarily pinned to a Git commit. Git must be able to reach its public repository. Keep this checkout and its `.venv` in a permanent location. Record the absolute path to `.venv/bin/uthana-mcp`; moving the checkout requires updating your host configuration.

## Select the API environment

Production (`uthana.com`) is the default. Keep the explicit production setting in the examples so the intended account is visible. Staging users must set `UTHANA_DOMAIN=staging.uthana.com` before upgrading from a staging-default version. For an authorized developer box, set a single-label hostname such as `devbox.uthana.dev` and use the key issued for that environment.

The shared Python client constructs the HTTPS URLs. Schemes, ports, paths, other domains, and multi-label developer hosts are rejected. Redirects and authentication failures never cause a fallback to another environment. Initialization and the workflow resource report the selected hostname.

Pass environment variables through the coding host configuration. The connector does not automatically load a project `.env`; this avoids silently selecting settings from an unrelated working directory. A launcher may explicitly load a trusted private `.env` before starting the server. Never commit it.

## Store your own API key

Use your normal uthana.com API key for production. A staging key is different. Keep it in a private regular file outside the checkout, owned by you with permissions `600`. Set `UTHANA_API_KEY_FILE` to that file's absolute path. Do not also set `UTHANA_API_KEY`.

The following works from bash or zsh on Linux/macOS and asks for the key without echoing it. It creates a new file and will not overwrite an existing one:

```sh
uv run --no-sync python -c 'import getpass, os; from pathlib import Path; os.umask(0o077); p=Path.home()/".config/uthana/production-key"; p.parent.mkdir(parents=True, exist_ok=True, mode=0o700); key=getpass.getpass("Uthana production API key: ").strip(); assert key and not any(c.isspace() for c in key), "Enter one key"; p.open("x").write(key+"\n"); print("Saved private key file:", p)'
```

Never paste the key into a chat, GitHub issue, or shell command. For an existing file, use `chmod 600 /absolute/path/to/key` and confirm it is owned by your OS user. The MCP rejects symlinks, shared-readable files, directories, empty files, and conflicting key settings.

## Connect Codex

Merge the following entry into your personal `~/.codex/config.toml`; replace every `/absolute/path` value. Leave existing unrelated settings intact.

```toml
[mcp_servers.uthana]
command = "/absolute/path/to/uthana-mcp/.venv/bin/uthana-mcp"
tool_timeout_sec = 1200

[mcp_servers.uthana.env]
UTHANA_DOMAIN = "uthana.com"
UTHANA_API_KEY_FILE = "/absolute/path/to/private/production-key"
UTHANA_MCP_DATA_DIR = "/absolute/path/to/private/uthana-state"
```

Restart the connection and check that Uthana is available. Select Astra or another supported model in Codex. [Codex MCP configuration](https://developers.openai.com/codex/mcp/) documents local server configuration and tool timeouts.

## Connect Claude Code

Register a local server in your personal configuration (the values below are paths, not secrets):

```sh
claude mcp add --transport stdio --scope user \
  --env UTHANA_DOMAIN=uthana.com \
  --env UTHANA_API_KEY_FILE=/absolute/path/to/private/production-key \
  --env UTHANA_MCP_DATA_DIR=/absolute/path/to/private/uthana-state \
  uthana -- /absolute/path/to/uthana-mcp/.venv/bin/uthana-mcp
```

Quote path arguments if they contain spaces. Start the CLI with a 20-minute tool deadline:

```sh
MCP_TOOL_TIMEOUT=1200000 claude
```

Use `/mcp` to inspect the connection. This timeout is in milliseconds and belongs to the Claude Code process, not just the MCP server's environment. Configure your preferred model in Claude Code. See [Claude Code MCP](https://code.claude.com/docs/en/mcp) and [environment variables](https://code.claude.com/docs/en/env-vars). Desktop variants need their own timeout verification.

## Separate staging connection

Use a second host entry named `uthana-staging`, `UTHANA_DOMAIN=staging.uthana.com`, and a different private key file containing your staging key. Give it its own data directory for clarity. Keep `uthana` for production. State explicitly which connection the agent should use; the server never switches between them automatically. Each environment uses its own account permissions and credits.

## First session

Ask your agent:

> Read Uthana's workflow and confirm the active environment is uthana.com. Check account usage and list characters named Tar. Estimate a four-second V3 motion of a person walking forward and waving, and show me the estimate before generating it. After I approve, generate it once, track its job, inspect preview frames, trim a usable interval, and download a GLB with mesh at 30 FPS. Report the saved file path and any limitations you observe.

Use the returned character ID explicitly when possible. Tar is the shared client's default, but account access must be checked. Initialization identifies the selected environment; it does not prove authentication succeeded. A successful account read establishes that separately.

Keep the private data directory across restarts: it contains request receipts and exports. Different credentials or environments use different scopes. Changing a key or deleting state does not establish that earlier work never happened. Follow the workflow's request recovery rules before resubmitting.

For uploads, add `UTHANA_MCP_INPUT_DIR` pointing to a dedicated local input folder. Uploads are disabled without it. Export and preview paths are on the machine running the connector. Character upload has a known unresolved upstream failure on a tested fixture; image, loop, and stitch operations remain experimental. Stitching additionally requires accurate host-sampled poses; this connector does not supply a sampler.

Production model usage consumes your Uthana account credits at the published prices. The connector adds no separate MCP fee; your coding host may bill separately. Tell the agent your spending limit. Use your own account; do not share another customer's key or state directory.

## Feedback

Include the release revision, OS, host/version, tool name, environment, and redacted error/support reference. Share request/job IDs privately when needed. Do not attach API keys, raw account balances, private assets, or the entire state directory.
