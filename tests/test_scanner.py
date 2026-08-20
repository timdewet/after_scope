from __future__ import annotations

import os
import time

from after_scope.watchdog.file_scan import AcquisitionScanner


def _touch(path, mtime=None, content=b"x"):
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_two_sweep_stability(cfg, tmp_path):
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    f = tmp_path / "watch" / "img.czi"
    _touch(f)
    assert scanner.sweep(start) == []          # first sighting: tracked only
    assert scanner.sweep(start) == [f]         # unchanged: stable
    assert scanner.sweep(start) == []          # reported once


def test_growing_file_not_reported_until_stable(cfg, tmp_path):
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    f = tmp_path / "watch" / "big.czi"
    _touch(f, content=b"1")
    scanner.sweep(start)
    _touch(f, content=b"22")                   # still being written
    assert scanner.sweep(start) == []
    assert scanner.sweep(start) == [f]


def test_old_files_ignored(cfg, tmp_path):
    scanner = AcquisitionScanner(cfg)
    f = tmp_path / "watch" / "old.czi"
    _touch(f, mtime=time.time() - 3600)
    start = time.time() - 10
    assert scanner.sweep(start) == []
    assert scanner.sweep(start) == []


def test_pattern_and_recursion(cfg, tmp_path):
    (tmp_path / "watch" / "sub").mkdir()
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    czi = tmp_path / "watch" / "sub" / "a.czi"
    txt = tmp_path / "watch" / "notes.txt"
    _touch(czi)
    _touch(txt)
    scanner.sweep(start)
    assert scanner.sweep(start) == [czi]


def test_last_file_mtime_tracks_activity(cfg, tmp_path):
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    now = time.time()
    f = tmp_path / "watch" / "img.czi"
    _touch(f, mtime=now)
    scanner.sweep(start)
    assert abs(scanner.last_file_mtime - now) < 2


def test_unreadable_watch_root_is_skipped(cfg, tmp_path):
    cfg.watch_dirs[0].path = tmp_path / "does-not-exist"
    scanner = AcquisitionScanner(cfg)
    assert scanner.sweep(time.time()) == []


def test_final_sweep_admits_first_sightings(cfg, tmp_path):
    """A file saved after the last periodic sweep must be captured by the at-exit
    sweep even though it was never seen before (ZEN is gone; nothing is writing)."""
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    assert scanner.sweep(start) == []  # nothing yet

    late = tmp_path / "watch" / "Snap-late.czi"
    _touch(late)
    # never seen before: the at-exit sweep must still capture it
    assert scanner.sweep(start, final=True) == [late]
    # and it is reported exactly once
    assert scanner.sweep(start, final=True) == []


def test_final_sweep_admits_changed_files(cfg, tmp_path):
    """Seen once, then changed before exit: still captured at exit."""
    scanner = AcquisitionScanner(cfg)
    start = time.time() - 10
    f = tmp_path / "watch" / "Snap-grow.czi"
    _touch(f, content=b"1")
    assert scanner.sweep(start) == []          # first sighting
    _touch(f, content=b"22")                   # ZEN finished writing at close
    assert scanner.sweep(start, final=True) == [f]
