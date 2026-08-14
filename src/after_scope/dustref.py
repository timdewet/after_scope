"""Dust-reference handling (manual capture path).

The user acquires a blank field of view with the standardized ZEN preset (100x,
brightfield) saved with the `dustref_` prefix; the scanner tags matching files and
this module registers them as dust references.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import AppConfig
from .db import repo


def is_dust_filename(name: str, cfg: AppConfig) -> bool:
    return Path(name).name.lower().startswith(cfg.dust.filename_prefix.lower())


def register_session_dust_refs(conn: sqlite3.Connection, session_id: int) -> list[int]:
    """Create dust_refs rows for the session's tagged files (idempotent)."""
    created = []
    for row in repo.session_files(conn, session_id):
        if row["status"] != "dust_ref":
            continue
        exists = conn.execute(
            "SELECT 1 FROM dust_refs WHERE file_id=?", (row["id"],)
        ).fetchone()
        if exists:
            continue
        created.append(
            repo.add_dust_ref(
                conn,
                session_id=session_id,
                file_id=row["id"],
                objective_name=row["objective_name"],
                method="manual",
            )
        )
    return created


def record_skip(conn: sqlite3.Connection, session_id: int, notes: str | None = None) -> None:
    if not repo.session_dust_ref(conn, session_id):
        repo.add_dust_ref(
            conn, session_id=session_id, file_id=None, objective_name=None,
            method="skipped", notes=notes,
        )
