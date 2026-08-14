"""Register a newly-stable acquisition file: DB row + metadata + thumbnail + raw XML."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ..config import AppConfig
from ..db import repo
from ..dustref import is_dust_filename
from ..metadata import czi as czimeta
from ..metadata.thumbs import make_thumbnail
from ..paths import AppPaths

log = logging.getLogger(__name__)


def ingest_stable_file(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    paths: AppPaths,
    session_id: int,
    path: Path,
) -> int:
    meta = czimeta.extract(path)
    file_id = repo.add_file(
        conn, session_id, str(path), size_bytes=meta.size_bytes, acquired_at=meta.acquired_at
    )
    db_meta = meta.to_db_dict()
    stem = f"f{file_id}"
    if meta.raw_xml:
        db_meta["raw_xml_path"] = czimeta.save_raw_xml(meta.raw_xml, paths.xml_dir, stem)
    thumb = make_thumbnail(path, paths.thumbs_dir, stem)
    if thumb:
        db_meta["thumbnail_path"] = thumb
    repo.set_file_metadata(conn, file_id, db_meta)
    if is_dust_filename(path.name, cfg):
        repo.set_file_status(conn, file_id, "dust_ref")
    log.info("Ingested %s (file id %d, objective=%s)", path.name, file_id, meta.objective_name)
    return file_id
