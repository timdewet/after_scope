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
