# Uthana MCP

[![PyPI version](https://badge.fury.io/py/uthana-mcp.svg)](https://badge.fury.io/py/uthana-mcp)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

The MCP connector code is licensed under [Apache-2.0](LICENSE). The bundled Tar character is separately licensed under the [Tar Demo Asset License](examples/tar/LICENSE.md) for testing, evaluation, tutorials, and demos, including commercial evaluation. Tar is not licensed for production games, asset-pack redistribution, AI training, or publication of appearance changes. [Tar usage guide](examples/tar/README.md).

Local [MCP](https://modelcontextprotocol.io) server for [Uthana](https://uthana.com): generate motion from text or video, create characters from prompts, images, or rigged files, trim, loop, and stitch motions, and export retargeted animation.

The host supplies the reasoning model. This server uses the shared [Uthana Python client](https://github.com/Uthana/uthana-python-client) and speaks stdio. It registers 24 tools and the `uthana://workflow` resource.

📖 [API documentation](https://uthana.com/docs/api) · [First animation](docs/first-animation.md)

## Install

Download and run the installer for your platform:

**macOS / Linux**

```sh
curl -fsSL https://raw.githubusercontent.com/Uthana/uthana-mcp/main/install.sh -o install.sh
sh install.sh
```

**Windows (PowerShell)**

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/Uthana/uthana-mcp/main/install.ps1 -OutFile install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

The installer checks for uv, installs it if needed, and installs the MCP with Python 3.12. No existing Python installation is required. It prints the server command for your host configuration. Create an API key in your [Uthana account settings](https://uthana.com) and paste its value into `UTHANA_API_KEY` below.

See the [installation guide](docs/installation.md) for manual installation, environment settings, and tool timeouts.

## Connect

Use the absolute server command printed by the installer. For Claude Desktop (`claude_desktop_config.json`):

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

Claude Code (one command; `-s user` stores it for every project, or put the same `mcpServers` object as above in a project `.mcp.json`):

```bash
claude mcp add uthana -s user -e UTHANA_API_KEY=your-api-key -e UTHANA_MCP_INPUT_DIR=/absolute/path/to/selected-inputs -- /absolute/path/to/uthana-mcp
```

[Install and connect](docs/installation.md) has Windows path examples and host timeout settings.

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
| `stitch` | Join typed motion/transition/motion steps with server preparation |
| `list_characters` | Character name filter and result pages |
| `list_motions` | Recent motion name search and source filters |
| `get_usage` | Pay-as-you-go balance, rates, and allowances |
| `check_download_allowed` | Current export eligibility |
| `save_motion` | Register host-edited animated GLTF JSON |
| `download_motion` | Retargeted FBX/GLB/BVH with export options |

`UthanaAPI.generate_v1` is a Python adapter method for V1 generation. It is not a separate MCP tool.

## Join two motions

Call the `stitch` tool with the following arguments, or ask your host to stitch the selected motions. Replace the character and motion IDs with your own.

### Simple join

Join two motions with automatic positioning. The server handles sampling and alignment.

```json
{
  "request_id": "stitch-basic",
  "character_id": "CHARACTER_ID",
  "steps": [
    {
      "type": "motion",
      "motion_id": "FIRST_MOTION_ID"
    },
    {
      "type": "transition",
      "duration_seconds": 1.0
    },
    {
      "type": "motion",
      "motion_id": "SECOND_MOTION_ID"
    }
  ]
}
```

### Join with ranges and positioning

Select source intervals and place the second motion one meter forward and half a meter right of the first motion’s ending pelvis, turned 45 degrees right. Placement is relative to the first motion’s ending facing.

```json
{
  "request_id": "stitch-positioned",
  "character_id": "CHARACTER_ID",
  "steps": [
    {
      "type": "motion",
      "motion_id": "FIRST_MOTION_ID",
      "range": {
        "start_frame": 12,
        "end_frame": 60
      }
    },
    {
      "type": "transition",
      "duration_seconds": 1.5
    },
    {
      "type": "motion",
      "motion_id": "SECOND_MOTION_ID",
      "range": {
        "start_seconds": 0.5,
        "end_seconds": 3.0
      },
      "placement": {
        "forward_m": 1.0,
        "right_m": 0.5,
        "turn_degrees": 45.0
      }
    }
  ]
}
```

Choose ranges that fit your source motions and leave the required transition context. Frame indices use each source’s native FPS; do not mix frames and seconds within one range. Inspect `resolved_steps` and review playback before accepting the result.

Each example makes a separate mutation. Use a distinct request ID for different arguments; recover an uncertain request before retrying. See [stitching](docs/stitching.md) for the full contract.

## Documentation

- [Workflow and recovery](src/uthana_mcp/WORKFLOW.md)
- [API coverage and limits](docs/api-coverage.md)
- [Stitching steps and positioning](docs/stitching.md)
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

The hosted MCP is a technical preview and is not recommended for production use. Operator integration is described in [Hosted transport](docs/hosting.md). Local stdio installation remains supported.
