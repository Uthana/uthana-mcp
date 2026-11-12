# Uthana MCP

[![PyPI version](https://badge.fury.io/py/uthana-mcp.svg)](https://badge.fury.io/py/uthana-mcp) [![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/LICENSE)

[MCP](https://modelcontextprotocol.io) connector for [Uthana](https://uthana.com): generate motion from text or video, create characters from prompts, images, or rigged files, trim, loop, and stitch motions, and export retargeted animation.

Connect to the hosted server with your Uthana account, or run the open-source connector locally with an API key. Your AI client supplies the reasoning model; Uthana provides the animation tools.

📖 [Set up Uthana MCP](https://uthana.com/mcp/setup) · [API documentation](https://uthana.com/docs/api) · [First animation](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/first-animation.md)

## Status and versions

- **Hosted (recommended):** `https://mcp.uthana.com/mcp` is Uthana's production MCP service. Sign in with your Uthana account; no installation or API key. Start at the [setup page](https://uthana.com/mcp/setup).
- **Local:** this open-source connector is supported on Linux, macOS, and Windows for clients that run local servers, or when you want it to read files from your own disk. It uses an API key.
- **Same platform, small differences:** both routes call the same Uthana service, account, and credits. The hosted server adds one tool, `get_artifact_download`, to refresh an expired download link; hosted tools take uploaded file handles instead of local paths and return download links instead of saving files.
- **Versions:** PyPI publishes tagged releases, and the PyPI page shows the README of that release. The `main` branch can contain changes that are not released yet; see [release notes](https://github.com/Uthana/uthana-mcp/releases). Check a local install with `uv tool list` and upgrade it with `uv tool upgrade uthana-mcp`.

## Hosted

Add this URL in your AI client's MCP settings:

```text
https://mcp.uthana.com/mcp
```

Sign in with your Uthana account and approve the requested permissions. Hosted setup needs no installation or API key. Start by asking: “Show my Uthana account’s available balance and allowances. Don’t create or change anything.”

See the [setup guide](https://uthana.com/mcp/setup) for Codex desktop/CLI, Claude desktop/web, Claude Code CLI, and Cursor setup, file uploads, downloads, and troubleshooting. The [technical reference](https://uthana.com/docs/api/capabilities/hosted-mcp) covers sign-in details, the client compatibility table, and recovery. Normal client approval prompts and Uthana pricing apply.

Tar, Ava, and Manny (also called Manny Fingers) are available to every user, so you can start animating without uploading a character. See the [first-animation walkthrough](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/first-animation.md).

## Local installation

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

See the [installation guide](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/installation.md) for manual installation, environment settings, and tool timeouts.

## Connect locally

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

[Install and connect](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/installation.md) has Windows path examples and host timeout settings.

Restart your host, then ask it to read Uthana’s workflow, check account access, and estimate a motion before generating it. Production generation spends your account’s credits. Continue with the [first-animation walkthrough](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/first-animation.md) for upload, generation, and export.

## Tools

| Tool | What it does |
| --- | --- |
| `generate_motion` | Text-to-motion V3: Regular, Lite or Mini via `model`, plus optional `fast`. Returns a job ID |
| `generate_motion_v2` | Text-to-motion V2. Returns a motion ID |
| `generate_locomotion` | Walk or run cycles from style, strides, speed, and direction |
| `list_locomotion_styles` | Available locomotion styles |
| `estimate_model_cost` | USD estimate from current model rates |
| `get_job` | Generation job state and available motion ID |
| `get_motion` | Native motion metadata and source-file identity |
| `get_request_status` | Request state, result IDs, and recovery guidance |
| `get_artifact_download` | Hosted only: refresh a cached file’s download link without another export |
| `trim_motion` | Save an interval as a new motion |
| `get_preview` | APNG or WebM preview |
| `get_preview_frame` | One APNG frame with index and available timing |
| `generate_motion_from_video` | Video-to-motion (V2M) job; 3.0 by default, 2.0 or 2.1 on request |
| `upload_character` | FBX/GLB upload, with optional auto-rig and rerig options |
| `create_character_from_image` | PNG/JPEG to a rigged character |
| `preview_character_from_prompt` | Preview images for a character description |
| `create_character_from_prompt` | Rig the preview you chose |
| `create_looped_motion` | Closed or open loop of an existing motion |
| `stitch` | Join two motion objects with server preparation |
| `list_characters` | Character name filter and result pages |
| `list_motions` | Recent motion name search and source filters |
| `copy_best_library_motion` | Charged library search: copies the single closest library clip into your organization |
| `get_usage` | Pay-as-you-go balance, rates, and allowances |
| `get_billing_history` | Recorded PAYG charges, payments, free credit and adjustments, newest first |
| `check_download_allowed` | Current export eligibility |
| `save_motion` | Register host-edited animated GLTF JSON |
| `download_motion` | Retargeted FBX/GLB/BVH with export options |
| `download_character` | The character's own GLB/FBX model, without animation |
| `rename_character`, `rename_motion` | Rename an asset your organization owns |
| `delete_character`, `delete_motion` | Soft-delete an asset your organization owns, by ID after the user selects it |
| `restore_character`, `restore_motion` | Undo a delete by ID |

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
      "motion_id": "FIRST_MOTION_ID"
    },
    {
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
      "motion_id": "FIRST_MOTION_ID",
      "trim_start_frame": 12,
      "trim_end_frame": 60,
      "transition_duration_seconds": 1.5,
      "transition_forward_meters": 1.0,
      "transition_right_meters": 0.5,
      "transition_facing_degrees": 45.0
    },
    {
      "motion_id": "SECOND_MOTION_ID",
      "trim_start_seconds": 0.5,
      "trim_end_seconds": 3.0
    }
  ]
}
```

Choose ranges that fit your source motions and leave the required transition context. Frame indices use each source’s native FPS; do not mix frames and seconds within one range. Inspect `resolved_steps` and review playback before accepting the result.

Each example makes a separate mutation. Use a distinct request ID for different arguments; recover an uncertain request before retrying. See [stitching](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/stitching.md) for the full contract.

## Documentation

- [Workflow and recovery](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/src/uthana_mcp/WORKFLOW.md)
- [API coverage and limits](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/api-coverage.md)
- [Stitching steps and positioning](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/stitching.md)
- [Hosted connection guide](https://uthana.com/docs/api/capabilities/hosted-mcp)
- [Local installation and connection](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/installation.md)
- [Hosted integration for operators](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/hosting.md)
- [First animation and export](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/first-animation.md)
- [Blender import, playback, and multiple clips](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/blender.md)
- [What each operation costs](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/pricing.md)
- [Operational checks](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/docs/operations.md)
- [Contributing](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/CONTRIBUTING.md)

- [Public API documentation](https://uthana.com/docs/api)

## Develop from source

```sh
uv sync --locked
uv run --locked bash ./test.sh
```

## Trial generation limits

Without a valid saved payment method, an organization can have four queued, delayed, or running jobs per type. TTM and VTM have separate slots; all members share them. Pending generations reserve funds before running.

A confirmed `job_limit_exceeded` HTTP 429 response is reported as `category="rate_limit"`, `outcome="rejected"`, and `safe_to_resubmit=true`. Wait for existing jobs to complete before resubmitting; the connector does not retry automatically. An unrecognized HTTP 429 keeps `outcome="unknown"` and requires the normal receipt recovery workflow before any resubmission.

## License

The MCP connector code is licensed under [Apache-2.0](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/LICENSE). The bundled Tar character is separately licensed under the [Tar Demo Asset License](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/examples/tar/LICENSE.md) for testing, evaluation, tutorials, and demos, including commercial evaluation. Tar is not licensed for production games, asset-pack redistribution, AI training, or publication of appearance changes. [Tar usage guide](https://github.com/Uthana/uthana-mcp/blob/v0.4.0/examples/tar/README.md).
