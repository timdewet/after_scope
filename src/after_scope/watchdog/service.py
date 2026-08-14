"""The watchdog state machine.

States:
    IDLE          no ZEN; poll for start, run nightly jobs, ingest migration manifests
    ACTIVE        ZEN running, session open, scanner sweeping, activity tracked
    DORMANT       ZEN open but nobody active (no input AND no new files)
    ABANDONED     idle so long the session auto-closed; ZEN still open, no session
    EXITING       ZEN process vanished; debounce window to catch helper respawns
    WAIT_RESTART  wizard said "I'm restarting ZEN"; wait for it to reappear

Driven by step() at ~1 Hz so tests can drive it with a fake clock — no threads.
Wizard processes are spawned synchronously; their exit codes report the outcome
(0 done, 2 skipped, 3 restarting-ZEN, 4 handover performed).
"""

from __future__ import annotations

import enum
import logging
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime

from ..appcontext import AppContext
from ..db import repo
from ..db.backup import backup_db
from ..db.export_csv import export_all
from ..session import SessionManager
from .file_scan import AcquisitionScanner
from .idle import IdleMonitor, make_idle_monitor
from .ingest import ingest_stable_file
from .process_watch import ProcessWatcher, ProcInfo, make_watcher

log = logging.getLogger(__name__)

EXIT_COMPLETE = 0
EXIT_SKIPPED = 2
EXIT_RESTART_ZEN = 3
EXIT_HANDOVER = 4


def read_pause_until(paths) -> datetime | None:
    """Timestamp before which the watchdog must not run, or None."""
    try:
        raw = paths.pause_until.read_text(encoding="utf-8-sig").strip()
        return datetime.fromisoformat(raw) if raw else None
    except (OSError, ValueError):
        return None


def request_pause(paths, until: datetime) -> None:
    try:
        paths.pause_until.write_text(until.isoformat(timespec="seconds"), encoding="utf-8")
    except OSError:
        log.error("Could not write pause file", exc_info=True)

DEBOUNCE_SECONDS = 5.0
RESTART_WAIT_SECONDS = 600.0
FRESH_INPUT_SECONDS = 10.0
NIGHTLY_HOUR = 3


class State(enum.Enum):
    IDLE = "idle"
    ACTIVE = "active"
    DORMANT = "dormant"
    ABANDONED = "abandoned"
    EXITING = "exiting"
    WAIT_RESTART = "wait_restart"


def _wizard_cmd(ctx: AppContext, reason: str, session_id: int | None) -> list[str]:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--config", str(ctx.config_path), "wizard"]
    else:
        cmd = [sys.executable, "-m", "after_scope", "--config", str(ctx.config_path), "wizard"]
    cmd += ["--reason", reason]
    if session_id is not None:
        cmd += ["--session-id", str(session_id)]
    return cmd


def spawn_wizard_process(ctx: AppContext, reason: str, session_id: int | None) -> int:
    """Run the wizard as a separate process; returns its exit code."""
    log.info("Spawning wizard: reason=%s session=%s", reason, session_id)
    try:
        return subprocess.run(_wizard_cmd(ctx, reason, session_id), check=False).returncode
    except OSError:
        log.error("Failed to spawn wizard", exc_info=True)
        return 1


def spawn_toast_process(ctx: AppContext, session_id: int, file_ids: list[int]) -> None:
    """Fire-and-forget annotation toast — must never block the watchdog loop."""
    cmd = _wizard_cmd(ctx, "annotate", session_id)
    cmd += ["--file-ids", ",".join(str(i) for i in file_ids)]
    try:
        subprocess.Popen(cmd)
    except OSError:
        log.error("Failed to spawn annotation toast", exc_info=True)


class WatchdogService:
    def __init__(
        self,
        ctx: AppContext,
        watcher: ProcessWatcher | None = None,
        idle_monitor: IdleMonitor | None = None,
        clock: Callable[[], float] = time.time,
        spawn_wizard: Callable[[AppContext, str, int | None], int] | None = None,
        spawn_toast: Callable[[AppContext, int, list[int]], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.cfg = ctx.config
        self.watcher = watcher or make_watcher(ctx.config.zen)
        self.idle = idle_monitor or make_idle_monitor()
        self.clock = clock
        self.spawn_wizard = spawn_wizard or spawn_wizard_process
        self.spawn_toast = spawn_toast or spawn_toast_process
        self.sm = SessionManager(
            ctx.db, machine=ctx.config.instrument.machine, app_version=ctx.app_version
        )
        self.state = State.IDLE
        self.session_id: int | None = None
        self.proc: ProcInfo | None = None
        self.scanner = AcquisitionScanner(ctx.config)
        self.running = True
        self.takeover_requested = False  # set by the tray thread
        self.declare_requested = False   # set by the tray thread
        self._last_scan = 0.0
        self._session_start_epoch = 0.0
        self._last_input_epoch = 0.0
        self._deadline = 0.0
        self._last_nightly_day: str | None = None
        self._boot()

    # -- helpers --------------------------------------------------------------------

    def _boot(self) -> None:
        self.sm.recover_orphans()
        proc = self.watcher.find_running()
        if proc:
            log.info("ZEN already running at watchdog start (pid %s)", proc.pid)
            self._on_zen_start(proc)

    def _iso(self, epoch: float) -> str:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%dT%H:%M:%S")

    def _last_activity_epoch(self) -> float:
        now = self.clock()
        last_input = now - self.idle.seconds_idle()
        return max(self._session_start_epoch, last_input, self.scanner.last_file_mtime)

    def request_takeover(self) -> None:
        self.takeover_requested = True

    def request_declare(self) -> None:
        self.declare_requested = True

    # -- publication ----------------------------------------------------------------

    def publish(self, nightly: bool = False) -> None:
        """Regenerate Dropbox artifacts (CSV, dashboard; backup nightly)."""
        conn = self.ctx.db
        export_all(conn, self.cfg.exports_dir)
        try:
            from ..report.dashboard import render_dashboard

            render_dashboard(conn, self.cfg, self.ctx.paths)
        except Exception:
            log.error("Dashboard render failed", exc_info=True)
        if nightly:
            backup_db(conn, self.cfg.backup_dir)

    def _nightly(self, now: float) -> None:
        day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        hour = datetime.fromtimestamp(now).hour
        if hour >= NIGHTLY_HOUR and day != self._last_nightly_day:
            self._last_nightly_day = day
            log.info("Running nightly export/backup/dashboard")
            self.publish(nightly=True)
            try:
                from ..migrate.ingest import ingest_inbox

                ingest_inbox(self.ctx)
            except Exception:
                log.error("Manifest ingest failed", exc_info=True)

    # -- state transitions ----------------------------------------------------------

    def _on_zen_start(self, proc: ProcInfo) -> None:
        self.proc = proc
        self.session_id = self.sm.open(proc.pid)
        self._session_start_epoch = self.clock()
        self.scanner.reset()
        self._last_scan = 0.0
        self.state = State.ACTIVE
        # Pre-use check (includes retro-checklist nag when one is pending).
        self.spawn_wizard(self.ctx, "start", self.session_id)
        self._resync_session()

    def _resync_session(self) -> None:
        """The wizard mutates sessions (handover, add-user, declared plan);
        re-read our pointer and pick up the planned session folder."""
        row = self.sm.open_session()
        self.session_id = row["id"] if row else None
        if row and row["planned_dir"]:
            self.scanner.add_extra_dir(row["planned_dir"])

    def _scan_if_due(self, now: float) -> None:
        if now - self._last_scan < self.cfg.scan.seconds:
            return
        self._last_scan = now
        if self.session_id is None:
            return
        session = repo.get_session(self.ctx.db, self.session_id)
        toast_ids: list[int] = []
        for path in self.scanner.sweep(self._session_start_epoch):
            try:
                file_id = ingest_stable_file(
                    self.ctx.db, self.cfg, self.ctx.paths, self.session_id, path
                )
            except Exception:
                log.error("Ingest failed for %s", path, exc_info=True)
                continue
            if session is not None:
                repo.fill_file_defaults(
                    self.ctx.db, file_id,
                    experiment_id=session["planned_experiment_id"],
                    user_id=session["user_id"],
                    strain=session["planned_strain"],
                    condition=session["planned_condition"],
                    coverslip=session["planned_coverslip"],
                )
            row = repo.get_file(self.ctx.db, file_id)
            if row is not None and row["status"] != "dust_ref":
                toast_ids.append(file_id)
        if toast_ids and self.cfg.annotate.mode == "toast":
            self.spawn_toast(self.ctx, self.session_id, toast_ids)

    def _do_handover(self) -> None:
        """Tray takeover or whoami 'someone else': wizard already performed the DB
        split (exit code 4); adopt the new open session."""
        self.takeover_requested = False
        code = self.spawn_wizard(self.ctx, "whoami", self.session_id)
        self._resync_session()
        if code == EXIT_HANDOVER:
            self._session_start_epoch = self.clock()
            self.scanner.reset()
        self.state = State.ACTIVE

    def _finalize_zen_exit(self) -> None:
        exit_code = self.watcher.exit_code(self.proc) if self.proc else None
        # final sweep so files saved moments before closing are captured
        self._last_scan = 0.0
        self._scan_if_due(self.clock())
        sid = self.session_id
        self.proc = None
        if sid is None:
            self.state = State.IDLE
            return
        self.sm.close_for_zen_exit(sid, exit_code)
        reason = "crash" if (exit_code not in (0, None)) else "close"
        code = self.spawn_wizard(self.ctx, reason, sid)
        if code == EXIT_COMPLETE:
            self.publish()
            self.state = State.IDLE
            self.session_id = None
        elif code == EXIT_RESTART_ZEN:
            repo.reopen_session(self.ctx.db, sid)
            self._deadline = self.clock() + RESTART_WAIT_SECONDS
            self.state = State.WAIT_RESTART
        elif code == EXIT_SKIPPED:
            # wizard recorded the skip + reason itself
            self.publish()
            self.state = State.IDLE
            self.session_id = None
        else:
            self.sm.checklist_crashed(sid)
            self.state = State.IDLE
            self.session_id = None

    # -- the tick -------------------------------------------------------------------

    def step(self) -> None:
        now = self.clock()
        if self.ctx.paths.stop_flag.exists():
            log.info("stop.flag present — shutting down for update")
            self.running = False
            return

        if self.state == State.IDLE:
            self._nightly(now)
            proc = self.watcher.find_running()
            if proc:
                self._on_zen_start(proc)
            return

        if self.state == State.WAIT_RESTART:
            proc = self.watcher.find_running()
            if proc:
                self.proc = proc
                with self.ctx.db as conn:
                    conn.execute(
                        "UPDATE sessions SET zen_pid=? WHERE id=?", (proc.pid, self.session_id)
                    )
                self.state = State.ACTIVE
            elif now > self._deadline:
                log.info("ZEN did not restart; reverting to end-of-session flow")
                self._finalize_zen_exit()
            return

        # ACTIVE / DORMANT / ABANDONED / EXITING all need liveness first
        if self.state == State.EXITING:
            proc = self.watcher.find_running()
            if proc:  # helper/child respawn — same session continues
                self.proc = proc
                self.state = State.ACTIVE if self.session_id is not None else State.ABANDONED
            elif now > self._deadline:
                self._finalize_zen_exit()
            return

        if self.proc and not self.watcher.is_alive(self.proc):
            self._deadline = now + DEBOUNCE_SECONDS
            self.state = State.EXITING
            return

        if self.state == State.ACTIVE:
            self._scan_if_due(now)
            if self.takeover_requested:
                self._do_handover()
                return
            if self.declare_requested:
                self.declare_requested = False
                self.spawn_wizard(self.ctx, "declare", self.session_id)
                self._resync_session()  # picks up a new planned_dir
                return
            idle_limit = self.cfg.handover.idle_minutes * 60
            if now - self._last_activity_epoch() > idle_limit:
                log.info("Session %s dormant (no input, no new files)", self.session_id)
                self.state = State.DORMANT
            return

        if self.state == State.DORMANT:
            self._scan_if_due(now)
            if self.takeover_requested:
                self._do_handover()
                return
            idle_limit = self.cfg.handover.idle_minutes * 60
            file_activity = max(self._session_start_epoch, self.scanner.last_file_mtime)
            if now - file_activity <= idle_limit:
                # frames are still landing (running acquisition) — resume silently;
                # keyboard input, by contrast, must go through the whoami check below
                self.state = State.ACTIVE
                return
            if self.idle.seconds_idle() < FRESH_INPUT_SECONDS:
                # someone is at the keyboard again — who?
                code = self.spawn_wizard(self.ctx, "whoami", self.session_id)
                self._resync_session()
                if code == EXIT_HANDOVER:
                    self._session_start_epoch = self.clock()
                    self.scanner.reset()
                self.state = State.ACTIVE
                return
            last_activity = self._last_activity_epoch()
            if now - last_activity > self.cfg.handover.auto_close_hours * 3600:
                self.sm.auto_close_idle(self.session_id, self._iso(last_activity))
                self.session_id = None
                self.state = State.ABANDONED
            return

        if self.state == State.ABANDONED:
            if self.idle.seconds_idle() < FRESH_INPUT_SECONDS or self.takeover_requested:
                self.takeover_requested = False
                proc = self.proc or self.watcher.find_running()
                if proc:
                    self._on_zen_start(proc)  # fresh session + pre-use check
            return

    def run(self, tick_seconds: float = 1.0) -> None:
        log.info("Watchdog running (state=%s)", self.state.name)
        tray = None
        if self.cfg.tray.enabled and sys.platform == "win32":
            try:
                from .tray import WatchdogTray

                tray = WatchdogTray(self)
                tray.start()
            except Exception:
                log.warning("Tray unavailable", exc_info=True)
        try:
            while self.running:
                try:
                    self.step()
                except Exception:
                    log.error("Watchdog step failed", exc_info=True)
                time.sleep(tick_seconds)
        finally:
            if tray:
                tray.stop()
