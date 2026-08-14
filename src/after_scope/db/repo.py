"""Plain-SQL data access functions (no ORM).

Every function takes the connection first; writes commit immediately — the wizard
persists page-by-page so a crash never loses answered pages.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..util import now_iso

# --- audit -------------------------------------------------------------------------


def audit(conn: sqlite3.Connection, event: str, **detail: Any) -> None:
    with conn:
        conn.execute(
            "INSERT INTO audit_log (ts, event, detail_json) VALUES (?,?,?)",
            (now_iso(), event, json.dumps(detail, default=str) if detail else None),
        )


# --- users -------------------------------------------------------------------------


def seed_roster(conn: sqlite3.Connection, roster: list[dict[str, Any]]) -> int:
    """Insert roster entries that don't exist yet (matched by initials). Returns #added."""
    added = 0
    with conn:
        for entry in roster:
            cur = conn.execute(
                """INSERT INTO users (full_name, initials, email, source, created_at)
                   VALUES (?,?,?,'roster',?)
                   ON CONFLICT(initials) DO NOTHING""",
                (entry["name"], entry["initials"], entry.get("email"), now_iso()),
            )
            added += cur.rowcount
    return added


def add_user(
    conn: sqlite3.Connection, full_name: str, initials: str, email: str | None = None
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO users (full_name, initials, email, source, created_at)
               VALUES (?,?,?,'wizard',?)""",
            (full_name, initials, email, now_iso()),
        )
    return cur.lastrowid


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def list_users(conn: sqlite3.Connection, active_only: bool = True) -> list[sqlite3.Row]:
    q = "SELECT * FROM users"
    if active_only:
        q += " WHERE active=1"
    return conn.execute(q + " ORDER BY full_name").fetchall()


def recent_users(conn: sqlite3.Connection, limit: int = 6) -> list[sqlite3.Row]:
    """Active users ordered by most recent session, then name — for the roster picker."""
    return conn.execute(
        """SELECT u.*, MAX(s.started_at) AS last_used
           FROM users u LEFT JOIN sessions s ON s.user_id = u.id
           WHERE u.active = 1
           GROUP BY u.id
           ORDER BY last_used DESC NULLS LAST, u.full_name
           LIMIT ?""",
        (limit,),
    ).fetchall()


# --- sessions ----------------------------------------------------------------------


def open_session(
    conn: sqlite3.Connection,
    zen_pid: int | None,
    started_at: str | None = None,
    machine: str = "",
    app_version: str = "",
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO sessions (machine, app_version, zen_pid, started_at, status)
               VALUES (?,?,?,?,'open')""",
            (machine, app_version, zen_pid, started_at or now_iso()),
        )
    return cur.lastrowid


def get_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()


def get_open_session(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE status='open' ORDER BY id DESC LIMIT 1"
    ).fetchone()


def set_session_user(
    conn: sqlite3.Connection, session_id: int, user_id: int, method: str
) -> None:
    with conn:
        conn.execute(
            "UPDATE sessions SET user_id=?, identify_method=? WHERE id=?",
            (user_id, method, session_id),
        )


def set_arrival_state(conn: sqlite3.Connection, session_id: int, ok: bool) -> None:
    with conn:
        conn.execute(
            "UPDATE sessions SET arrival_state_ok=? WHERE id=?", (1 if ok else 0, session_id)
        )


def end_session(
    conn: sqlite3.Connection,
    session_id: int,
    ended_reason: str,
    ended_at: str | None = None,
    zen_exit_code: int | None = None,
    status: str = "awaiting_checklist",
    incomplete_reason: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE sessions SET ended_at=?, ended_reason=?, zen_exit_code=?,
                                   status=?, incomplete_reason=?
               WHERE id=?""",
            (
                ended_at or now_iso(),
                ended_reason,
                zen_exit_code,
                status,
                incomplete_reason,
                session_id,
            ),
        )


def set_session_status(
    conn: sqlite3.Connection,
    session_id: int,
    status: str,
    incomplete_reason: str | None = None,
) -> None:
    with conn:
        if status == "complete":
            conn.execute(
                """UPDATE sessions SET status='complete', incomplete_reason=NULL,
                                       checklist_completed_at=? WHERE id=?""",
                (now_iso(), session_id),
            )
        else:
            conn.execute(
                "UPDATE sessions SET status=?, incomplete_reason=? WHERE id=?",
                (status, incomplete_reason, session_id),
            )


def set_session_plan(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    experiment_id: int | None,
    strain: str | None,
    condition: str | None,
    coverslip: str | None,
    notes: str | None,
    planned_dir: str | None,
    imaging: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE sessions SET planned_experiment_id=?, planned_strain=?,
                                   planned_condition=?, planned_coverslip=?,
                                   planned_notes=?, planned_dir=?, planned_imaging=?
               WHERE id=?""",
            (experiment_id, strain, condition, coverslip, notes, planned_dir,
             imaging, session_id),
        )


def set_session_purpose(conn: sqlite3.Connection, session_id: int, purpose: str) -> None:
    """Record a quick session purpose (viewing / analysis / quick look) without
    touching the rest of the plan; existing notes are preserved."""
    with conn:
        conn.execute(
            """UPDATE sessions
               SET planned_notes = COALESCE(NULLIF(planned_notes, ''), ?)
               WHERE id=?""",
            (purpose, session_id),
        )


def last_session_plan_for_user(
    conn: sqlite3.Connection, user_id: int
) -> sqlite3.Row | None:
    """Most recent session by this user that had a declared plan."""
    return conn.execute(
        """SELECT s.*, e.name AS planned_experiment_name
           FROM sessions s LEFT JOIN experiments e ON e.id = s.planned_experiment_id
           WHERE s.user_id=? AND (s.planned_experiment_id IS NOT NULL
                                  OR s.planned_strain IS NOT NULL)
           ORDER BY s.id DESC LIMIT 1""",
        (user_id,),
    ).fetchone()


def fill_file_defaults(
    conn: sqlite3.Connection,
    file_id: int,
    *,
    experiment_id: int | None = None,
    user_id: int | None = None,
    strain: str | None = None,
    condition: str | None = None,
    coverslip: str | None = None,
    notes: str | None = None,
) -> None:
    """Fill-only: the reverse of set_file_user_meta — existing values always win,
    so plan defaults never overwrite anything a user typed."""
    with conn:
        conn.execute(
            """UPDATE files SET experiment_id=COALESCE(experiment_id, ?),
                                user_id=COALESCE(user_id, ?),
                                strain=COALESCE(strain, ?),
                                condition=COALESCE(condition, ?),
                                coverslip=COALESCE(coverslip, ?),
                                notes=COALESCE(notes, ?)
               WHERE id=?""",
            (experiment_id, user_id, strain, condition, coverslip, notes, file_id),
        )


def reopen_session(conn: sqlite3.Connection, session_id: int, zen_pid: int | None = None) -> None:
    """User chose 'I'm restarting ZEN' — resurrect the session as open."""
    with conn:
        conn.execute(
            """UPDATE sessions SET status='open', ended_at=NULL, ended_reason=NULL,
                                   zen_exit_code=NULL, incomplete_reason=NULL,
                                   zen_pid=COALESCE(?, zen_pid)
               WHERE id=?""",
            (zen_pid, session_id),
        )


def previous_session(conn: sqlite3.Connection, before_session_id: int) -> sqlite3.Row | None:
    """The session immediately before the given one (for found-dirty attribution)."""
    return conn.execute(
        "SELECT * FROM sessions WHERE id < ? ORDER BY id DESC LIMIT 1",
        (before_session_id,),
    ).fetchone()


def incomplete_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Sessions whose checklist was never completed — the nag queue, oldest first."""
    return conn.execute(
        """SELECT * FROM sessions
           WHERE status IN ('incomplete', 'awaiting_checklist') AND ended_at IS NOT NULL
           ORDER BY id"""
    ).fetchall()


def recover_orphans(conn: sqlite3.Connection) -> int:
    """Close sessions left 'open' by a crash/reboot. Returns number recovered."""
    with conn:
        cur = conn.execute(
            """UPDATE sessions
               SET status='incomplete', incomplete_reason='interrupted',
                   ended_reason='interrupted', ended_at=COALESCE(ended_at, ?)
               WHERE status='open'""",
            (now_iso(),),
        )
    return cur.rowcount


def list_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.*, u.full_name AS user_name, u.initials AS user_initials
           FROM sessions s LEFT JOIN users u ON u.id = s.user_id
           ORDER BY s.id"""
    ).fetchall()


# --- experiments -------------------------------------------------------------------


def get_or_create_experiment(
    conn: sqlite3.Connection, name: str, user_id: int | None
) -> int:
    row = conn.execute(
        "SELECT id FROM experiments WHERE name=? AND user_id IS ?", (name, user_id)
    ).fetchone()
    if row:
        return row["id"]
    with conn:
        cur = conn.execute(
            "INSERT INTO experiments (name, user_id, created_at) VALUES (?,?,?)",
            (name, user_id, now_iso()),
        )
    return cur.lastrowid


def list_experiment_names(conn: sqlite3.Connection, limit: int = 50) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM experiments ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r["name"] for r in rows]


_RECENT_VALUE_COLUMNS = {"strain", "condition", "coverslip"}


def recent_file_values(conn: sqlite3.Connection, column: str, limit: int = 8) -> list[str]:
    """Most recently used distinct values of a files column — feeds the quick-pick
    chips and completers in the wizard. Column name is whitelisted (no user input)."""
    if column not in _RECENT_VALUE_COLUMNS:
        raise ValueError(f"unsupported column: {column}")
    rows = conn.execute(
        f"""SELECT {column} AS v, MAX(id) AS last_id FROM files
            WHERE {column} IS NOT NULL AND {column} != ''
            GROUP BY {column} ORDER BY last_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [r["v"] for r in rows]


# --- files -------------------------------------------------------------------------


def add_file(
    conn: sqlite3.Connection,
    session_id: int | None,
    path: str,
    *,
    origin: str = "session",
    status: str = "new",
    size_bytes: int | None = None,
    acquired_at: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO files (session_id, origin, status, original_path, current_path,
                                  size_bytes, acquired_at, created_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(original_path, session_id) DO NOTHING""",
            (session_id, origin, status, path, path, size_bytes, acquired_at, now_iso()),
        )
    if cur.lastrowid and cur.rowcount:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM files WHERE original_path=? AND session_id IS ?", (path, session_id)
    ).fetchone()
    return row["id"]


def set_file_metadata(conn: sqlite3.Connection, file_id: int, meta: dict[str, Any]) -> None:
    """Update extraction-derived columns from a metadata dict (keys = column names)."""
    cols = [
        "acquired_at",
        "size_bytes",
        "thumbnail_path",
        "raw_xml_path",
        "objective_name",
        "magnification",
        "na",
        "immersion",
        "pixel_size_um",
        "channels_json",
        "dims_json",
    ]
    sets = [f"{c}=?" for c in cols if c in meta]
    vals = [meta[c] for c in cols if c in meta]
    if not sets:
        return
    with conn:
        conn.execute(f"UPDATE files SET {', '.join(sets)} WHERE id=?", (*vals, file_id))


def set_file_user_meta(
    conn: sqlite3.Connection,
    file_id: int,
    *,
    experiment_id: int | None = None,
    user_id: int | None = None,
    strain: str | None = None,
    condition: str | None = None,
    coverslip: str | None = None,
    sample_prep: str | None = None,
    notes: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """UPDATE files SET experiment_id=COALESCE(?, experiment_id),
                                user_id=COALESCE(?, user_id),
                                strain=COALESCE(?, strain),
                                condition=COALESCE(?, condition),
                                coverslip=COALESCE(?, coverslip),
                                sample_prep=COALESCE(?, sample_prep),
                                notes=COALESCE(?, notes)
               WHERE id=?""",
            (experiment_id, user_id, strain, condition, coverslip, sample_prep, notes, file_id),
        )


def set_file_status(conn: sqlite3.Connection, file_id: int, status: str) -> None:
    with conn:
        conn.execute("UPDATE files SET status=? WHERE id=?", (status, file_id))


def session_files(
    conn: sqlite3.Connection, session_id: int, include_excluded: bool = True
) -> list[sqlite3.Row]:
    q = "SELECT * FROM files WHERE session_id=?"
    if not include_excluded:
        q += " AND status != 'excluded'"
    return conn.execute(q + " ORDER BY COALESCE(acquired_at, created_at), id", (session_id,)).fetchall()


def get_file(conn: sqlite3.Connection, file_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()


def record_move(
    conn: sqlite3.Connection, file_id: int, from_path: str, to_path: str, verified: bool
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO file_moves (file_id, moved_at, from_path, to_path, verified)
               VALUES (?,?,?,?,?)""",
            (file_id, now_iso(), from_path, to_path, 1 if verified else 0),
        )
        conn.execute("UPDATE files SET current_path=? WHERE id=?", (to_path, file_id))
    return cur.lastrowid


def session_oil_objectives(conn: sqlite3.Connection, session_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT objective_name FROM files
           WHERE session_id=? AND objective_name IS NOT NULL
             AND (LOWER(immersion) LIKE '%oil%' OR LOWER(objective_name) LIKE '%oil%')""",
        (session_id,),
    ).fetchall()
    return [r["objective_name"] for r in rows]


# --- checklist / maintenance -------------------------------------------------------


def save_checklist_response(
    conn: sqlite3.Connection,
    session_id: int,
    item_key: str,
    label: str,
    response: Any,
    flagged: bool = False,
) -> None:
    with conn:
        conn.execute(
            """INSERT INTO checklist_responses
                   (session_id, item_key, label_snapshot, response_json, flagged, answered_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(session_id, item_key) DO UPDATE SET
                   response_json=excluded.response_json, flagged=excluded.flagged,
                   answered_at=excluded.answered_at, label_snapshot=excluded.label_snapshot""",
            (session_id, item_key, label, json.dumps(response), 1 if flagged else 0, now_iso()),
        )


def checklist_responses(conn: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM checklist_responses WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()


def add_maintenance_event(
    conn: sqlite3.Connection,
    type_: str,
    *,
    objective_name: str | None = None,
    solvent: str | None = None,
    session_id: int | None = None,
    user_id: int | None = None,
    notes: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO maintenance_events
                   (type, objective_name, solvent, session_id, user_id, notes, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (type_, objective_name, solvent, session_id, user_id, notes, now_iso()),
        )
    return cur.lastrowid


def last_solvent_clean(
    conn: sqlite3.Connection, objective_name: str | None = None
) -> sqlite3.Row | None:
    if objective_name:
        return conn.execute(
            """SELECT * FROM maintenance_events WHERE type='solvent_clean' AND objective_name=?
               ORDER BY created_at DESC LIMIT 1""",
            (objective_name,),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM maintenance_events WHERE type='solvent_clean' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()


def maintenance_events(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT m.*, u.full_name AS user_name FROM maintenance_events m
           LEFT JOIN users u ON u.id = m.user_id ORDER BY m.created_at DESC, m.id DESC"""
    ).fetchall()


# --- incidents ---------------------------------------------------------------------


def add_incident(
    conn: sqlite3.Connection,
    *,
    session_id: int | None,
    attributed_session_id: int | None = None,
    reported_by: int | None = None,
    category: str = "other",
    severity: str = "minor",
    description: str | None = None,
    photo_path: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO incidents (session_id, attributed_session_id, reported_by, category,
                                      severity, description, photo_path, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                session_id,
                attributed_session_id,
                reported_by,
                category,
                severity,
                description,
                photo_path,
                now_iso(),
            ),
        )
    return cur.lastrowid


def open_incidents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.*, u.full_name AS reporter_name FROM incidents i
           LEFT JOIN users u ON u.id = i.reported_by
           WHERE i.status='open' ORDER BY i.created_at DESC"""
    ).fetchall()


def list_incidents(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.*, u.full_name AS reporter_name FROM incidents i
           LEFT JOIN users u ON u.id = i.reported_by
           ORDER BY i.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def resolve_incident(
    conn: sqlite3.Connection, incident_id: int, resolved_by: int | None = None
) -> None:
    with conn:
        conn.execute(
            "UPDATE incidents SET status='resolved', resolved_at=?, resolved_by=? WHERE id=?",
            (now_iso(), resolved_by, incident_id),
        )


# --- dust refs ---------------------------------------------------------------------


def add_dust_ref(
    conn: sqlite3.Connection,
    *,
    session_id: int | None,
    file_id: int | None,
    objective_name: str | None,
    method: str,
    notes: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO dust_refs (session_id, file_id, objective_name, method, notes, created_at)
               VALUES (?,?,?,?,?,?)""",
            (session_id, file_id, objective_name, method, notes, now_iso()),
        )
    return cur.lastrowid


def dust_refs(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT d.*, f.thumbnail_path, f.current_path
           FROM dust_refs d LEFT JOIN files f ON f.id = d.file_id
           ORDER BY d.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def session_dust_ref(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT d.*, f.thumbnail_path FROM dust_refs d LEFT JOIN files f ON f.id=d.file_id
           WHERE d.session_id=? AND d.method != 'skipped' ORDER BY d.id DESC LIMIT 1""",
        (session_id,),
    ).fetchone()


# --- migration manifests -----------------------------------------------------------


def record_manifest(
    conn: sqlite3.Connection,
    manifest_name: str,
    *,
    submitted_by: str | None,
    submitted_at: str | None,
    status: str,
    file_count: int | None = None,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """INSERT INTO migration_manifests
                   (manifest_name, submitted_by, submitted_at, ingested_at, status, file_count, error)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(manifest_name) DO UPDATE SET
                   ingested_at=excluded.ingested_at, status=excluded.status,
                   file_count=excluded.file_count, error=excluded.error""",
            (manifest_name, submitted_by, submitted_at, now_iso(), status, file_count, error),
        )
