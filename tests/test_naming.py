from __future__ import annotations

from after_scope.metadata.naming import (
    build_context,
    propose_filename,
    render_dest_dir,
    sanitize_token,
)

TEMPLATE = "{date}_{initials}_{experiment}_{strain}_{condition}_{seq:03d}"
DEST = "{dropbox_root}/MicroscopeData/{year}/{initials}/{date}_{experiment}"


def ctx(**over):
    base = build_context(
        acquired_at="2026-08-14T13:00:00",
        initials="TdW",
        experiment="efflux timelapse",
        strain="MSM155",
        condition="37C",
    )
    base.update(over)
    return base


def test_sanitize_token():
    assert sanitize_token("efflux timelapse") == "efflux-timelapse"
    assert sanitize_token("Δstrain #7 (37°C)") == "strain-7-37-C"
    assert sanitize_token("--weird--__stuff--") == "weird-stuff"
    assert sanitize_token(None) == ""
    assert len(sanitize_token("x" * 100)) <= 40


def test_basic_name_and_dest(tmp_path):
    c = ctx()
    name = propose_filename(TEMPLATE, c, tmp_path, ".czi", set())
    assert name == "20260814_TdW_efflux-timelapse_MSM155_37C_001.czi"
    dest = render_dest_dir(DEST, c, tmp_path)
    assert dest.as_posix().endswith("MicroscopeData/2026/TdW/20260814_efflux-timelapse")


def test_missing_tokens_collapse():
    c = build_context(acquired_at="2026-08-14T13:00:00", initials="JD",
                      experiment=None, strain=None, condition=None)
    name = propose_filename(TEMPLATE, c, __import__("pathlib").Path("/nonexistent-dir"), ".czi", set())
    assert name == "20260814_JD_001.czi"


def test_sequence_avoids_existing_and_planned(tmp_path):
    c = ctx()
    (tmp_path / "20260814_TdW_efflux-timelapse_MSM155_37C_001.czi").write_text("x")
    taken = {"20260814_TdW_efflux-timelapse_MSM155_37C_002.czi"}
    name = propose_filename(TEMPLATE, c, tmp_path, ".czi", taken)
    assert name.endswith("_003.czi")


def test_path_length_guard(tmp_path):
    c = ctx(experiment="e" * 40, strain="s" * 40, condition="c" * 40)
    deep = tmp_path / "d"
    limit = len(str(deep)) + 60  # room for a shortened name but not the full one
    name = propose_filename(TEMPLATE, c, deep, ".czi", set(), max_path_length=limit)
    assert len(str(deep / name)) <= limit
    assert name.endswith(".czi")


def test_dest_dir_caps_long_experiment(tmp_path):
    c = ctx(experiment="a-very-long-experiment-name-that-goes-on-and-on")
    dest = render_dest_dir(DEST, c, tmp_path)
    assert len(dest.name) <= len("20260814_") + 24


def test_acquisition_date_used_not_today():
    c = build_context(acquired_at="2019-03-02T09:00:00", initials="JD",
                      experiment="old", strain=None, condition=None)
    assert c["date"] == "20190302" and c["year"] == "2019"
