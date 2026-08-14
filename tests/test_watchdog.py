from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from after_scope.appcontext import AppContext
from after_scope.db import repo
from after_scope.session import SessionManager
from after_scope.watchdog.idle import FakeIdleMonitor
from after_scope.watchdog.process_watch import ProcInfo
from after_scope.watchdog.service import (
    EXIT_COMPLETE,
    EXIT_HANDOVER,
    EXIT_RESTART_ZEN,
    State,
    WatchdogService,
)


class FakeWatcher:
    def __init__(self):
        self.proc: ProcInfo | None = None
        self.alive = False
        self._exit_code = 0

    def start_zen(self, pid=100):
        self.proc = ProcInfo(pid, "Zen.exe", time.time())
        self.alive = True

    def kill_zen(self, exit_code=0):
        self.alive = False
        self._exit_code = exit_code

    def find_running(self):
        return self.proc if self.alive else None

    def is_alive(self, proc):
        return self.alive

    def exit_code(self, proc):
        return self._exit_code


class FakeClock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class WizardStub:
    """Records spawns; per-reason exit codes; optional per-reason side effects."""

    def __init__(self):
        self.calls: list[tuple[str, int | None]] = []
        self.exit_codes: dict[str, int] = {}
        self.effects: dict[str, callable] = {}

    def __call__(self, ctx, reason, session_id):
        self.calls.append((reason, session_id))
        if reason in self.effects:
            self.effects[reason](ctx, session_id)
        return self.exit_codes.get(reason, 0)


class ToastStub:
    def __init__(self):
        self.calls: list[tuple[int, list[int]]] = []

    def __call__(self, ctx, session_id, file_ids):
        self.calls.append((session_id, list(file_ids)))


@pytest.fixture
def service(cfg, tmp_path):
    cfg.handover.idle_minutes = 10 / 60  # 10 s
    cfg.handover.auto_close_hours = 60 / 3600  # 60 s
    cfg.scan.seconds = 1
    ctx = AppContext(config=cfg, paths=cfg.app_paths().ensure(), config_path=tmp_path / "c.yaml")
    watcher = FakeWatcher()
    clock = FakeClock()
    idle = FakeIdleMonitor(0.0)
    wizard = WizardStub()
    toast = ToastStub()
    svc = WatchdogService(
        ctx, watcher=watcher, idle_monitor=idle, clock=clock,
        spawn_wizard=wizard, spawn_toast=toast,
    )
    svc.fake = dict(watcher=watcher, clock=clock, idle=idle, wizard=wizard, toast=toast, ctx=ctx)
    return svc


def test_zen_start_opens_session_and_preuse(service):
    f = service.fake
    assert service.state == State.IDLE
    f["watcher"].start_zen()
    service.step()
    assert service.state == State.ACTIVE
    assert service.session_id is not None
    assert f["wizard"].calls == [("start", service.session_id)]


def test_full_close_cycle_completes_session(service, tmp_path):
    f = service.fake
    f["wizard"].effects["close"] = lambda ctx, sid: SessionManager(ctx.db).checklist_complete(sid)
    f["watcher"].start_zen()
    service.step()
    sid = service.session_id

    # a file appears and stabilizes across two scans
    czi = tmp_path / "watch" / "img.czi"
    czi.write_bytes(b"data")
    os.utime(czi, (f["clock"].t, f["clock"].t))
    f["clock"].advance(2)
    service.step()  # sweep 1: tracked
    f["clock"].advance(2)
    service.step()  # sweep 2: stable -> ingested
    files = repo.session_files(f["ctx"].db, sid)
    assert [Path(r["original_path"]).name for r in files] == ["img.czi"]

    f["watcher"].kill_zen(exit_code=0)
    service.step()
    assert service.state == State.EXITING
    f["clock"].advance(6)
    service.step()
    assert ("close", sid) in f["wizard"].calls
    assert service.state == State.IDLE
    row = repo.get_session(f["ctx"].db, sid)
    assert row["status"] == "complete" and row["ended_reason"] == "zen_close"
    # publish ran: exports exist
    assert (service.cfg.exports_dir / "sessions.csv").exists()


def test_crash_spawns_crash_reason(service):
    f = service.fake
    f["watcher"].start_zen()
    service.step()
    sid = service.session_id
    f["watcher"].kill_zen(exit_code=1)
    service.step()
    f["clock"].advance(6)
    service.step()
    assert ("crash", sid) in f["wizard"].calls
    assert repo.get_session(f["ctx"].db, sid)["ended_reason"] == "crash"


def test_debounce_respawn_keeps_session(service):
    f = service.fake
    f["watcher"].start_zen(pid=100)
    service.step()
    sid = service.session_id
    f["watcher"].kill_zen()
    service.step()
    assert service.state == State.EXITING
    f["watcher"].start_zen(pid=101)  # helper respawn within debounce
    service.step()
    assert service.state == State.ACTIVE and service.session_id == sid


def test_dormancy_whoami_same_user(service):
    f = service.fake
    f["watcher"].start_zen()
    service.step()
    f["idle"].value = 3600  # nobody at the keyboard
    f["clock"].advance(30)  # > idle_minutes (10 s)
    service.step()
    assert service.state == State.DORMANT
    f["idle"].value = 1.0  # input resumed
    f["wizard"].exit_codes["whoami"] = EXIT_COMPLETE
    service.step()
    assert service.state == State.ACTIVE
    assert f["wizard"].calls[-1][0] == "whoami"


def test_dormancy_handover_switches_session(service):
    f = service.fake

    def do_handover(ctx, sid):
        sm = SessionManager(ctx.db)
        sm.handover(sid)

    f["wizard"].effects["whoami"] = do_handover
    f["wizard"].exit_codes["whoami"] = EXIT_HANDOVER
    f["watcher"].start_zen()
    service.step()
    old_sid = service.session_id
    f["idle"].value = 3600
    f["clock"].advance(30)
    service.step()
    assert service.state == State.DORMANT
    f["idle"].value = 0.5
    service.step()
    assert service.state == State.ACTIVE
    assert service.session_id != old_sid
    old = repo.get_session(f["ctx"].db, old_sid)
    assert old["incomplete_reason"] == "handover"


def test_timelapse_files_prevent_dormancy(service, tmp_path):
    f = service.fake
    f["watcher"].start_zen()
    service.step()
    f["idle"].value = 3600  # no keyboard input for an hour...
    f["clock"].advance(5)
    czi = tmp_path / "watch" / "t0.czi"
    czi.write_bytes(b"frame")
    os.utime(czi, (f["clock"].t, f["clock"].t))  # ...but frames keep landing
    service.step()  # sweep sees fresh file -> activity
    f["clock"].advance(6)
    service.step()
    assert service.state == State.ACTIVE


def test_auto_close_after_long_idle(service):
    f = service.fake
    f["watcher"].start_zen()
    service.step()
    sid = service.session_id
    f["idle"].value = 10_000
    f["clock"].advance(30)
    service.step()
    assert service.state == State.DORMANT
    f["clock"].advance(120)  # > auto_close (60 s)
    service.step()
    assert service.state == State.ABANDONED and service.session_id is None
    assert repo.get_session(f["ctx"].db, sid)["ended_reason"] == "idle_timeout"
    # someone shows up: fresh session + pre-use
    f["idle"].value = 1.0
    service.step()
    assert service.state == State.ACTIVE
    assert service.session_id is not None and service.session_id != sid
    assert f["wizard"].calls[-1][0] == "start"


def test_tray_takeover_in_active(service):
    f = service.fake

    f["wizard"].effects["whoami"] = lambda ctx, sid: SessionManager(ctx.db).handover(sid)
    f["wizard"].exit_codes["whoami"] = EXIT_HANDOVER
    f["watcher"].start_zen()
    service.step()
    old_sid = service.session_id
    service.request_takeover()
    f["clock"].advance(2)
    service.step()
    assert service.session_id != old_sid
    assert service.state == State.ACTIVE


def test_restart_zen_flow(service):
    f = service.fake
    f["wizard"].exit_codes["close"] = EXIT_RESTART_ZEN
    f["watcher"].start_zen()
    service.step()
    sid = service.session_id
    f["watcher"].kill_zen()
    service.step()
    f["clock"].advance(6)
    service.step()
    assert service.state == State.WAIT_RESTART
    assert repo.get_session(f["ctx"].db, sid)["status"] == "open"
    f["watcher"].start_zen(pid=202)
    service.step()
    assert service.state == State.ACTIVE and service.session_id == sid


def test_stop_flag_stops(service):
    service.ctx.paths.stop_flag.touch()
    service.step()
    assert service.running is False


def test_plan_defaults_applied_and_toast_fired(service, tmp_path):
    f = service.fake

    def declare(ctx, sid):
        eid = repo.get_or_create_experiment(ctx.db, "declared-exp", None)
        planned = tmp_path / "session_dir"
        planned.mkdir()
        repo.set_session_plan(ctx.db, sid, experiment_id=eid, strain="MSM9",
                              condition="hypoxia", coverslip=None, notes=None,
                              planned_dir=str(planned))

    f["wizard"].effects["start"] = declare
    f["watcher"].start_zen()
    service.step()
    sid = service.session_id
    # planned dir picked up as a session-scoped watch root
    assert service.scanner.extra_dirs == [tmp_path / "session_dir"]

    # one file in the planned dir, one dust file in the normal watch dir
    for name, folder in [("in_plan.czi", tmp_path / "session_dir"),
                         ("dustref_x.czi", tmp_path / "watch")]:
        p = folder / name
        p.write_bytes(b"data")
        os.utime(p, (f["clock"].t, f["clock"].t))
    f["clock"].advance(2)
    service.step()
    f["clock"].advance(2)
    service.step()

    rows = {Path(r["original_path"]).name: r for r in repo.session_files(f["ctx"].db, sid)}
    assert rows["in_plan.czi"]["strain"] == "MSM9"
    assert rows["in_plan.czi"]["condition"] == "hypoxia"
    assert rows["in_plan.czi"]["experiment_id"] is not None
    # toast fired only for the non-dust file
    assert len(f["toast"].calls) == 1
    assert f["toast"].calls[0] == (sid, [rows["in_plan.czi"]["id"]])


def test_no_toast_when_annotate_off(service, tmp_path):
    f = service.fake
    service.cfg.annotate.mode = "off"
    f["watcher"].start_zen()
    service.step()
    p = tmp_path / "watch" / "img.czi"
    p.write_bytes(b"data")
    os.utime(p, (f["clock"].t, f["clock"].t))
    f["clock"].advance(2)
    service.step()
    f["clock"].advance(2)
    service.step()
    assert repo.session_files(f["ctx"].db, service.session_id)
    assert f["toast"].calls == []


def test_tray_declare_request_spawns_declare_wizard(service, tmp_path):
    f = service.fake

    def declare(ctx, sid):
        planned = tmp_path / "later_dir"
        planned.mkdir()
        repo.set_session_plan(ctx.db, sid, experiment_id=None, strain="LATE",
                              condition=None, coverslip=None, notes=None,
                              planned_dir=str(planned))

    f["wizard"].effects["declare"] = declare
    f["watcher"].start_zen()
    service.step()
    service.request_declare()
    f["clock"].advance(2)
    service.step()
    assert ("declare", service.session_id) in f["wizard"].calls
    assert tmp_path / "later_dir" in service.scanner.extra_dirs


def test_orphan_recovery_at_boot(cfg, tmp_path):
    ctx = AppContext(config=cfg, paths=cfg.app_paths().ensure(), config_path=tmp_path / "c.yaml")
    sid = repo.open_session(ctx.db, zen_pid=1)  # left open by a "crash"
    svc = WatchdogService(
        ctx, watcher=FakeWatcher(), idle_monitor=FakeIdleMonitor(), clock=FakeClock(),
        spawn_wizard=WizardStub(),
    )
    assert repo.get_session(ctx.db, sid)["status"] == "incomplete"
    assert svc.state == State.IDLE
