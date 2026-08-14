"""Sweep watch directories for new acquisition files and report them once stable.

A file is "stable" when its size+mtime are unchanged across two consecutive sweeps
AND it can be opened for shared read (ZEN holds exclusive locks while writing on
Windows). Robust on Dropbox/network paths, no filesystem-event dependencies.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig

log = logging.getLogger(__name__)


@dataclass
class _Tracked:
    size: int
    mtime: float
    stable_sweeps: int = 0
    reported: bool = False


class AcquisitionScanner:
    def __init__(self, cfg: AppConfig) -> None:
        self.watch_dirs = [(Path(w.path), w.recursive) for w in cfg.watch_dirs]
        self.extra_dirs: list[Path] = []  # session-scoped (e.g. the declared session folder)
        self.patterns = [p.lower() for p in cfg.scan.file_patterns]
        self.slack = cfg.scan.pre_start_slack_seconds
        self._tracked: dict[str, _Tracked] = {}
        self.last_file_mtime: float = 0.0  # activity signal for dormancy detection

    def add_extra_dir(self, path: Path | str) -> None:
        """Watch an additional root for the current session (deduplicated; a dir
        already under a recursive watch root is skipped)."""
        p = Path(path)
        if any(p == d for d in self.extra_dirs):
            return
        for root, recursive in self.watch_dirs:
            if p == root or (recursive and p.is_relative_to(root)):
                return
        self.extra_dirs.append(p)

    def _matches(self, name: str) -> bool:
        low = name.lower()
        return any(fnmatch.fnmatch(low, p) for p in self.patterns)

    def _iter_files(self, root: Path, recursive: bool):
        try:
            with os.scandir(root) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                yield from self._iter_files(Path(entry.path), True)
                        elif self._matches(entry.name):
                            yield entry
                    except OSError:
                        continue
        except OSError:
            return  # unreadable / offline watch root: skip this sweep

    @staticmethod
    def _readable(path: str) -> bool:
        try:
            with open(path, "rb") as f:
                f.read(1)
            return True
        except OSError:
            return False

    def sweep(self, session_start_epoch: float) -> list[Path]:
        """Returns files that became stable this sweep (each reported exactly once)."""
        cutoff = session_start_epoch - self.slack
        newly_stable: list[Path] = []
        for root, recursive in self.watch_dirs + [(d, True) for d in self.extra_dirs]:
            for entry in self._iter_files(root, recursive):
                try:
                    st = entry.stat()
                except OSError:
                    continue
                if st.st_mtime < cutoff:
                    continue
                self.last_file_mtime = max(self.last_file_mtime, st.st_mtime)
                tracked = self._tracked.get(entry.path)
                if tracked is None:
                    self._tracked[entry.path] = _Tracked(st.st_size, st.st_mtime)
                    continue
                if tracked.reported:
                    continue
                if st.st_size == tracked.size and st.st_mtime == tracked.mtime:
                    tracked.stable_sweeps += 1
                    if tracked.stable_sweeps >= 1 and self._readable(entry.path):
                        tracked.reported = True
                        newly_stable.append(Path(entry.path))
                else:
                    tracked.size, tracked.mtime, tracked.stable_sweeps = (
                        st.st_size,
                        st.st_mtime,
                        0,
                    )
        return newly_stable

    def reset(self) -> None:
        self._tracked.clear()
        self.extra_dirs.clear()
        self.last_file_mtime = 0.0
