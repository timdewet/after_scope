"""Seconds since the last keyboard/mouse input."""

from __future__ import annotations

import sys
from typing import Protocol


class IdleMonitor(Protocol):
    def seconds_idle(self) -> float: ...


class NullIdleMonitor:
    """Used where real input tracking isn't available (macOS dev): never idle,
    so dormancy/handover only triggers via the tray or tests."""

    def seconds_idle(self) -> float:
        return 0.0


class FakeIdleMonitor:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def seconds_idle(self) -> float:
        return self.value


class WindowsIdleMonitor:
    """GetLastInputInfo — no admin rights, session-wide, cheap."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        self._ctypes = ctypes
        self._user32 = ctypes.WinDLL("user32")
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._struct = LASTINPUTINFO

    def seconds_idle(self) -> float:
        info = self._struct()
        info.cbSize = self._ctypes.sizeof(info)
        if not self._user32.GetLastInputInfo(self._ctypes.byref(info)):
            return 0.0
        ticks = self._kernel32.GetTickCount() - info.dwTime  # wraps every ~49 days; harmless
        return max(0.0, ticks / 1000.0)


def make_idle_monitor() -> IdleMonitor:
    if sys.platform == "win32":
        return WindowsIdleMonitor()
    return NullIdleMonitor()
