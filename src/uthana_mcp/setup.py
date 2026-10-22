"""Interactive, local-only API key setup."""

import argparse
import getpass
import os
import subprocess
import warnings
from pathlib import Path

from .safe_open import _windows_current_user_sid, private_to_user

MAX_KEY_BYTES = 8192


def save_key(path: Path, key: str) -> None:
    """Create a private key file without replacing an existing file or link."""
    content = (key.strip() + "\n").encode("utf-8")
    if not key.strip() or any(char.isspace() for char in key.strip()) or len(content) > MAX_KEY_BYTES:
        raise ValueError("Enter one nonempty API key without whitespace (at most 8191 UTF-8 bytes).")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        # Harden the empty Windows file before writing any secret. Validation below
        # also rejects unexpected explicit allow entries retained from the parent.
        if os.name == "nt":
            sid = _windows_current_user_sid()
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:F"],
                check=True,
                capture_output=True,
            )
        if not private_to_user(stream.fileno(), os.fstat(stream.fileno())):
            raise ValueError("Cannot make the key file private. No key was written; choose a private folder.")
        stream.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Save your Uthana API key privately without making an API request.")
    parser.add_argument(
        "--key-file",
        type=Path,
        default=Path.home() / ".config" / "uthana" / "production-key",
        help="destination for a new private key file (existing files are never overwritten)",
    )
    args = parser.parse_args()
    path = args.key_file.expanduser().absolute()
    try:
        # getpass otherwise warns and falls back to an echoed stdin read.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("Uthana API key (hidden): ")
        save_key(path, key)
    except FileExistsError:
        parser.exit(1, "Key file already exists; use --key-file to choose a new path. Nothing was overwritten.\n")
    except (OSError, ValueError, subprocess.CalledProcessError):
        parser.exit(
            1,
            "Could not save a private key file. Check the path and permissions; existing files are never overwritten.\n",
        )
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        parser.exit(1, "Setup needs an interactive terminal with hidden input; no key was saved.\n")
    print(f"Saved private key file: {path}")
    print("Set UTHANA_API_KEY_FILE in your MCP host configuration to this path, then restart the host.")
    print("No API request was made.")


if __name__ == "__main__":
    main()
