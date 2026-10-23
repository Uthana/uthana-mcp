"""Local server configuration captured from the environment at startup."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

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
    _key: str = field(repr=False)

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            domain=os.environ.get("UTHANA_DOMAIN") or UTHANA_DOMAIN,
            data_dir=os.environ.get("UTHANA_MCP_DATA_DIR", str(Path.home() / ".local/state/uthana-mcp")),
            input_dir=os.environ.get("UTHANA_MCP_INPUT_DIR") or None,
            _key=os.environ.get("UTHANA_API_KEY", ""),
        )
