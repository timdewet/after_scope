"""Rotating per-role log files under the local data dir."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import AppPaths

FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(paths: AppPaths, role: str, level: int = logging.INFO) -> None:
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(
        paths.logs_dir / f"{role}.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(FMT))
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter(FMT))
    root.addHandler(sh)
