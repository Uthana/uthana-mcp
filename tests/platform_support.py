"""Create OS-specific fixtures, or skip when this platform cannot create them."""

import os

import pytest

from uthana_mcp.safe_open import open_nofollow, private_to_user

WINDOWS = os.name == "nt"


def symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError as error:
        # Windows needs Developer Mode or an elevated shell to create symlinks.
        if WINDOWS and getattr(error, "winerror", None) == 1314:
            pytest.skip("symlink creation needs Developer Mode or elevation on Windows")
        raise


def mkfifo_or_skip(path, *mode):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs do not exist on this platform")
    os.mkfifo(path, *mode)


def is_private(path):
    """POSIX: exact 600/700 mode. Windows: the DACL check the server itself applies."""
    if not WINDOWS:
        expected = 0o700 if path.is_dir() else 0o600
        return path.stat().st_mode & 0o777 == expected
    if path.is_dir():
        probe = path / ".private-probe"
        probe.write_bytes(b"")
        try:
            return is_private(probe)
        finally:
            probe.unlink()
    descriptor = open_nofollow(path)
    try:
        return private_to_user(descriptor, os.fstat(descriptor))
    finally:
        os.close(descriptor)
