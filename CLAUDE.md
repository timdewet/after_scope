# after_scope — project context

End-of-session compliance & metadata tool for the lab's shared Zeiss microscope
(ZEN Blue, Windows scope PC). Read README.md for the user-facing overview.

## State (as of 2026-08-14)

Built and verified on macOS: 89 tests green (`pytest`), including an end-to-end
simulated session (`tests/e2e/`). **Nothing has run on real Windows hardware yet** —
that is the next milestone. The Windows-specific code paths that need first-run
verification: `watchdog/win32_watch.py` (exit codes via OpenProcess),
`watchdog/idle.py` (GetLastInputInfo), `watchdog/tray.py` (pystray),
`watchdog/single_instance.py` (named mutex), and everything in `deploy/windows/`.
The first-deploy smoke checklist is at the bottom of README.md.

## Architecture in one paragraph

`after_scope watchdog` (resident, never imports Qt) polls for Zen.exe, opens a session
row, sweeps `watch_dirs` for new .czi files (two-sweep stability + shared-read check),
extracts metadata header-only (pylibCZIrw → czifile fallback; parser in
`metadata/czi.py` is pure XML), and spawns wizard **processes** at lifecycle points:
`--reason start` (pre-use: user, experiment declaration, arrival check, issues board),
`--reason close|crash|nag` (end-of-session: files table → rename/move → cleaning
checklist → dust ref → incidents → summary), `--reason whoami` (idle re-confirm /
handover), `--reason declare` (tray-initiated), `--reason annotate` (corner toast when
files land). Exit codes signal outcomes (0 done, 2 skipped, 3 restarting-ZEN,
4 handover). SQLite lives on the local disk (`paths.py`); Dropbox gets only derived
artifacts: CSV exports, nightly backups, and the self-contained HTML dashboard
(`report/dashboard.py`).

## Conventions

- Plain SQL in `db/repo.py` (no ORM); migrations = numbered files in `db/schema/`
  applied via `PRAGMA user_version` — never edit an existing migration.
- Timestamps: local naive ISO strings (`util.now_iso`).
- Watchdog is a `step()`-driven state machine (IDLE/ACTIVE/DORMANT/ABANDONED/EXITING/
  WAIT_RESTART) with injected clock/idle/process-watcher/spawners — tests drive it
  synchronously with fakes (`tests/test_watchdog.py`).
- Plan defaults use **fill-only** semantics (`repo.fill_file_defaults`): never
  overwrite user-entered values. `set_file_user_meta` is the overwriting variant.
- Dormancy = no keyboard input AND no new files (timelapses must not go dormant).
- Never block ZEN, never physically prevent anything: enforcement is logged skips,
  nag-at-next-start, and dashboard visibility.
- The wizard never opens modal dialogs from `closeEvent` when invisible (test
  teardown hangs otherwise — see `WizardWindow.closeEvent`).

## Commands

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows
pytest                          # full suite incl. e2e (~8 s)
ruff check src tests scripts
after-scope --config config/config.simulate.yaml watchdog       # simulate loop
after-scope --config <cfg> doctor                               # env validation
```

On Windows, build + install: `deploy/build.ps1`, then `deploy/windows/install.ps1`
(admin; registers the Task Scheduler keep-alive and the config pointer file).

## Next steps (in order)

1. On the scope PC (or any Windows box): clone, venv, `pytest` — confirm the suite
   passes on Windows (path handling, Qt offscreen).
2. Run the simulate loop on Windows (fake_zen + simulate_acquisition) to verify the
   real tray icon, idle monitor, and toast focus behavior.
3. `deploy/build.ps1` → `install.ps1` on the scope PC; walk the README smoke checklist.
4. Config for production: real `watch_dirs`, Dropbox root, roster, approved solvent +
   nudge cadence, create the ZEN preset `AfterScope_DustRef` (100x brightfield,
   `dustref_` prefix), one-time `_legacy/` move via Dropbox web UI.
5. v1.1 backlog: migration wizard GUI (manifest + ingest already in `migrate/`),
   dashboard trend charts, per-file user reassignment; v1.2: ZEN API dust auto-snap.
