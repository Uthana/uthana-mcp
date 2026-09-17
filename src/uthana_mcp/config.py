"""Explicit local server configuration; secrets are loaded only for API operations."""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from .validation import STAGING, api_domain


@dataclass(frozen=True)
class Settings:
    domain: str
    data_dir: str
    input_dir: str | None
    key: str = field(repr=False)
    key_file: str | None

    @classmethod
    def from_env(cls):
        return cls(
            domain=api_domain(os.environ.get("UTHANA_DOMAIN", STAGING)),
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
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
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
