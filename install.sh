#!/bin/sh
# Install locally for the current user; no sudo or shell profile changes.
set -eu

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) printf '%s\n' 'Use install.ps1 on Windows.' >&2; exit 1 ;;
esac

uv_command=$(command -v uv || true)
if [ -z "$uv_command" ] && [ -x "$HOME/.local/bin/uv" ]; then
    uv_command="$HOME/.local/bin/uv"
fi
if [ -z "$uv_command" ]; then
    command -v curl >/dev/null 2>&1 || {
        printf '%s\n' 'curl is required to install uv. Install curl or uv, then rerun this script.' >&2
        exit 1
    }
    printf '%s\n' 'Installing uv for your user from astral.sh...'
    uv_installer=$(mktemp)
    trap 'rm -f "$uv_installer"' EXIT HUP INT TERM
    curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh -o "$uv_installer"
    UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$uv_installer"
    uv_command="$HOME/.local/bin/uv"
fi

"$uv_command" --version
printf '%s\n' 'Installing Uthana MCP with Python 3.12 (downloaded by uv if needed)...'
"$uv_command" tool install --python 3.12 uthana-mcp
bin_dir=$("$uv_command" tool dir --bin)
printf 'MCP server command: %s/uthana-mcp\n' "$bin_dir"
printf '%s\n' 'Use that absolute command in your host configuration with no arguments.'

printf '%s\n' 'Create an API key in your Uthana account settings and set UTHANA_API_KEY in your host configuration.'
printf '%s\n' 'Restart your MCP host after configuring it.'
