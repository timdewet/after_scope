"""Design tokens — the single source of truth for spacing, type and colour.

Nothing outside this package should hardcode a colour or margin; widgets that
paint manually read the active palette via `active()`.

Kiosk context: the wizard runs fullscreen on the scope PC and is read at arm's
length, so the type scale sits a step larger than a desktop app's.
"""

from __future__ import annotations

from dataclasses import dataclass

# spacing scale (px)
S1, S2, S3, S4, S5, S6, S7, S8 = 4, 8, 12, 16, 20, 24, 32, 48

# radii
R_SM, R_MD, R_LG, R_PILL = 4, 6, 10, 999

FONT_FAMILY = '"Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", sans-serif'
FONT_FAMILY_MONO = 'Consolas, "SF Mono", Menlo, monospace'

# type scale (px)
FS_CAPTION, FS_BODY, FS_H3, FS_H2, FS_H1, FS_TITLE = 12, 14, 15, 17, 21, 26

FW_REGULAR, FW_MEDIUM, FW_SEMIBOLD, FW_BOLD = 400, 500, 600, 700


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_disabled: str
    on_primary: str
    success: str
    success_hover: str
    warning: str
    danger: str
    focus_ring: str
    selection: str


LIGHT = Palette(
    name="light",
    bg="#fafbfc",
    surface="#ffffff",
    surface_alt="#f4f6f8",
    border="#e2e6eb",
    border_strong="#d8dde3",
    text="#1f2329",
    text_muted="#5b6571",
    text_subtle="#8b939d",
    primary="#2563eb",
    primary_hover="#1d4fc4",
    primary_pressed="#173f9c",
    primary_disabled="#b8c8e8",
    on_primary="#ffffff",
    success="#16a34a",
    success_hover="#0f8a3d",
    warning="#d97706",
    danger="#dc2626",
    focus_ring="#4a90e2",
    selection="#cfe3ff",
)

DARK = Palette(
    name="dark",
    bg="#0e1116",
    surface="#161b22",
    surface_alt="#1c222b",
    border="#2a313c",
    border_strong="#3a424d",
    text="#e6edf3",
    text_muted="#9ba6b3",
    text_subtle="#6e7681",
    primary="#4493f8",
    primary_hover="#5aa3ff",
    primary_pressed="#2f7ee0",
    primary_disabled="#26385a",
    on_primary="#ffffff",
    success="#4ade80",
    success_hover="#36c96c",
    warning="#fbbf24",
    danger="#f87171",
    focus_ring="#4493f8",
    selection="#1f3a5f",
)

_active: Palette = LIGHT


def set_active(palette: Palette) -> None:
    global _active
    _active = palette


def active() -> Palette:
    return _active
