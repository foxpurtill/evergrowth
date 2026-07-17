"""Cross-process singleton guard for the persistent Evergrowth runtime."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time
from pathlib import Path


class RuntimeSingleton:
    """Hold one OS-level lock for one Evergrowth data directory."""

    def __init__(self, marker_path: Path, *, handle=None, lock_file=None, kernel32=None):
        self.marker_path = marker_path
        self._handle = handle
        self._lock_file = lock_file
        self._kernel32 = kernel32

    @classmethod
    def acquire(cls, data_dir: Path):
        data_dir = data_dir.expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        marker_path = data_dir / "persistent-runtime.lock.json"
        digest = hashlib.sha256(str(data_dir).lower().encode("utf-8")).hexdigest()[:16]

        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_bool
            handle = kernel32.CreateMutexW(None, False, f"Local\\Evergrowth-{digest}")
            if not handle:
                raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
            if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(handle)
                return None
            guard = cls(marker_path, handle=handle, kernel32=kernel32)
        else:
            import fcntl

            lock_file = open(data_dir / "persistent-runtime.lock", "a+b")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                return None
            guard = cls(marker_path, lock_file=lock_file)

        guard._write_marker()
        return guard

    def _write_marker(self) -> None:
        payload = {
            "pid": os.getpid(),
            "acquired_at": time.time(),
            "mode": "persistent",
        }
        temporary = self.marker_path.with_suffix(self.marker_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.marker_path)

    def release(self) -> None:
        try:
            if self._handle is not None and self._kernel32 is not None:
                self._kernel32.CloseHandle(self._handle)
                self._handle = None
            if self._lock_file is not None:
                import fcntl

                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
        finally:
            try:
                data = json.loads(self.marker_path.read_text(encoding="utf-8"))
                if data.get("pid") == os.getpid():
                    self.marker_path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
