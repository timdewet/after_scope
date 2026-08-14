from __future__ import annotations

import textwrap

import pytest

from after_scope.config import AppConfig, load_config

GOOD = textwrap.dedent("""
    instrument: { name: "Zeiss LSM980" }
    zen:
      process_names: ["Zen.exe"]
    watch_dirs:
      - { path: "watch" }
    dropbox: { root: "dropbox" }
    roster:
      - { name: "Tim de Wet", initials: "TdW" }
    handover: { idle_minutes: 30, auto_close_hours: 4 }
""")


def test_load_and_resolve_relative_paths(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(GOOD, encoding="utf-8")
    cfg = load_config(p, cache_path=tmp_path / "cache" / "last_good.yaml")
    assert cfg.instrument.name == "Zeiss LSM980"
    # relative paths resolved against the config file's directory
    assert cfg.watch_dirs[0].path == (tmp_path / "watch").resolve()
    assert cfg.dropbox.root == (tmp_path / "dropbox").resolve()
    assert cfg.exports_dir == (tmp_path / "dropbox").resolve() / "AfterScope" / "exports"
    assert cfg.handover.idle_minutes == 30
    # last-good cache written
    assert (tmp_path / "cache" / "last_good.yaml").exists()


def test_broken_config_falls_back_to_last_good(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(GOOD, encoding="utf-8")
    cache = tmp_path / "cache" / "last_good.yaml"
    load_config(p, cache_path=cache)

    p.write_text("watch_dirs: 'not a list'", encoding="utf-8")
    cfg = load_config(p, cache_path=cache)  # falls back, no raise
    assert cfg.instrument.name == "Zeiss LSM980"


def test_broken_config_without_cache_raises(tmp_path):
    import yaml

    p = tmp_path / "config.yaml"
    p.write_text("zen: [nonsense", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_config(p, cache_path=tmp_path / "nope.yaml")


def test_defaults_are_sensible():
    cfg = AppConfig()
    assert cfg.zen.process_names == ["Zen.exe"]
    assert cfg.organize.mode == "move"
    assert cfg.dust.filename_prefix == "dustref"
    assert cfg.enforcement.allow_skip is True
    assert cfg.handover.idle_minutes == 45
