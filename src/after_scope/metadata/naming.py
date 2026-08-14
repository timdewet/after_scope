"""Standardized file naming: templates, sanitization, sequence numbers, length guard."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

TOKEN_MAX = 40
_ALLOWED = re.compile(r"[^A-Za-z0-9\-]+")
_DASHES = re.compile(r"-{2,}")


def sanitize_token(value: str | None, max_len: int = TOKEN_MAX) -> str:
    """Make a value safe as a filename token: [A-Za-z0-9-] only."""
    if not value:
        return ""
    v = _ALLOWED.sub("-", value.strip())
    v = _DASHES.sub("-", v).strip("-")
    return v[:max_len].strip("-")


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _fmt(template: str, ctx: dict) -> str:
    out = template.format_map(_SafeDict(ctx))
    # collapse artefacts of empty tokens: "a__b" -> "a_b", trailing separators
    out = re.sub(r"_{2,}", "_", out)
    return out.strip("_-")


def build_context(
    *,
    acquired_at: str | None,
    initials: str | None,
    experiment: str | None,
    strain: str | None,
    condition: str | None,
    original_stem: str | None = None,
) -> dict:
    try:
        dt = datetime.strptime((acquired_at or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        dt = datetime.now()
    return {
        "date": dt.strftime("%Y%m%d"),
        "time": dt.strftime("%H%M"),
        "year": dt.strftime("%Y"),
        "initials": sanitize_token(initials),
        "experiment": sanitize_token(experiment),
        "strain": sanitize_token(strain),
        "condition": sanitize_token(condition),
        "orig": sanitize_token(original_stem, 60),
    }


DIR_TOKEN_MAX = 24


def render_dest_dir(dest_template: str, ctx: dict, dropbox_root: Path) -> Path:
    # Free-text tokens are capped harder in directory names — the directory is shared
    # by every file of the experiment and the filename guard can't shorten it later.
    dir_ctx = {
        k: (v[:DIR_TOKEN_MAX] if k in ("experiment", "strain", "condition") else v)
        for k, v in ctx.items()
    }
    rendered = _fmt(dest_template, {**dir_ctx, "dropbox_root": str(dropbox_root)})
    return Path(rendered)


def propose_filename(
    filename_template: str,
    ctx: dict,
    dest_dir: Path,
    suffix: str,
    taken: set[str],
    max_path_length: int = 240,
) -> str:
    """Pick the first free sequence number in dest_dir (also avoiding `taken` names
    planned in this batch), shortening tokens if the full path would be too long."""
    local_ctx = dict(ctx)
    for attempt in range(4):
        for seq in range(1, 1000):
            name = _fmt(filename_template, {**local_ctx, "seq": seq}) + suffix
            full = dest_dir / name
            if name in taken or full.exists():
                continue
            if len(str(full)) <= max_path_length:
                return name
            break  # too long: shorten tokens and retry
        # progressively truncate the longest free-text tokens
        limit = (12, 8, 4)[min(attempt, 2)]
        for key in ("experiment", "condition", "strain", "orig"):
            if local_ctx.get(key):
                local_ctx[key] = local_ctx[key][:limit]
    # last resort: date + seq only
    for seq in range(1, 10000):
        name = f"{ctx.get('date', 'file')}_{seq:04d}{suffix}"
        if name not in taken and not (dest_dir / name).exists():
            return name
    raise RuntimeError("Could not find a free filename")
