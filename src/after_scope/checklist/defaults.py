"""Built-in end-of-session checklist, used when the config doesn't define one.

The config's `checklist:` section (same shape) fully replaces this when present, so
the lab manager can tune wording and items without touching code.
"""

DEFAULT_CHECKLIST: list[dict] = [
    {
        "key": "used_oil",
        "label": "Did you use oil immersion objectives?",
        "type": "yes_no",
        "required": True,
        "prefill_from": "objectives_contain_oil",
    },
    {
        "key": "oil_wicked",
        "label": "Oil wicked off with clean lens tissue",
        "type": "checkbox",
        "required": True,
        "show_if": {"key": "used_oil", "equals": True},
        "help": (
            "Touch a folded piece of lens tissue to the front lens and let the oil wick "
            "into it. Never rub, and never use dry swabs — they scratch the coating."
        ),
    },
    {
        "key": "solvent_clean",
        "label": "I solvent-cleaned the objective today",
        "type": "solvent_clean",
        "required": False,
        "show_if": {"key": "used_oil", "equals": True},
        "help": (
            "Solvent cleaning is periodic, not required every session. If residue is "
            "building up or it's been a while, do it now and it will be logged."
        ),
    },
    {
        "key": "stage_clean",
        "label": "Stage wiped — no oil or sample residue",
        "type": "checkbox",
        "required": True,
    },
    {
        "key": "objective_parked",
        "label": "Lowest-magnification objective in place, stage lowered",
        "type": "checkbox",
        "required": True,
    },
    {
        "key": "sample_removed",
        "label": "Did you remove your sample and slides?",
        "type": "yes_no",
        "required": True,
        "flag_if": False,
    },
    {
        "key": "lamps_off",
        "label": "Lamps/lasers off or in standby per lab policy",
        "type": "checkbox",
        "required": True,
    },
    {
        "key": "dust_cover",
        "label": "Dust cover on",
        "type": "checkbox",
        "required": True,
    },
]
