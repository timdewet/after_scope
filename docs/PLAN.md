# after_scope increment: pre-session experiment declaration + save-time annotation

## Context

The MVP (watchdog + pre-use/end-of-session wizards + CZI metadata + organize + dashboard)
is built and verified: 79 unit tests + the macOS E2E simulate all green. New user request:
metadata should be capturable **before/during** the session, not only at the end —

1. **When ZEN boots**, the user can declare what they're about to image (experiment,
   strain, condition, coverslip); the tool creates the structured directory up front.
2. **When a CZI is saved**, a prompt records what that file is.

Decisions made with the user:
- **Save prompt = corner toast**: small, always-on-top, never steals keyboard focus,
  auto-dismisses in ~15 s applying the declared defaults; click only to override.
  (Blocking dialogs during acquisition were explicitly rejected.)
- **Pre-created directory = scratch session folder** (e.g. `D:\ScratchData\20260814_TdW_efflux-timelapse\`):
  ZEN keeps writing to fast local disk, no Dropbox sync churn mid-acquisition; the existing
  end-of-session filing step moves everything into the Dropbox tree as before.

Payoff: files are auto-tagged as they land, and the end-of-session wizard becomes a quick
review instead of data entry.

## Design

### 1. Schema — `src/after_scope/db/schema/0002_session_plan.sql`
New migration (the runner in [connection.py](../../Library/CloudStorage/Dropbox-MMRU/Timothy%20de%20Wet/Science/Admin/2026/Code/after_scope/src/after_scope/db/connection.py) already handles NNNN files):
```sql
ALTER TABLE sessions ADD COLUMN planned_experiment_id INTEGER REFERENCES experiments(id);
ALTER TABLE sessions ADD COLUMN planned_strain TEXT;
ALTER TABLE sessions ADD COLUMN planned_condition TEXT;
ALTER TABLE sessions ADD COLUMN planned_coverslip TEXT;
ALTER TABLE sessions ADD COLUMN planned_notes TEXT;
ALTER TABLE sessions ADD COLUMN planned_dir TEXT;
```

### 2. Config (`config.py`)
```yaml
declare:  { enabled: true, create_scratch_dir: true, scratch_root: null }  # null -> first watch_dir
annotate: { mode: toast, timeout_seconds: 15 }                             # toast | off
```

### 3. Repo (`db/repo.py`)
- `set_session_plan(conn, sid, experiment_id, strain, condition, coverslip, notes, planned_dir)`
- `fill_file_defaults(conn, file_id, *, experiment_id, user_id, strain, condition, coverslip)` —
  **fill-only semantics** (`COALESCE(existing, ?)`, the reverse of `set_file_user_meta`), so
  plan defaults never overwrite anything a user typed on the toast or in the end wizard.

### 4. ExperimentPage (`wizard/pages/declare.py`)
Inserted after UserPage in the pre-use flow (`build_pages`, reasons start/handover); also a
standalone flow `--reason declare` = [ExperimentPage] for mid-session changes from the tray.
- Fields: experiment (editable combo seeded from `repo.list_experiment_names`), strain,
  condition, coverslip/prep, notes.
- "Same as my last session" button: prefills from this user's most recent session plan.
- "Skip — not sure yet": declaring is optional; page validates empty as OK.
- `save()`: `get_or_create_experiment` → `set_session_plan`; if `declare.create_scratch_dir`,
  create `{scratch_root}/{date}_{initials}_{experiment}/` using the existing
  `naming.build_context` + `sanitize_token` (`metadata/naming.py`), store as `planned_dir`,
  audit. `auto_fill()`: experiment `e2e-experiment`, strain `TEST1`, condition `ctrl`
  (keeps existing E2E assertions coherent).

### 5. Watchdog (`watchdog/service.py`, `watchdog/file_scan.py`)
- `AcquisitionScanner.add_extra_dir(path)`: session-scoped watch root (the planned scratch
  dir may sit outside configured watch_dirs); cleared by `scanner.reset()`.
- After the pre-use wizard returns in `_on_zen_start` (and after whoami handover resync):
  read `planned_dir` from the session row → `add_extra_dir`.
- In `_scan_if_due`, after `ingest_stable_file`: apply `fill_file_defaults` from the session
  plan (+ session user), then — if `annotate.mode == 'toast'` and the file is not a
  dust_ref — collect the new file ids and fire the toast **without blocking**:
  new injectable `spawn_toast(ctx, session_id, file_ids)`, default `subprocess.Popen`
  (fire-and-forget; never `wait()` in the step loop), one toast per sweep batch.
- Tray menu (`watchdog/tray.py`): add "Set experiment details…" → sets a
  `declare_requested` flag consumed by `step()` in ACTIVE (same pattern as takeover) →
  blocking spawn of `--reason declare`; re-read planned_dir after.

### 6. Annotate toast (`wizard/toast.py`)
Not a WizardWindow — a small frameless widget, bottom-right, flags
`Qt.Tool | WindowStaysOnTopHint | WindowDoesNotAcceptFocus` (never steals focus from ZEN).
- Shows the batch: thumbnail, filename, current tags ("Snap-003 → efflux-timelapse / MSM155 — click to change").
- Auto-closes after `annotate.timeout_seconds` (defaults were already applied at ingest, so
  silent close = accept). Clicking expands inline fields (experiment/strain/condition/
  coverslip/notes) + Apply → `set_file_user_meta` on the listed files.
- CLI routing in `__main__.py`: `wizard --reason annotate --file-ids 12,13` → `run_toast`;
  `--reason` choices gain `annotate` and `declare`. Always exits 0.

### 7. Untouched
End-of-session FilesPage/NamingPage already display and file whatever the rows carry —
prefilled rows just mean less typing. Dashboard, exports, migration, deploy: unchanged
(0002 migration applies automatically on first run after update).

## Files touched
- `src/after_scope/db/schema/0002_session_plan.sql` (new)
- `src/after_scope/db/repo.py` (+2 functions)
- `src/after_scope/config.py` (DeclareCfg, AnnotateCfg)
- `src/after_scope/wizard/pages/declare.py` (new), `wizard/controller.py` (build_pages),
  `wizard/toast.py` (new), `wizard/app.py` + `__main__.py` (routing, --file-ids)
- `src/after_scope/watchdog/service.py`, `watchdog/file_scan.py`, `watchdog/tray.py`
- `config/config.example.yaml`, `config/config.simulate.yaml`, `README.md`

## Verification
- **Unit**: migration 0002 upgrades an existing v1 DB; `fill_file_defaults` never overwrites
  user-entered values; ExperimentPage save creates a sanitized scratch dir + plan row, skip
  leaves no plan; scanner `add_extra_dir` picks up files outside configured watch roots and
  clears on reset; watchdog applies plan defaults on ingest and fires `spawn_toast` (stub)
  with the right file ids — and not for dust files; toast widget smoke test offscreen
  (build, apply-edit writes DB, timer close).
- **E2E** (`tests/e2e/test_simulated_session.py` extended): pre-use auto-declares → assert
  scratch session dir created; drop one CZI *into the planned dir* (proves session-scoped
  watching) and the others in scratch root; assert ingested rows carry plan defaults before
  the end wizard runs; existing final assertions (template names, dashboard, completion)
  stay green.
- **Manual simulate loop** on macOS per README: declare at fake-ZEN start, watch the toast
  appear on a simulated save, confirm end wizard shows prefilled rows.
