"""Open a local file for reading without following a final symlink, on POSIX and Windows."""

import errno
import os
import stat

NOFOLLOW_NATIVE = hasattr(os, "O_NOFOLLOW")
_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


def _is_link(info) -> bool:
    # Windows junctions and other reparse points are not reported as S_IFLNK.
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_reparse_tag", 0))


def open_nofollow(path) -> int:
    """Return a read-only descriptor; raise OSError(ELOOP) when the final component is a link.

    POSIX uses O_NOFOLLOW (and O_NONBLOCK so a FIFO cannot hang the caller). Windows has
    neither flag, so reject a link from lstat and confirm the opened descriptor is the same
    file, which closes the window between the check and the open.
    """
    if NOFOLLOW_NATIVE:
        return os.open(path, _FLAGS)
    before = os.lstat(path)
    if _is_link(before):
        raise OSError(errno.ELOOP, "Refusing to follow a symlink", str(path))
    if stat.S_ISDIR(before.st_mode):
        # Windows cannot open a directory descriptor; POSIX callers reject it after fstat.
        raise IsADirectoryError(errno.EISDIR, "Expected a regular file", str(path))
    descriptor = os.open(path, _FLAGS)
    after = os.fstat(descriptor)
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        os.close(descriptor)
        raise OSError(errno.ELOOP, "File was replaced while opening", str(path))
    return descriptor


def private_to_user(descriptor: int, info) -> bool:
    """True when only this user can read the open file.

    POSIX: owned by this user with no group/other permission bits (mode 600).
    Windows: owned by this user, and every allow entry in the file's DACL names this
    user, OWNER RIGHTS, SYSTEM, or Administrators. A missing (NULL) DACL grants everyone access.
    """
    if os.name != "nt":
        return info.st_uid == os.geteuid() and not info.st_mode & 0o077
    try:
        owner, allowed = _windows_owner_and_allowed_sids(descriptor)
        user = _windows_current_user_sid()
    except OSError:
        return False
    if allowed is None or owner != user:
        return False
    return allowed <= {user, _OWNER_RIGHTS_SID, _SYSTEM_SID, _ADMINISTRATORS_SID}


# OWNER RIGHTS is what Python 3.12+ writes for mkdir(mode=0o700) on Windows.
_OWNER_RIGHTS_SID = "S-1-3-4"
_SYSTEM_SID = "S-1-5-18"
_ADMINISTRATORS_SID = "S-1-5-32-544"
# ACCESS_ALLOWED, ACCESS_ALLOWED_OBJECT, ACCESS_ALLOWED_CALLBACK, ACCESS_ALLOWED_CALLBACK_OBJECT
_ALLOW_ACE_TYPES = {0, 5, 9, 11}
_INHERIT_ONLY_ACE = 0x08


def _windows_api():
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.GetSecurityInfo.restype = wintypes.DWORD
    advapi32.GetSecurityInfo.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]  # fmt: skip
    advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]  # fmt: skip
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return ctypes, wintypes, advapi32, kernel32


def _sid_string(ctypes, wintypes, advapi32, kernel32, sid) -> str:
    text = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW failed")
    try:
        return text.value
    finally:
        kernel32.LocalFree(text)


def _windows_owner_and_allowed_sids(descriptor: int):
    """Return (owner SID, set of SIDs with allow entries), or (owner, None) for a NULL DACL."""
    import msvcrt

    ctypes, wintypes, advapi32, kernel32 = _windows_api()
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    security = ctypes.c_void_p()
    se_file_object, owner_info, dacl_info = 1, 0x1, 0x4
    status = advapi32.GetSecurityInfo(
        msvcrt.get_osfhandle(descriptor), se_file_object, owner_info | dacl_info,
        ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(security),
    )  # fmt: skip
    if status:
        raise OSError(status, "GetSecurityInfo failed")
    try:
        owner_sid = _sid_string(ctypes, wintypes, advapi32, kernel32, owner)
        if not dacl.value:
            return owner_sid, None
        # ACL header: AclRevision, Sbz1 (BYTE), AclSize, AceCount, Sbz2 (WORD)
        ace_count = ctypes.cast(dacl, ctypes.POINTER(wintypes.WORD))[2]
        allowed = set()
        for index in range(ace_count):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                raise OSError(ctypes.get_last_error(), "GetAce failed")
            # ACE header: AceType, AceFlags (BYTE), AceSize (WORD); then Mask (DWORD), then the SID.
            header = ctypes.cast(ace, ctypes.POINTER(ctypes.c_ubyte))
            ace_type, ace_flags = header[0], header[1]
            if ace_flags & _INHERIT_ONLY_ACE:
                continue
            if ace_type not in _ALLOW_ACE_TYPES:
                continue
            if ace_type != 0:
                # Object and callback allow entries are unusual on files; treat them as non-private.
                return owner_sid, {"unrecognized-allow-entry"}
            allowed.add(_sid_string(ctypes, wintypes, advapi32, kernel32, ace.value + 8))
        return owner_sid, allowed
    finally:
        kernel32.LocalFree(security)


def _windows_current_user_sid() -> str:
    ctypes, wintypes, advapi32, kernel32 = _windows_api()
    token = wintypes.HANDLE()
    token_query, token_user = 0x0008, 1
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, token_user, buffer, size, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation failed")
        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first field is the SID pointer.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        return _sid_string(ctypes, wintypes, advapi32, kernel32, sid)
    finally:
        kernel32.CloseHandle(token)
