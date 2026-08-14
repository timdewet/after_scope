from __future__ import annotations

from pathlib import Path

import pytest

from after_scope.metadata.czi import extract, parse_czi_xml, save_raw_xml

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def zen_xml() -> str:
    return (FIXTURES / "zen_blue_metadata.xml").read_text(encoding="utf-8")


def test_parse_zen_blue_xml(zen_xml):
    out = parse_czi_xml(zen_xml)
    assert out["dims"] == {"X": 1936, "Y": 1460, "C": 2, "T": 1}
    # objective resolved via ObjectiveRef (the 100x oil, not the first listed)
    assert out["objective_name"] == "Plan-Apochromat 100x/1.40 Oil"
    assert out["magnification"] == 100 and out["na"] == 1.4 and out["immersion"] == "Oil"
    assert out["pixel_size_um"] == pytest.approx(0.065)
    assert out["acquired_at"].startswith("2026-08-12T")  # tz-localized, naive
    bf, gfp = out["channels"]
    assert bf["name"] == "TL Brightfield" and bf["exposure_ms"] == 25.0
    assert gfp["excitation_nm"] == "488" and gfp["light_intensity"] == "20 %"


def test_parse_garbage_xml_returns_empty():
    assert parse_czi_xml("<not-even") == {}
    assert parse_czi_xml("<Empty/>") == {}


def test_extract_nonexistent_file_is_safe(tmp_path):
    meta = extract(tmp_path / "missing.czi")
    assert meta.size_bytes is None and meta.channels == []


def test_extract_non_czi_file_gives_stat_only(tmp_path):
    p = tmp_path / "junk.czi"
    p.write_bytes(b"not a czi at all")
    meta = extract(p)
    assert meta.size_bytes == 16
    assert meta.acquired_at is not None  # falls back to mtime
    assert meta.objective_name is None


def test_extract_real_generated_czi(tmp_path):
    from scripts.make_fixture_czi import make_fixture_czi

    czi = make_fixture_czi(tmp_path / "gen.czi")
    meta = extract(czi)
    assert meta.dims["X"] == 96 and meta.dims["C"] == 2
    assert meta.pixel_size_um == pytest.approx(0.065)
    assert [c["name"] for c in meta.channels] == ["TL Brightfield", "EGFP"]
    assert meta.raw_xml and "<Metadata" in meta.raw_xml
    db = meta.to_db_dict()
    assert db["channels_json"] and db["dims_json"]


def test_thumbnail_from_generated_czi(tmp_path):
    from after_scope.metadata.thumbs import make_thumbnail
    from scripts.make_fixture_czi import make_fixture_czi

    czi = make_fixture_czi(tmp_path / "gen.czi")
    out = make_thumbnail(czi, tmp_path / "thumbs", "gen")
    assert out and Path(out).exists()
    from PIL import Image

    with Image.open(out) as img:
        assert max(img.size) <= 256


def test_save_raw_xml_gzip(tmp_path, zen_xml):
    out = save_raw_xml(zen_xml, tmp_path / "xml", "f1")
    import gzip

    with gzip.open(out, "rt", encoding="utf-8") as f:
        assert "ImageDocument" in f.read()
