# after_scope — project context

End-of-session compliance & metadata tool for the lab's shared Zeiss microscope
(ZEN Blue, Windows scope PC). Read README.md for the user-facing overview.

## State (as of 2026-08-14)

Verified on Windows 10: 89 tests green (`pytest`), and the simulate loop ran
end-to-end on real hardware — tray icon (pystray), GetLastInputInfo idle monitor,
named-mutex single instance, Win32 exit codes (clean vs taskkill crash), CZI
ingest + toast, and the copy→verify→delete move into the Dropbox tree.
`config/config.simulate.win.yaml` is the simulate profile with the tray enabled.
Still needing eyes-on: tray menu actions (takeover/declare), idle→whoami flow,
and the deploy scripts (`deploy/windows/`) — smoke checklist at the bottom of
README.md. Dev-only quirk: the venv `python.exe` is a launcher, so cmdline-marker
detection finds the child interpreter; irrelevant for the real `Zen.exe`.

Wizard/toast styling is a token-based design system in `wizard/ui/`
(`tokens.py` palettes light+dark, `theme.py` generates the whole QSS,
`stepper.py` step indicator) — ported from MycoMorph's GUI. No `.qss` files;
change tokens, not widget stylesheets.

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

## Deployed (2026-08-14)

Installed on the scope PC: bundle at `C:\Program Files\AfterScope`, data at
`C:\ProgramData\AfterScope`, Task Scheduler keep-alive `AfterScopeWatchdog`
(logon trigger + 5-min repeat), master config at
`C:\Users\User\MMRU Dropbox\Network Data\Microscopy\AfterScope\config.yaml`
(pointer file in ProgramData). Dropbox root is `...\Network Data\Microscopy`
(the team-space root has a filesystem Deny ACL — top-level folders can only be
made in the Dropbox web UI). Frozen-build fixes that must not regress:
`deploy/launcher.py` (absolute-import entry + six/shiboken import guard) and
BOM-less `config.path` (`paths.py` reads utf-8-sig; install.ps1 writes via
`[IO.File]::WriteAllText`). Updates: build, then `deploy/windows/update.ps1`.

**Running (2026-08-20).** To pause: tray menu → Pause, or exit the watchdog and
`Disable-ScheduledTask -TaskName AfterScopeWatchdog` (admin). All work is on the
`windows-deploy` branch (PR #1); the deployed bundle matches its head.
Config gotcha: YAML parses bare `off`/`on` as booleans — literal fields coerce
them now, but quote `'off'` in configs anyway. The last-known-good config cache
is keyed by config path (a test config once poisoned the global cache and sent
wizards to a pytest temp DB — silent and nasty; doctor now flags fallback).

## Next steps (in order)

1. Remaining smoke items (README checklist): real ZEN open/close/crash cycle,
   wizard-over-ZEN-splash, sleep/resume, non-admin user, Defender quiet for a week
   (consider `Add-MpPreference -ExclusionPath 'C:\Program Files\AfterScope'`).
2. Create the ZEN preset `AfterScope_DustRef` (100x brightfield, `dustref_` prefix);
   one-time `_legacy/` move via Dropbox web UI; extend the roster as users join.
3. v1.1 backlog: migration wizard GUI (manifest + ingest already in `migrate/`),
   dashboard trend charts, per-file user reassignment; v1.2: ZEN API dust auto-snap.
