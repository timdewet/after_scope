"""SQLite connection setup + schema migrations."""

from __future__ import annotations

import re
import sqlite3
from importlib import resources
from pathlib import Path

MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def connect(db_path: Path | str) -> sqlite3.Connection:
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _schema_files() -> list[tuple[int, str, str]]:
    """(number, name, sql) for every packaged schema/NNNN_*.sql, sorted."""
    out = []
    pkg = resources.files("after_scope.db") / "schema"
    for entry in pkg.iterdir():
        m = MIGRATION_RE.match(entry.name)
        if m:
            out.append((int(m.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    return sorted(out)


def _statements(sql: str) -> list[str]:
    """Split a schema file into statements (line comments stripped).

    Migration files are under our control: no string literals containing ';'.
    Avoids executescript(), whose implicit COMMIT would break per-migration
    transactions.
    """
    lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        lines.append(line[:idx] if idx >= 0 else line)
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply pending schema files (NNNN > PRAGMA user_version), each in one transaction."""
    applied = []
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, name, sql in _schema_files():
        if number <= current:
            continue
        with conn:  # transaction per migration
            for stmt in _statements(sql):
                conn.execute(stmt)
            conn.execute(f"PRAGMA user_version = {number}")
        applied.append(name)
        current = number
    return applied


def open_db(db_path: Path | str) -> sqlite3.Connection:
    conn = connect(db_path)
    apply_migrations(conn)
    return conn
