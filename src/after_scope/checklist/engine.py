"""Checklist evaluation: visibility, prefill, validation, flagging.

Items come from config (NEMO-style declarative definitions) or the built-in default.
The engine is UI-free — the wizard renders items, the engine decides which are shown,
what starts prefilled, which answers are missing, and which answers raise a flag.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..config import AppConfig, ChecklistItemCfg
from ..db import repo
from .defaults import DEFAULT_CHECKLIST


def load_items(cfg: AppConfig) -> list[ChecklistItemCfg]:
    if cfg.checklist:
        return cfg.checklist
    return [ChecklistItemCfg.model_validate(d) for d in DEFAULT_CHECKLIST]


# --- prefill hooks -----------------------------------------------------------------


def _objectives_contain_oil(conn: sqlite3.Connection, session_id: int, cfg: AppConfig) -> bool:
    return bool(repo.session_oil_objectives(conn, session_id))


PREFILL_HOOKS = {
    "objectives_contain_oil": _objectives_contain_oil,
}


def prefill(
    conn: sqlite3.Connection, session_id: int, cfg: AppConfig, items: list[ChecklistItemCfg]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        hook = PREFILL_HOOKS.get(item.prefill_from or "")
        if hook:
            out[item.key] = hook(conn, session_id, cfg)
    return out


# --- evaluation --------------------------------------------------------------------


def visible_items(
    items: list[ChecklistItemCfg], responses: dict[str, Any]
) -> list[ChecklistItemCfg]:
    out = []
    for item in items:
        if item.show_if is None:
            out.append(item)
        elif responses.get(item.show_if.key) == item.show_if.equals:
            out.append(item)
    return out


def missing_required(
    items: list[ChecklistItemCfg], responses: dict[str, Any]
) -> list[ChecklistItemCfg]:
    """Visible, required items without a satisfying answer.

    checkbox: must be True. Other types: must be answered (non-None, non-empty).
    """
    missing = []
    for item in visible_items(items, responses):
        if not item.required:
            continue
        value = responses.get(item.key)
        if item.type == "checkbox":
            if value is not True:
                missing.append(item)
        elif value is None or value == "":
            missing.append(item)
    return missing


def is_flagged(item: ChecklistItemCfg, value: Any) -> bool:
    return item.flag_if is not None and value == item.flag_if


def save_responses(
    conn: sqlite3.Connection,
    session_id: int,
    items: list[ChecklistItemCfg],
    responses: dict[str, Any],
) -> list[ChecklistItemCfg]:
    """Persist visible responses; returns the items whose answers were flagged."""
    flagged: list[ChecklistItemCfg] = []
    for item in visible_items(items, responses):
        if item.key not in responses:
            continue
        value = responses[item.key]
        flag = is_flagged(item, value)
        repo.save_checklist_response(conn, session_id, item.key, item.label, value, flagged=flag)
        if flag:
            flagged.append(item)
    return flagged
