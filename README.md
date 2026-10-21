# Uthana MCP

Animate a bipedal character through an AI assistant and export the result into your game. Start with [Uthana's rigged Tar GLB](examples/tar/cXi2eAP19XwQ.glb): “Upload my Tar character, make a four-second walk that ends with a wave, show me the motion, then export an animated FBX at 30 FPS.” The assistant can upload your selected FBX/GLB, generate motion, inspect previews, and request a retargeted export. [Follow the first-result walkthrough](FIRST-RESULT.md) to reproduce that sequence.

This package exposes Uthana's motion platform to MCP-capable coding agents: generate motions from text or video, create characters from images or rigged files, trim, loop, and stitch motions, and export retargeted animation. See [partner setup](PARTNER-SETUP.md) for local installation and [acceptance](BETA-ACCEPTANCE.md) for environment and host verification.

**Release review:** [Brandon's overview](BRANDON-REVIEW.md) explains what has been built, what to check before making this repository public, and how the related PRs fit together.

The host supplies the reasoning model and any editing or pose-sampling skills. The server uses the shared [Uthana Python client](https://github.com/Uthana/uthana-python-client) and local stdio transport. A browser-hosted connector requires a separate authenticated remote transport.

## Install and connect

Targets: Linux, macOS, and Windows, with Python 3.11 or later, Git, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Paths below are written for Linux/macOS; [partner setup](PARTNER-SETUP.md#windows) lists the Windows equivalents.

```sh
uv sync --locked
```

This installs the package and development tools from `pyproject.toml` and `uv.lock`. A server-only installation uses `uv sync --locked --no-dev`.

This baseline uses the published Uthana Python client. The lockfile records the exact dependency versions. Git is needed only when installing from a Git checkout.

The host starts `.venv/bin/uthana-mcp` (Windows: `.venv\Scripts\uthana-mcp.exe`) as a stdio server. **Production (`uthana.com`) is the default.** Override with `UTHANA_DOMAIN` (host env, constructor, or a checkout `.env` / `.env.local`). Tool discovery and the workflow resource work without credentials; Uthana operations require a key for the selected environment, supplied through a private file or the host environment.

| Variable | Purpose |
| --- | --- |
| `UTHANA_API_KEY` | API key for the selected environment; use this or the private file option |
| `UTHANA_API_KEY_FILE` | Private regular file containing the key, owned by the current user with mode 600 (Windows: an access list granting only you, `OWNER RIGHTS`, `SYSTEM`, and `Administrators`); not a symlink |
| `UTHANA_DOMAIN` | Defaults to `uthana.com`; override with any host. Host env wins over checkout `.env` / `.env.local` |
| `UTHANA_MCP_DATA_DIR` | Persistent private state; defaults to `~/.local/state/uthana-mcp` |
| `UTHANA_MCP_INPUT_DIR` | Selected input files on the server machine; uploads disabled when absent |

A host-neutral connection descriptor, with field names adapted to the host:

```json
{
  "command": "/absolute/path/to/venv/bin/uthana-mcp",
  "args": [],
  "env": {
    "UTHANA_DOMAIN": "uthana.com",
    "UTHANA_API_KEY_FILE": "/absolute/path/to/private-api-key",
    "UTHANA_MCP_DATA_DIR": "/absolute/path/to/private-state",
    "UTHANA_MCP_INPUT_DIR": "/absolute/path/to/selected-inputs"
  }
}
```

Only the key file path belongs in this descriptor. Keep the key itself outside prompts and Git; setting both key options is an error. Restart the server after changing environment or credentials. Production operations use the customer account and its credits. Authentication failures never switch environments. Inputs and exported files live on the server machine; remote hosts need a way to transfer those files.

Run `.venv/bin/uthana-mcp-smoke` to verify installation, tool discovery, and workflow loading without credentials or paid operations. With an explicitly configured API key, `--api-read` also checks one read-only account call. See [operational checks](OPERATIONS.md) for limits and troubleshooting.

| Operation | Host tool timeout |
| --- | --- |
| Character upload, looping, stitching | At least 420 seconds |
| Character from image | At least 1080 seconds |

Slow transfers may require longer. These four tools send MCP progress notifications when the caller supplies a progress token. Notifications report activity rather than a percentage; hosts may still enforce a total deadline.

## Tools

| Tool | What it does |
| --- | --- |
| `generate_motion` | Text-to-motion V3; usual starting point, including styled, compound, and acrobatic motion; returns a job ID |
| `generate_motion_v2` | Text-to-motion V2; fast basic motions, placeholders, and previz; returns a motion ID |
| `generate_locomotion` | Walk/run cycles from style, strides, speed, and direction |
| `list_locomotion_styles` | Available locomotion styles |
| `estimate_model_cost` | USD estimate from current model rates |
| `get_job` | Generation job state and available motion ID |
| `get_motion` | Native motion metadata and source-file identity |
| `get_request_status` | Local request state, result IDs, and recovery guidance |
| `trim_motion` | Save an interval as a new motion |
| `get_preview` | APNG or WebM preview |
| `get_preview_frame` | One APNG image with frame index and available timing |
| `generate_motion_from_video` | Video-to-motion (V2M) 2.0 or 2.1 job |
| `upload_character` | FBX/GLB upload with optional auto-rig, finger-joint control, and r15/ue5 skeleton conversion |
| `create_character_from_image` | PNG/JPEG to a rigged character |
| `preview_character_from_prompt` | Text prompt to candidate character images (stage 1) |
| `create_character_from_prompt` | Rig the chosen preview into a character (stage 2) |
| `create_looped_motion` | Closed/open loop of an existing motion |
| `create_stitched_motion` | Join two clips using host-sampled poses |
| `list_characters` | Character name filter and result pages |
| `list_motions` | Recent motion name search and source filters |
| `get_usage` | Pay-as-you-go (PAYG) balance, rates, and allowances |
| `check_download_allowed` | Current export eligibility |
| `save_motion` | Register host-edited animated GLTF JSON |
| `download_motion` | Retargeted FBX/GLB/BVH with export options |

The server exposes 24 tools, the `uthana://workflow` resource, and the optional `review_motion` prompt.

## Pricing and limitations

The [workflow](src/uthana_mcp/WORKFLOW.md) defines pricing, request recovery, and review behavior. The [coverage guide](COVERAGE.md) lists limitations, including local character pagination and the host's responsibility for stitching pose samples. Looping and stitching use preview APIs whose contracts can change.

## Documentation

- [Workflow and recovery](src/uthana_mcp/WORKFLOW.md)
- [API coverage](COVERAGE.md)
- [Stitching pose contract](STITCHING.md)
- [Acceptance procedure](ACCEPTANCE.md)
- [Example prompts and expected outcomes](PROMPT-TESTS.md)
- [First animation and export](FIRST-RESULT.md)
- [Operational checks and attribution](OPERATIONS.md)
- [Release review handoff](RELEASE-REVIEW.md)
- [Brandon's release overview](BRANDON-REVIEW.md)
- [Public API documentation](https://uthana.com/docs/api)

Context7 can provide optional documentation lookup alongside this operational MCP. Uthana's library identifier is `/websites/uthana_api`; documentation versions can differ from the installed tool schema.

## Development and license

```sh
uv run --locked ./test.sh
```

The checks run offline tests, formatting, lint, and package builds. `test.sh` needs a POSIX shell; on Windows, run the offline tests with `uv run --no-sync pytest -q`. There, symlink tests skip unless Developer Mode or an elevated shell allows creating symlinks, and FIFO tests skip because Windows has no FIFOs. Live model acceptance is a separate explicitly configured run that incurs model charges; tests must not silently select production.

Licensed under [Apache-2.0](LICENSE).
