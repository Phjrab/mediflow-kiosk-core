"""Private cross-process lock used by every device lifecycle entry point."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
from typing import IO


class LifecycleLockError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def open_lifecycle_lock(path: str | os.PathLike[str]) -> IO[str]:
    """Open an owner-only regular lock without following a final symlink."""
    lock_path = Path(path)
    if not lock_path.is_absolute():
        raise LifecycleLockError("unsafe_lifecycle_lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = lock_path.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise LifecycleLockError("unsafe_lifecycle_lock")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LifecycleLockError("unsafe_lifecycle_lock") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077):
            raise LifecycleLockError("unsafe_lifecycle_lock")
        return os.fdopen(descriptor, "r+")
    except Exception:
        os.close(descriptor)
        raise


def acquire_lifecycle_lock(handle: IO[str]) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise LifecycleLockError("operation_in_progress") from exc


def release_lifecycle_lock(handle: IO[str]) -> None:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
