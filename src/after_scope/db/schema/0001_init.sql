-- after_scope initial schema.
-- Timestamps are local naive ISO strings ("YYYY-MM-DDTHH:MM:SS") — single-machine tool.

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    initials TEXT NOT NULL UNIQUE,
    email TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'roster',      -- roster | wizard
    created_at TEXT NOT NULL
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    machine TEXT,
    app_version TEXT,
    zen_pid INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    ended_reason TEXT,                          -- zen_close | handover | idle_timeout | crash | interrupted
    zen_exit_code INTEGER,
    user_id INTEGER REFERENCES users(id),
    identify_method TEXT,                       -- roster | new | manual
    arrival_state_ok INTEGER,                   -- 1 ok, 0 found dirty, NULL unanswered
    status TEXT NOT NULL DEFAULT 'open',        -- open | awaiting_checklist | complete | incomplete
    incomplete_reason TEXT,                     -- skipped | wizard_crash | interrupted | handover | idle_timeout
    checklist_completed_at TEXT
);

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    description TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (name, user_id)
);

CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id), -- NULL for migrated files
    origin TEXT NOT NULL DEFAULT 'session',     -- session | migration
    experiment_id INTEGER REFERENCES experiments(id),
    status TEXT NOT NULL DEFAULT 'new',         -- new | indexed | moved | copied | excluded | dust_ref | move_failed | missing
    original_path TEXT NOT NULL,
    current_path TEXT NOT NULL,
    acquired_at TEXT,
    size_bytes INTEGER,
    thumbnail_path TEXT,
    raw_xml_path TEXT,
    objective_name TEXT,
    magnification REAL,
    na REAL,
    immersion TEXT,
    pixel_size_um REAL,
    channels_json TEXT,
    dims_json TEXT,
    user_id INTEGER REFERENCES users(id),
    strain TEXT,
    condition TEXT,
    coverslip TEXT,
    sample_prep TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (original_path, session_id)
);
CREATE INDEX idx_files_session ON files(session_id);
CREATE INDEX idx_files_current_path ON files(current_path);

CREATE TABLE file_moves (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id),
    moved_at TEXT NOT NULL,
    from_path TEXT NOT NULL,
    to_path TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    undone_at TEXT
);

CREATE TABLE checklist_responses (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    item_key TEXT NOT NULL,
    label_snapshot TEXT,
    response_json TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    answered_at TEXT NOT NULL,
    UNIQUE (session_id, item_key)
);

CREATE TABLE maintenance_events (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,                         -- solvent_clean | other
    objective_name TEXT,
    solvent TEXT,
    session_id INTEGER REFERENCES sessions(id),
    user_id INTEGER REFERENCES users(id),
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE incidents (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),             -- session in which it was reported
    attributed_session_id INTEGER REFERENCES sessions(id),  -- session held responsible (found-dirty)
    reported_by INTEGER REFERENCES users(id),
    category TEXT NOT NULL DEFAULT 'other',
    -- found_dirty_oil | found_sample | not_parked | dirty_objective | problem | other
    severity TEXT NOT NULL DEFAULT 'minor',     -- minor | major | blocking
    description TEXT,
    photo_path TEXT,
    status TEXT NOT NULL DEFAULT 'open',        -- open | resolved
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

CREATE TABLE dust_refs (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    file_id INTEGER REFERENCES files(id),
    objective_name TEXT,
    method TEXT NOT NULL,                       -- manual | zen_api | skipped
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE migration_manifests (
    id INTEGER PRIMARY KEY,
    manifest_name TEXT NOT NULL UNIQUE,
    submitted_by TEXT,
    submitted_at TEXT,
    ingested_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',     -- pending | ingested | failed
    file_count INTEGER,
    error TEXT
);

CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    detail_json TEXT
);
