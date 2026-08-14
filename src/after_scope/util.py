"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def now_iso() -> str:
    """Local naive ISO timestamp, second precision.

    This is a single-machine tool whose records are read directly by lab members,
    so local wall-clock time is stored everywhere (sortable, human-readable).
    """
    return datetime.now().strftime(ISO_FMT)


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value[:19], ISO_FMT)


def fmt_dt(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return ""
    try:
        return parse_iso(value).strftime(fmt)
    except ValueError:
        return value
