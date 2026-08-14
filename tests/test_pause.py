"""Tray-requested pause: file round-trip and expiry semantics."""

from datetime import datetime, timedelta

from after_scope.paths import AppPaths
from after_scope.watchdog.service import read_pause_until, request_pause


def test_pause_round_trip(tmp_path):
    paths = AppPaths(tmp_path).ensure()
    assert read_pause_until(paths) is None
    until = datetime.now() + timedelta(hours=2)
    request_pause(paths, until)
    got = read_pause_until(paths)
    assert got is not None
    assert abs((got - until).total_seconds()) < 1


def test_pause_tolerates_garbage(tmp_path):
    paths = AppPaths(tmp_path).ensure()
    paths.pause_until.write_text("not-a-timestamp", encoding="utf-8")
    assert read_pause_until(paths) is None


def test_watchdog_declines_while_paused(tmp_path, monkeypatch):
    """The __main__ gate: a future pause timestamp means exit before the mutex."""
    from after_scope.watchdog.service import read_pause_until as gate

    paths = AppPaths(tmp_path).ensure()
    request_pause(paths, datetime.now() + timedelta(minutes=30))
    until = gate(paths)
    assert until is not None and until > datetime.now()
    # expired pause no longer gates
    request_pause(paths, datetime.now() - timedelta(seconds=1))
    until = gate(paths)
    assert until is not None and until <= datetime.now()
