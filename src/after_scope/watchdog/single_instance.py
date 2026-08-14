"""One watchdog / one wizard at a time (named mutex on Windows, lockfile elsewhere)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


class SingleInstance:
    def __init__(self, name: str, lock_dir: Path) -> None:
        self.name = name
        self.lock_dir = lock_dir
        self._handle = None
        self._file = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            ERROR_ALREADY_EXISTS = 183
            if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                return False
            self._handle = handle
            return True
        import fcntl

        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_dir / f"{self.name}.lock", "w")
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._file.close()
            self._file = None
            return False

    def release(self) -> None:
        if self._handle is not None:
            import ctypes

            ctypes.WinDLL("kernel32").CloseHandle(self._handle)
            self._handle = None
        if self._file is not None:
            self._file.close()
            self._file = None
