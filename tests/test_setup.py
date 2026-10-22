"""Setup must never expose a secret to an unprotected or existing file."""

import getpass
import sys

import pytest

from uthana_mcp import setup
from uthana_mcp.config import Config


def test_private_key_round_trip(tmp_path):
    path = tmp_path / "keys" / "api-key"
    setup.save_key(path, "example-key")
    config = Config(domain="uthana.com", data_dir=str(tmp_path), input_dir=None, key="", key_file=str(path))
    assert config.api_key() == "example-key"


def test_existing_file_is_preserved(tmp_path):
    path = tmp_path / "api-key"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        setup.save_key(path, "replacement")
    assert path.read_text() == "original"


@pytest.mark.parametrize("key", ["", "  ", "two keys", "a\nb", "x" * 8192])
def test_invalid_key_creates_no_file(tmp_path, key):
    path = tmp_path / "api-key"
    with pytest.raises(ValueError):
        setup.save_key(path, key)
    assert not path.exists()


def test_permission_failure_writes_no_secret(tmp_path, monkeypatch):
    path = tmp_path / "api-key"
    monkeypatch.setattr(setup, "private_to_user", lambda *args: False)
    with pytest.raises(ValueError, match="No key was written"):
        setup.save_key(path, "example-key")
    assert path.read_bytes() == b""


def test_cli_hidden_prompt_and_output(tmp_path, monkeypatch, capsys):
    path = tmp_path / "api-key"
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-setup", "--key-file", str(path)])
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "example-key")
    setup.main()
    output = capsys.readouterr().out
    assert str(path) in output
    assert "example-key" not in output
    assert "UTHANA_API_KEY_FILE" in output


@pytest.mark.parametrize("error", [getpass.GetPassWarning, EOFError, KeyboardInterrupt])
def test_cli_refuses_echoed_or_unavailable_input(tmp_path, monkeypatch, capsys, error):
    path = tmp_path / "api-key"
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-setup", "--key-file", str(path)])

    def prompt(_):
        raise error()

    monkeypatch.setattr(getpass, "getpass", prompt)
    with pytest.raises(SystemExit) as result:
        setup.main()
    assert result.value.code == 1
    assert not path.exists()
    assert "interactive terminal" in capsys.readouterr().err


def test_cli_existing_key_error(tmp_path, monkeypatch, capsys):
    path = tmp_path / "api-key"
    path.write_text("original")
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-setup", "--key-file", str(path)])
    monkeypatch.setattr(getpass, "getpass", lambda _: "replacement")
    with pytest.raises(SystemExit):
        setup.main()
    assert "already exists" in capsys.readouterr().err
    assert path.read_text() == "original"


def test_cli_save_error_is_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["uthana-mcp-setup", "--key-file", str(tmp_path / "key")])
    monkeypatch.setattr(getpass, "getpass", lambda _: "two keys")
    with pytest.raises(SystemExit):
        setup.main()
    assert "two keys" not in capsys.readouterr().err
