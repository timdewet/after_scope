# after_scope

End-of-session compliance & metadata tool for a shared Zeiss microscope (ZEN Blue).

An always-running watchdog on the scope PC brackets every ZEN session:

- **When ZEN starts** — a quick pre-use check opens: who you are, an optional "what are
  you imaging today?" declaration (which pre-creates a scratch session folder and
  auto-tags every file saved during the session), "was everything OK when you arrived?"
  (found-dirty reports are attributed to the previous user), and an open-issues board.
- **When a CZI is saved** — a small corner toast confirms how the file was tagged
  ("Snap-003 → efflux-timelapse / MSM155 — click to change"); it never steals focus and
  auto-dismisses accepting the declared defaults.
- **When ZEN closes** — a fullscreen checklist wizard captures per-file experimental
  metadata (acquisition settings auto-extracted from CZI headers), renames/moves files
  into a standard Dropbox tree, walks the cleaning checklist (incl. tracked solvent-clean
  events), records the 100× brightfield dust reference, and takes incident reports.
- **If ZEN is left open** — idle detection re-confirms who is at the scope and splits the
  session on handover; a tray menu offers "I'm taking over" at any time.

Everything lands in SQLite on the scope PC's local disk, with CSV exports, nightly DB
backups, and a self-contained HTML lab dashboard written to the shared Dropbox.

## Layout

- `src/after_scope/` — the application (watchdog, wizard, metadata, DB, dashboard)
- `config/` — annotated example config + macOS simulate profile
- `scripts/` — fake ZEN + acquisition simulator + CZI fixture generator (dev)
- `deploy/` — PyInstaller spec and Windows install/update scripts
- `tests/` — unit, wizard (offscreen Qt), and end-to-end simulate tests

## Development (macOS or any desktop OS)

```bash
python3.12 -m venv ~/.venvs/after_scope   # keep the venv OUTSIDE Dropbox
~/.venvs/after_scope/bin/pip install -e ".[dev]"
~/.venvs/after_scope/bin/pytest
```

Run the full simulated loop without a microscope:

```bash
after-scope watchdog --config config/config.simulate.yaml   # terminal 1
python scripts/fake_zen.py                                  # terminal 2 ("ZEN opens")
python scripts/simulate_acquisition.py                      # terminal 3 (drips CZI files)
# quit fake_zen (Ctrl+C)  ->  the end-of-session wizard appears
```

## Deployment (Windows scope PC)

See `deploy/windows/install.ps1`. Build with `deploy/build.ps1` on a Windows machine or
CI (`windows-latest`); PyInstaller cannot cross-build from macOS.

The Windows first-deploy smoke checklist lives at the bottom of this file.

## Windows first-deploy smoke checklist

- [ ] Scheduled task fires at logon; watchdog visible in tray
- [ ] Open/close ZEN three times, incl. one `taskkill /f /im Zen.exe` crash simulation
- [ ] Save a CZI to local scratch and to Dropbox — both captured in the wizard
- [ ] Move across volumes (scratch → Dropbox) verified byte-size equal, original removed
- [ ] Wizard appears on top of ZEN's shutdown splash
- [ ] Works as a non-admin user
- [ ] Sleep/resume mid-session does not kill the session
- [ ] Leave ZEN open past the idle threshold → "who's at the scope?" prompt on return
- [ ] Tray "I'm taking over" splits the session between two roster users
- [ ] A mock long acquisition (files appearing, no input) does NOT go dormant
- [ ] Defender quiet for a week (onedir build + IT allowlist)
