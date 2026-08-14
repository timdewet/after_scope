"""Windows-specific watcher: real exit codes via a process handle.

Detection still polls (cheap); the SYNCHRONIZE handle grabbed at detection time lets
us read GetExitCodeProcess after death to distinguish crash from clean close.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from ..config import ZenCfg
from .process_watch import PollProcessWatcher, ProcInfo

log = logging.getLogger(__name__)

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class Win32ProcessWatcher(PollProcessWatcher):
    def __init__(self, zen_cfg: ZenCfg) -> None:
        super().__init__(zen_cfg)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handles: dict[int, int] = {}

    def find_running(self) -> ProcInfo | None:
        proc = super().find_running()
        if proc and proc.pid not in self._handles:
            handle = self._kernel32.OpenProcess(
                SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, proc.pid
            )
            if handle:
                self._handles[proc.pid] = handle
            else:
                log.warning("OpenProcess failed for pid %s (err=%s)", proc.pid,
                            ctypes.get_last_error())
        return proc

    def exit_code(self, proc: ProcInfo) -> int | None:
        handle = self._handles.get(proc.pid)
        if not handle:
            return None
        code = wintypes.DWORD()
        ok = self._kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        self._kernel32.CloseHandle(handle)
        self._handles.pop(proc.pid, None)
        if not ok or code.value == STILL_ACTIVE:
            return None
        return int(code.value)
