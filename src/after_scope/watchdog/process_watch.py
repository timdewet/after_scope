"""Detecting ZEN (or the fake dev stand-in) starting and stopping."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import psutil

from ..config import ZenCfg

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    name: str
    create_time: float


class ProcessWatcher(Protocol):
    def find_running(self) -> ProcInfo | None: ...

    def is_alive(self, proc: ProcInfo) -> bool: ...

    def exit_code(self, proc: ProcInfo) -> int | None: ...


class PollProcessWatcher:
    """psutil-based watcher. Matches by process name, or — for dev, where a python
    script's name is just "python" — by a marker substring in the command line."""

    def __init__(self, zen_cfg: ZenCfg) -> None:
        self._names = {n.lower() for n in zen_cfg.process_names}
        self._marker = zen_cfg.cmdline_contains

    def _matches(self, info: dict) -> bool:
        name = (info.get("name") or "").lower()
        if name in self._names:
            return True
        if self._marker:
            cmdline = " ".join(info.get("cmdline") or [])
            return self._marker in cmdline
        return False

    def find_running(self) -> ProcInfo | None:
        for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            try:
                if self._matches(p.info):
                    return ProcInfo(p.info["pid"], p.info["name"] or "", p.info["create_time"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def is_alive(self, proc: ProcInfo) -> bool:
        try:
            p = psutil.Process(proc.pid)
            # guard against PID reuse
            return p.is_running() and abs(p.create_time() - proc.create_time) < 1.0
        except psutil.NoSuchProcess:
            return False

    def exit_code(self, proc: ProcInfo) -> int | None:
        # Not knowable for a non-child process without Win32 handles; the Windows
        # watcher overrides this. None is treated as a clean exit.
        return None


def make_watcher(zen_cfg: ZenCfg) -> ProcessWatcher:
    import sys

    if sys.platform == "win32":
        try:
            from .win32_watch import Win32ProcessWatcher

            return Win32ProcessWatcher(zen_cfg)
        except Exception:
            log.warning("Win32 watcher unavailable; falling back to polling", exc_info=True)
    return PollProcessWatcher(zen_cfg)
