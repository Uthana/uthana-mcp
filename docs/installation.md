# Install and connect

This guide targets Linux, macOS, and Windows with Codex or Claude Code. [Windows](#windows) lists the path and command differences. The MCP runs locally and calls Uthana using your account. Choose your preferred model in your coding host; no Uthana-specific model subscription is bundled.

## Install

Use the [README installation and host configuration](../README.md#install) to get started. This guide covers private key setup, environment selection, and platform details.

To develop from a checkout you need Git and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv sync --locked --no-dev
```

Keep that checkout and its `.venv` in a permanent location. Record the absolute path to `.venv/bin/uthana-mcp`; moving the checkout requires updating your host configuration.

## Select the API environment

Production (`uthana.com`) is the default. Keep the explicit production setting in the examples so the intended account is visible. Override with `UTHANA_DOMAIN` and use the key issued for that environment.

The shared Python client constructs the HTTPS URLs from the hostname. Redirects and authentication failures never cause a fallback to another environment. Initialization and the workflow resource report the selected hostname.

Set `UTHANA_DOMAIN` in the coding host configuration, or in a checkout `.env` / `.env.local` (`.env.local` overrides `.env`; neither overrides variables the host already set). A `.env` in some other working directory is ignored. Never commit these files.

## Store your own API key

Use your normal uthana.com API key for production. A key for another host is different. Keep it in a private regular file outside the checkout, owned by you with permissions `600`. Set `UTHANA_API_KEY_FILE` to that file's absolute path. Do not also set `UTHANA_API_KEY`.

The following works from bash or zsh on Linux/macOS and asks for the key without echoing it. It creates a new file and will not overwrite an existing one:

```sh
uv run --no-sync python -c 'import getpass, os; from pathlib import Path; os.umask(0o077); p=Path.home()/".config/uthana/production-key"; p.parent.mkdir(parents=True, exist_ok=True, mode=0o700); key=getpass.getpass("Uthana production API key: ").strip(); assert key and not any(c.isspace() for c in key), "Enter one key"; p.open("x").write(key+"\n"); print("Saved private key file:", p)'
```

Never paste the key into a chat, GitHub issue, or shell command. For an existing file, use `chmod 600 /absolute/path/to/key` and confirm it is owned by your OS user. The MCP rejects symlinks, shared-readable files, directories, empty files, and conflicting key settings.

## Connect a host

Use the [README configuration examples](../README.md#connect) for Claude Desktop, Cursor, or Codex. Configure host tool timeouts of at least 420 seconds for upload, loop, and stitch, and 1080 seconds for character generation. Allow longer for slow transfers.

## Separate host connection

Use a second host entry if you need another API host. Set `UTHANA_DOMAIN` to that hostname and a different private key file. Give it its own data directory. Keep `uthana` for production. State explicitly which connection the agent should use; the server never switches between them automatically. Each environment uses its own account permissions and credits.

## First session

Follow the [first animation and export walkthrough](first-animation.md) to check account access, select a character, estimate costs, and generate and export a motion.

Keep the private data directory across restarts: it contains request receipts and exports. Different credentials or environments use different scopes. Changing a key or deleting state does not establish that earlier work never happened. Follow the workflow's request recovery rules before resubmitting.

For uploads, add `UTHANA_MCP_INPUT_DIR` pointing to a dedicated local input folder. Uploads are disabled without it. Export and preview paths are on the machine running the connector. If a character upload is interrupted, inspect the account catalog before submitting it again. Stitching with sampled poses requires accurate host-sampled poses; this connector does not supply a sampler.

Production model usage consumes your Uthana account credits at the published prices. The connector adds no separate MCP fee; your coding host may bill separately. Tell the agent your spending limit. Use your own account; do not share another customer's key or state directory.

## Windows

The server runs natively on Windows. Follow the steps above with these differences:

- The server executable is `.venv\Scripts\uthana-mcp.exe`. Use it wherever this guide says `.venv/bin/uthana-mcp`. In TOML, write Windows paths with forward slashes or doubled backslashes.
- The key file belongs in `%USERPROFILE%\.config\uthana\production-key`. The MCP accepts it only when you own it and its access list grants access to no one except you, `OWNER RIGHTS`, `SYSTEM`, and `Administrators`. Symlinks, junctions, and other reparse points are rejected.
- From PowerShell, create the key file with the same code passed through a here-string. With Python 3.12.4 or later, a newly created `%USERPROFILE%\.config\uthana` folder is owner-only, so the file it writes is accepted:

  ```powershell
  @'
  import getpass, os
  from pathlib import Path
  os.umask(0o077)
  p = Path.home() / ".config/uthana/production-key"
  p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
  key = getpass.getpass("Uthana production API key: ").strip()
  assert key and not any(c.isspace() for c in key), "Enter one key"
  p.open("x").write(key + "\n")
  print("Saved private key file:", p)
  '@ | uv run --no-sync python -
  ```

- For an existing file, or one in a folder that already existed, remove inherited entries and grant only yourself, then check the result:

  ```powershell
  icacls "$env:USERPROFILE\.config\uthana\production-key" /inheritance:r /grant:r "${env:USERNAME}:F"
  icacls "$env:USERPROFILE\.config\uthana\production-key"
  ```

  If any other user or group is still listed, remove it with `icacls <file> /remove:g <name>`.
- The default data directory is `%USERPROFILE%\.local\state\uthana-mcp`.
- In PowerShell, start Claude Code with the tool deadline as `$env:MCP_TOOL_TIMEOUT = "1200000"; claude`.

## Feedback

Include the release revision, OS, host/version, tool name, environment, and redacted error. Share request/job IDs privately when needed. Do not attach API keys, raw account balances, private assets, or the entire state directory.
