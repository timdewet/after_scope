"""after_scope CLI: watchdog | wizard | doctor | export | backup | migrate | version."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="after-scope")
    parser.add_argument("--config", help="Path to config.yaml", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("watchdog", help="Run the resident watchdog")

    p_wizard = sub.add_parser("wizard", help="Run the checklist wizard")
    p_wizard.add_argument("--session-id", type=int, required=True)
    p_wizard.add_argument(
        "--reason",
        choices=["start", "close", "crash", "nag", "handover", "whoami", "declare", "annotate"],
        default="close",
    )
    p_wizard.add_argument("--file-ids", default="",
                          help="annotate only: comma-separated file ids for the toast")
    p_wizard.add_argument("--auto-accept", action="store_true", help="Testing: accept defaults")

    sub.add_parser("doctor", help="Validate config, paths and environment")
    sub.add_parser("export", help="Regenerate CSV exports and the dashboard now")
    sub.add_parser("backup", help="Back up the DB into Dropbox now")

    p_migrate = sub.add_parser("migrate", help="Legacy-data migration")
    p_migrate.add_argument("--ingest", action="store_true",
                           help="Ingest pending manifests from the Dropbox inbox (scope PC)")

    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    if args.command == "version":
        from . import __version__

        print(__version__)
        return 0

    from .appcontext import AppContext

    ctx = AppContext.build(args.config, role=args.command)

    if args.command == "watchdog":
        return _run_watchdog(ctx)
    if args.command == "wizard":
        if args.reason == "annotate":
            from .wizard.toast import run_toast

            file_ids = [int(x) for x in args.file_ids.split(",") if x.strip()]
            return run_toast(ctx, args.session_id, file_ids)
        from .wizard.app import run_wizard

        return run_wizard(ctx, args.session_id, args.reason, auto_accept=args.auto_accept)
    if args.command == "doctor":
        return _run_doctor(ctx)
    if args.command == "export":
        from .db.export_csv import export_all
        from .report.dashboard import render_dashboard

        written = export_all(ctx.db, ctx.config.exports_dir)
        dash = render_dashboard(ctx.db, ctx.config, ctx.paths)
        print(f"Wrote {len(written)} CSV file(s) to {ctx.config.exports_dir}")
        print(f"Dashboard: {dash}")
        return 0
    if args.command == "backup":
        from .db.backup import backup_db

        dest = backup_db(ctx.db, ctx.config.backup_dir)
        print(f"Backup: {dest}" if dest else "Backup FAILED — see logs")
        return 0 if dest else 1
    if args.command == "migrate":
        if args.ingest:
            from .migrate.ingest import ingest_inbox

            n = ingest_inbox(ctx)
            print(f"Ingested {n} file(s) from manifests")
            return 0
        print("The migration wizard ships in v1.1. For now: --ingest processes the inbox.")
        return 0
    return 2


def _run_watchdog(ctx) -> int:
    from datetime import datetime

    from .watchdog.service import WatchdogService, read_pause_until
    from .watchdog.single_instance import SingleInstance

    until = read_pause_until(ctx.paths)
    if until is not None and until > datetime.now():
        # tray-requested pause: the keep-alive task keeps relaunching us, and we
        # keep declining until the timestamp passes
        print(f"AfterScope paused until {until:%H:%M} — exiting.")
        return 0

    guard = SingleInstance("AfterScopeWatchdog", ctx.paths.data_dir)
    if not guard.acquire():
        print("Watchdog already running — exiting.")
        return 0
    try:
        # a leftover stop.flag from an update must not stop the fresh instance
        ctx.paths.stop_flag.unlink(missing_ok=True)
        ctx.paths.pause_until.unlink(missing_ok=True)
        WatchdogService(ctx).run()
        return 0
    finally:
        guard.release()


def _run_doctor(ctx) -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    cfg = ctx.config
    check(
        "config loads",
        not cfg.loaded_from_cache,
        str(ctx.config_path)
        + (" — LIVE FILE BROKEN, running on cached last-known-good!" if cfg.loaded_from_cache else ""),
    )
    check("data dir writable", _writable(ctx.paths.data_dir), str(ctx.paths.data_dir))
    try:
        ctx.db.execute("SELECT 1")
        check("database opens", True, str(ctx.paths.db_path))
    except Exception as exc:
        check("database opens", False, str(exc))
    for wd in cfg.watch_dirs:
        check(f"watch dir exists: {wd.path}", wd.path.exists())
    if not cfg.watch_dirs:
        check("watch dirs configured", False, "no watch_dirs in config!")
    check("dropbox root exists", cfg.dropbox.root.exists(), str(cfg.dropbox.root))
    check("exports dir writable", _writable(cfg.exports_dir), str(cfg.exports_dir))
    check("roster non-empty", bool(cfg.roster) or _has_users(ctx))
    from .watchdog.process_watch import make_watcher

    watcher = make_watcher(cfg.zen)
    proc = watcher.find_running()
    check(
        f"ZEN process ({', '.join(cfg.zen.process_names)})",
        True,
        f"running now (pid {proc.pid})" if proc else "not currently running (fine)",
    )
    if sys.platform == "win32":
        check("tray available", _importable("pystray"))
    check("CZI reader (pylibCZIrw)", _importable("pylibCZIrw"))
    check("CZI fallback (czifile)", _importable("czifile"))
    check("Qt (PySide6)", _importable("PySide6"))

    width = max(len(c[0]) for c in checks) + 2
    failures = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{mark}] {name:<{width}} {detail}")
    print(f"\n{len(checks) - failures}/{len(checks)} checks passed.")
    return 0 if failures == 0 else 1


def _writable(path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _has_users(ctx) -> bool:
    try:
        from .db import repo

        return bool(repo.list_users(ctx.db))
    except Exception:
        return False


def _importable(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
