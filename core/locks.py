"""Cross-process advisory locks under the plugin's profile-scoped data dir."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import time
from pathlib import Path


class LockTimeout(RuntimeError):
    pass


@contextlib.contextmanager
def file_lock(path: Path, timeout: float = 30.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"timed out waiting for lock {path.name}")
                time.sleep(0.1)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def task_lock(data_dir: Path, task_id: str | None, path: Path, timeout: float = 30.0):
    """Lock keyed by task ID (stable across renames), falling back to path."""
    key = f"id:{task_id}" if task_id else f"path:{path}"
    name = hashlib.sha256(key.encode()).hexdigest() + ".lock"
    return file_lock(data_dir / "locks" / name, timeout)


def workspace_lock(data_dir: Path, name: str, timeout: float = 60.0):
    return file_lock(data_dir / "locks" / f"{name}.lock", timeout)
