# Uthana MCP

[![PyPI version](https://badge.fury.io/py/uthana-mcp.svg)](https://badge.fury.io/py/uthana-mcp)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

Local [MCP](https://modelcontextprotocol.io) server for [Uthana](https://uthana.com): generate motion from text or video, create characters from prompts, images, or rigged files, trim, loop, and stitch motions, and export retargeted animation.

The host supplies the reasoning model. This server uses the shared [Uthana Python client](https://github.com/Uthana/uthana-python-client) and speaks stdio. It registers 25 tools and the `uthana://workflow` resource.

📖 [API documentation](https://uthana.com/docs/api) · [First animation](docs/first-animation.md)

## Install

Python 3.11 or later.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) to let your MCP host run `uvx uthana-mcp` automatically. Alternatively, install with `pip install uthana-mcp` and configure the host command as `uthana-mcp` with no arguments.

Create an API key at [uthana.com](https://uthana.com) under account settings. Prefer a private key file over putting the key in a config file:

Run the setup command and paste the key at its hidden prompt (Linux, macOS, or Windows):

```sh
uvx --from uthana-mcp uthana-mcp-setup
```

Use the printed key-file path in the configuration below. See the [installation guide](docs/installation.md) for key creation commands, Windows permissions, environment settings, and tool timeouts.

## Connect

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "uthana": {
      "command": "uvx",
      "args": ["uthana-mcp"],
      "env": {
        "UTHANA_API_KEY_FILE": "/absolute/path/to/private-api-key",
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
command = "uvx"
args = ["uthana-mcp"]

[mcp_servers.uthana.env]
UTHANA_API_KEY_FILE = "/absolute/path/to/private-api-key"
UTHANA_MCP_INPUT_DIR = "/absolute/path/to/selected-inputs"
```

On Windows the key file lives under `%USERPROFILE%\.config\uthana\` and must stay private to your user. [Install and connect](docs/installation.md) has the Windows commands and host timeout settings.

Restart your host, then ask it to read Uthana’s workflow, check account access, and estimate a motion before generating it. Production generation spends your account’s credits. Continue with the [first-animation walkthrough](docs/first-animation.md) for upload, generation, and export.

## Tools

| Tool | What it does |
| --- | --- |
| `generate_motion` | Text-to-motion V3. Returns a job ID |
| `generate_motion_v2` | Text-to-motion V2. Returns a motion ID |
| `generate_locomotion` | Walk or run cycles from style, strides, speed, and direction |
| `list_locomotion_styles` | Available locomotion styles |
| `estimate_model_cost` | USD estimate from current model rates |
| `get_job` | Generation job state and available motion ID |
| `get_motion` | Native motion metadata and source-file identity |
| `get_request_status` | Local request state, result IDs, and recovery guidance |
| `trim_motion` | Save an interval as a new motion |
| `get_preview` | APNG or WebM preview |
| `get_preview_frame` | One APNG frame with index and available timing |
| `generate_motion_from_video` | Video-to-motion (V2M) 2.0 or 2.1 job |
| `upload_character` | FBX/GLB upload, with optional auto-rig and rerig options |
| `create_character_from_image` | PNG/JPEG to a rigged character |
| `preview_character_from_prompt` | Preview images for a character description |
| `create_character_from_prompt` | Rig the preview you chose |
| `create_looped_motion` | Closed or open loop of an existing motion |
| `stitch_motions` | Join two clips with server sampling and optional placement |
| `create_stitched_motion` | Advanced join using host-sampled poses |
| `list_characters` | Character name filter and result pages |
| `list_motions` | Recent motion name search and source filters |
| `get_usage` | Pay-as-you-go balance, rates, and allowances |
| `check_download_allowed` | Current export eligibility |
| `save_motion` | Register host-edited animated GLTF JSON |
| `download_motion` | Retargeted FBX/GLB/BVH with export options |

`UthanaAPI.generate_v1` is a Python adapter method for V1 generation. It is not a separate MCP tool.

## Join two motions

Ask: “Stitch these two motions on my character with a one-second transition.” The `stitch_motions` tool asks Uthana to sample and align both clips. Optional forward/right offsets use meters relative to the first clip’s ending facing; positive facing degrees turn right. Review playback before accepting the result. See [stitching guidance](docs/stitching.md).

## Documentation

- [Workflow and recovery](src/uthana_mcp/WORKFLOW.md)
- [API coverage and limits](docs/api-coverage.md)
- [Stitching pose contract](docs/stitching.md)
- [Install and connect](docs/installation.md)
- [First animation and export](docs/first-animation.md)
- [Operational checks](docs/operations.md)
- [Contributing](CONTRIBUTING.md)
- [Public API documentation](https://uthana.com/docs/api)

## Develop from source

```sh
uv sync --locked
uv run --locked bash ./test.sh
```

Licensed under [Apache-2.0](LICENSE).
