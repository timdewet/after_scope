from __future__ import annotations

from after_scope.checklist import engine
from after_scope.config import AppConfig
from after_scope.db import repo


def test_default_items_load(cfg):
    items = engine.load_items(cfg)
    keys = [i.key for i in items]
    assert "used_oil" in keys and "solvent_clean" in keys and "dust_cover" in keys


def test_config_checklist_overrides_default():
    cfg = AppConfig.model_validate(
        {"checklist": [{"key": "custom", "label": "Custom item", "type": "checkbox"}]}
    )
    items = engine.load_items(cfg)
    assert [i.key for i in items] == ["custom"]


def test_show_if_visibility(cfg):
    items = engine.load_items(cfg)
    hidden = engine.visible_items(items, {"used_oil": False})
    shown = engine.visible_items(items, {"used_oil": True})
    hidden_keys = {i.key for i in hidden}
    shown_keys = {i.key for i in shown}
    assert "oil_wicked" not in hidden_keys and "solvent_clean" not in hidden_keys
    assert "oil_wicked" in shown_keys and "solvent_clean" in shown_keys


def test_missing_required(cfg):
    items = engine.load_items(cfg)
    responses = {"used_oil": True, "oil_wicked": True, "stage_clean": True}
    missing = {i.key for i in engine.missing_required(items, responses)}
    # solvent_clean is optional; the rest of the always-on items are still missing
    assert "solvent_clean" not in missing
    assert {"objective_parked", "sample_removed", "lamps_off", "dust_cover"} <= missing
    # unchecked checkbox counts as missing
    responses["dust_cover"] = False
    assert "dust_cover" in {i.key for i in engine.missing_required(items, responses)}


def test_oil_prefill_from_session_metadata(conn, cfg):
    sid = repo.open_session(conn, zen_pid=1)
    fid = repo.add_file(conn, sid, "/d/a.czi")
    repo.set_file_metadata(conn, fid, {"objective_name": "100x Oil", "immersion": "Oil"})
    items = engine.load_items(cfg)
    pre = engine.prefill(conn, sid, cfg, items)
    assert pre["used_oil"] is True

    sid2 = repo.open_session(conn, zen_pid=2)
    assert engine.prefill(conn, sid2, cfg, items)["used_oil"] is False


def test_save_responses_flags(conn, cfg):
    sid = repo.open_session(conn, zen_pid=1)
    items = engine.load_items(cfg)
    responses = {
        "used_oil": False,
        "stage_clean": True,
        "objective_parked": True,
        "sample_removed": False,  # flag_if: false
        "lamps_off": True,
        "dust_cover": True,
    }
    flagged = engine.save_responses(conn, sid, items, responses)
    assert [i.key for i in flagged] == ["sample_removed"]
    saved = {r["item_key"]: r for r in repo.checklist_responses(conn, sid)}
    assert saved["sample_removed"]["flagged"] == 1
    # hidden items were not saved
    assert "oil_wicked" not in saved
