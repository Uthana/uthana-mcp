import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from uthana_mcp import artifact_io
from uthana_mcp.artifact_io import MAX_ARTIFACT_BYTES, read_artifact_bytes


def metadata(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@pytest.mark.parametrize("data", [b"native export bytes", b""])
def test_intact_artifact_returns_original_bytes(tmp_path, data):
    path = tmp_path / "export.fbx"
    path.write_bytes(data)
    assert read_artifact_bytes(path, metadata(data)) == data


def test_missing_artifact_preserves_missing_file_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_artifact_bytes(tmp_path / "missing.fbx", metadata(b"original"))


@pytest.mark.parametrize("replacement", [b"different", b"short", b"longer replacement"])
def test_changed_content_or_size_is_not_recovered(tmp_path, replacement):
    path = tmp_path / "export.fbx"
    path.write_bytes(replacement)
    with pytest.raises(ValueError, match="changed"):
        read_artifact_bytes(path, metadata(b"original!"))


def test_final_symlink_is_rejected_even_when_target_matches_hash(tmp_path):
    original = tmp_path / "original.fbx"
    original.write_bytes(b"original")
    path = tmp_path / "export.fbx"
    path.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        read_artifact_bytes(path, metadata(b"original"))


def test_directory_is_rejected_before_reading(tmp_path):
    with pytest.raises(ValueError, match="regular file"):
        read_artifact_bytes(tmp_path, metadata(b"original"))


def test_fifo_without_writer_cannot_block_recovery(tmp_path):
    path = tmp_path / "export.fbx"
    artifact_io.os.mkfifo(path)
    # A regression to blocking open must fail this child, rather than hang pytest.
    script = """
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from uthana_mcp.artifact_io import read_artifact_bytes
try:
    read_artifact_bytes(Path(sys.argv[2]), {"bytes": 1, "sha256": hashlib.sha256(b"x").hexdigest()})
except ValueError as error:
    assert "regular file" in str(error)
else:
    raise AssertionError("FIFO was accepted")
"""
    # subprocess.run kills and reaps the child if its bounded timeout expires.
    result = subprocess.run(
        [sys.executable, "-c", script, str(Path(artifact_io.__file__).parents[1]), str(path)],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_oversized_sparse_file_is_rejected_without_allocating_its_contents(tmp_path):
    path = tmp_path / "export.fbx"
    with path.open("wb") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(ValueError, match="changed"):
        read_artifact_bytes(path, metadata(b"original"))


@pytest.mark.parametrize("expected", [None, True, -1, 1.0, "1", MAX_ARTIFACT_BYTES + 1])
def test_invalid_or_over_limit_receipt_size_is_rejected_before_open(tmp_path, expected):
    receipt = metadata(b"x")
    receipt["bytes"] = expected
    with pytest.raises(ValueError, match="metadata"):
        read_artifact_bytes(tmp_path / "does-not-exist", receipt)


@pytest.mark.parametrize("digest", [None, "x" * 64, "a" * 63])
def test_invalid_receipt_hash_is_rejected_before_open(tmp_path, digest):
    receipt = metadata(b"x")
    receipt["sha256"] = digest
    with pytest.raises(ValueError, match="metadata"):
        read_artifact_bytes(tmp_path / "does-not-exist", receipt)


@pytest.mark.parametrize("receipt", [None, [], "metadata", {}])
def test_missing_or_non_object_receipt_is_a_recoverable_error(tmp_path, receipt):
    with pytest.raises(ValueError, match="metadata"):
        read_artifact_bytes(tmp_path / "does-not-exist", receipt)


@pytest.mark.parametrize("replacement_size", [1, MAX_ARTIFACT_BYTES + 1])
def test_size_change_after_initial_stat_is_rejected_with_a_bounded_read(tmp_path, monkeypatch, replacement_size):
    path = tmp_path / "export.fbx"
    path.write_bytes(b"original")
    original_fstat = artifact_io.os.fstat
    changed = False

    def change_after_stat(descriptor):
        nonlocal changed
        info = original_fstat(descriptor)
        if not changed:
            changed = True
            with path.open("r+b") as stream:
                stream.truncate(replacement_size)
        return info

    monkeypatch.setattr(artifact_io.os, "fstat", change_after_stat)
    with pytest.raises(ValueError, match="changed"):
        read_artifact_bytes(path, metadata(b"original"))


def test_growth_after_snapshot_read_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "export.fbx"
    path.write_bytes(b"original")
    original_fstat = artifact_io.os.fstat
    calls = 0

    def grow_before_final_stat(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            with path.open("ab") as stream:
                stream.write(b"extra")
        return original_fstat(descriptor)

    monkeypatch.setattr(artifact_io.os, "fstat", grow_before_final_stat)
    with pytest.raises(ValueError, match="changed"):
        read_artifact_bytes(path, metadata(b"original"))
