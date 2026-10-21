"""Explicit local server configuration; secrets are loaded only for API operations."""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from .safe_open import open_nofollow, private_to_user
from .validation import UTHANA_DOMAIN


def git_root() -> Path | None:
    """Locate the uthana-mcp checkout; ignore a host project's working directory."""
    for path in Path(__file__).resolve().parents:
        pyproject = path / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if 'name = "uthana-mcp"' in text:
            return path
    return None


def load_dotenv() -> None:
    """Apply checkout .env then .env.local without overriding host-provided process env."""
    root = git_root()
    if root is None:
        return
    values = {}
    for name in (".env", ".env.local"):
        values.update({key: value for key, value in dotenv_values(root / name).items() if value is not None})
    for key, value in values.items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    domain: str
    data_dir: str
    input_dir: str | None
    key: str = field(repr=False)
    key_file: str | None

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            domain=os.environ.get("UTHANA_DOMAIN") or UTHANA_DOMAIN,
            data_dir=os.environ.get("UTHANA_MCP_DATA_DIR", str(Path.home() / ".local/state/uthana-mcp")),
            input_dir=os.environ.get("UTHANA_MCP_INPUT_DIR") or None,
            key=os.environ.get("UTHANA_API_KEY", ""),
            key_file=os.environ.get("UTHANA_API_KEY_FILE") or None,
        )

    def api_key(self):
        if self.key.strip() and self.key_file:
            raise ValueError("Configure only one of UTHANA_API_KEY or UTHANA_API_KEY_FILE")
        if not self.key_file:
            return self.key
        message = (
            "UTHANA_API_KEY_FILE must be a readable private regular file owned by this user "
            "(mode 600), not a symlink, containing one API key"
        )
        try:
            path = Path(self.key_file).expanduser()
            # O_NONBLOCK avoids hanging discovery's first API call on a FIFO.
            fd = open_nofollow(path)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not private_to_user(stream.fileno(), info):
                    raise ValueError(message)
                content = stream.read(8193)
            if len(content) > 8192:
                raise ValueError(message)
            key = content.decode("utf-8").strip()
            if not key or any(c.isspace() for c in key):
                raise ValueError(message)
            return key
        except (OSError, UnicodeError, ValueError):
            raise ValueError(message) from None
