"""Bounded reads of receipt-associated local artifacts; never fetch replacements."""

import errno
import hashlib
import os
import re
import stat
from pathlib import Path

from .safe_open import open_nofollow

# Matches the largest response accepted by UthanaAPI.download; previews are smaller.
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024


def read_artifact_bytes(path: Path, metadata: dict) -> bytes:
    """Verify a bounded snapshot from one regular-file descriptor.

    A missing or malformed size/hash receipt cannot establish local integrity.
    Preserve missing-file OS errors for callers that distinguish them from changes.
    """
    metadata_error = "Saved artifact metadata is invalid or changed; do not redownload automatically"
    if not isinstance(metadata, dict):
        raise ValueError(metadata_error)
    expected = metadata.get("bytes")
    digest = metadata.get("sha256")
    if isinstance(expected, bool) or not isinstance(expected, int):
        raise ValueError(metadata_error)
    if not isinstance(digest, str):
        raise ValueError(metadata_error)
    size_out_of_bounds = not 0 <= expected <= MAX_ARTIFACT_BYTES
    invalid_sha256 = re.fullmatch(r"[a-fA-F0-9]{64}", digest) is None
    if size_out_of_bounds or invalid_sha256:
        raise ValueError(metadata_error)

    try:
        descriptor = open_nofollow(path)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError("Artifact was replaced by a symlink") from None
        if error.errno == errno.EISDIR:
            raise ValueError("Saved artifact changed; expected a regular file") from None
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Saved artifact changed; expected a regular file")
        if info.st_size != expected:
            raise ValueError("Saved artifact changed size; do not redownload automatically")
        # The extra byte detects growth without trusting a prior stat or reading to EOF.
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(expected + 1)
        if len(data) != expected or os.fstat(descriptor).st_size != expected:
            raise ValueError("Saved artifact changed size while reading; do not redownload automatically")
    finally:
        os.close(descriptor)

    if hashlib.sha256(data).hexdigest() != digest.lower():
        raise ValueError("Saved artifact changed; do not redownload automatically")
    return data
