# Install and connect

This guide targets Linux, macOS, and Windows with Claude Desktop, Cursor, or Codex. [Windows](#windows) lists the path and command differences. The MCP runs locally and calls Uthana using your account. Choose your preferred model in your coding host; no Uthana-specific model subscription is bundled.

## Install

### Recommended: platform installer

Download and run the appropriate installer. You can inspect the downloaded script before running it.

macOS / Linux:

```sh
curl -fsSL https://raw.githubusercontent.com/Uthana/uthana-mcp/main/install.sh -o install.sh
sh install.sh
```

Windows (PowerShell):

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Uthana/uthana-mcp/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The scripts reuse uv when available or download its [official installer](https://docs.astral.sh/uv/getting-started/installation/). They install the MCP for your user with Python 3.12, downloading Python if needed, and print the installed server command. No administrator access or preinstalled Python is required. They do not edit your shell profile or host configuration. Copy the printed server command into the host examples below and set `UTHANA_API_KEY` to the API key from your Uthana account settings.

### Manual installation

With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed:

```sh
uv tool install --python 3.12 uthana-mcp
```

Find the installed executable directory with `uv tool dir --bin` and use the absolute path to `uthana-mcp` (`uthana-mcp.exe` on Windows) in your host configuration. You can also run without a permanent install using `uvx --python 3.12 uthana-mcp`; configure `uvx` as the host command and `["--python", "3.12", "uthana-mcp"]` as its arguments.

Alternatively, with Python 3.11 or later already installed:

```sh
pip install uthana-mcp
```

Use the installed `uthana-mcp` executable as the host command with no arguments.

To develop from a checkout you need Git and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv sync --locked --no-dev
```

Keep that checkout and its `.venv` in a permanent location. Record the absolute path to `.venv/bin/uthana-mcp`; moving the checkout requires updating your host configuration.

## Select the API environment

Production (`uthana.com`) is the default. Override with `UTHANA_DOMAIN` and use the key issued for that environment.

The shared Python client constructs the HTTPS URLs from the hostname. Redirects and authentication failures never cause a fallback to another environment. Initialization and the workflow resource report the selected hostname.

Set `UTHANA_DOMAIN` in the coding host configuration, or in a checkout `.env` / `.env.local` (`.env.local` overrides `.env`; neither overrides variables the host already set). A `.env` in some other working directory is ignored. Never commit these files.

## Configure your API key

Create an API key in your [Uthana account settings](https://uthana.com). Set `UTHANA_API_KEY` to the key itself in the host configuration below. Use the key issued for the selected API environment. Keep configurations containing keys out of version control and do not paste keys into chats or issues.

## Connect a host

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "uthana": {
      "command": "/absolute/path/to/uthana-mcp",
      "args": [],
      "env": {
        "UTHANA_API_KEY": "your-api-key",
        "UTHANA_MCP_INPUT_DIR": "/absolute/path/to/selected-inputs"
      }
    }
  }
}
```

Cursor (`.cursor/mcp.json`) uses the same `mcpServers` object.

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.uthana]
command = "/absolute/path/to/uthana-mcp"
args = []

[mcp_servers.uthana.env]
UTHANA_API_KEY = "your-api-key"
UTHANA_MCP_INPUT_DIR = "/absolute/path/to/selected-inputs"
```

Use the absolute server command printed by the installer. Replace `your-api-key` with your API key and the input path with your own absolute path, then restart the host. The input directory is optional; omit `UTHANA_MCP_INPUT_DIR` if you do not need uploads.

For a checkout installation, use the absolute path to `.venv/bin/uthana-mcp` (Windows: `.venv\Scripts\uthana-mcp.exe`) as the command with no arguments.

### Environment settings and timeouts

| Variable | Purpose |
| --- | --- |
| `UTHANA_API_KEY` | API key value for the selected environment |
| `UTHANA_DOMAIN` | Defaults to `uthana.com` |
| `UTHANA_MCP_DATA_DIR` | Persistent private state. Defaults to `~/.local/state/uthana-mcp` |
| `UTHANA_MCP_INPUT_DIR` | Folder of files the server may upload. Uploads stay disabled when this is unset |

Tool discovery works without a key. Uthana operations use the account for the selected environment. Production operations spend that account's credits.

| Operation | Host tool timeout |
| --- | --- |
| Character upload, looping, stitching | At least 420 seconds |
| Character from an image or a chosen prompt preview | At least 1080 seconds |

Allow longer tool timeouts for slow transfers.

## Separate host connection

Use a second host entry if you need another API host. Set `UTHANA_DOMAIN` to that hostname and `UTHANA_API_KEY` to the key issued for that host. Give it its own data directory. Keep `uthana` for production. State explicitly which connection the agent should use; the server never switches between them automatically. Each environment uses its own account permissions and credits.

## First session

Restart the host and ask the agent to read `uthana://workflow`, confirm the selected environment, check account usage, and estimate a motion before generating it. Approve the estimate before making a paid request.

To verify the protocol independently, run `uvx --from uthana-mcp uthana-mcp-smoke` (or `uthana-mcp-smoke` for a direct installation). Add `--api-read` for one read-only account check after setting `UTHANA_API_KEY` in the shell environment; host configuration is not inherited by a separate shell command. A protocol check alone does not verify authentication.

Keep the private data directory across restarts: it contains request receipts and exports. Different credentials or environments use different scopes. Changing a key or deleting state does not establish that earlier work never happened. Follow the workflow's request recovery rules before resubmitting.

For uploads, add `UTHANA_MCP_INPUT_DIR` pointing to a dedicated local input folder. Uploads are disabled without it. Export and preview paths are on the machine running the connector. If a character upload is interrupted, inspect the account catalog before submitting it again. Stitching with sampled poses requires accurate host-sampled poses; this connector does not supply a sampler.

Production model usage consumes your Uthana account credits at the published prices. The connector adds no separate MCP fee; your coding host may bill separately. Tell the agent your spending limit. Use your own account; do not share another customer's key or state directory.

## Windows

The server runs natively on Windows. Follow the steps above with these differences:

- The server executable is `.venv\Scripts\uthana-mcp.exe`. Use it wherever this guide says `.venv/bin/uthana-mcp`. In TOML, write Windows paths with forward slashes or doubled backslashes.
- The default data directory is `%USERPROFILE%\.local\state\uthana-mcp`.
- In PowerShell, start Claude Code with the tool deadline as `$env:MCP_TOOL_TIMEOUT = "1200000"; claude`.

## Feedback

Include the release revision, OS, host/version, tool name, environment, and redacted error. Share request/job IDs privately when needed. Do not attach API keys, raw account balances, private assets, or the entire state directory.
