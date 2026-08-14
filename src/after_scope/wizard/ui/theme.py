"""Theme: generates the full application stylesheet from the token palette.

`apply_theme(app)` picks light or dark from the OS colour scheme (the wizard is
a short-lived process, so a startup snapshot is enough), installs a matching
QPalette for native widgets, and sets the generated QSS.

Check-glyph and chevron images are written as small SVGs into the temp dir at
runtime so their colour follows the palette (QSS `image:` needs a file URL).
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtGui import QPalette as QtPalette

from . import tokens as t
from .tokens import DARK, LIGHT, Palette

log = logging.getLogger(__name__)

CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    '<path d="M3.5 8.5 L6.5 11.5 L12.5 4.5" fill="none" stroke="{color}"'
    ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
CHEVRON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
    '<path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="{color}"'
    ' stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def _ensure_assets(p: Palette) -> dict[str, str]:
    """Write palette-tinted SVGs; return {name: file-url} (forward slashes)."""
    out: dict[str, str] = {}
    base = Path(tempfile.gettempdir()) / "after_scope_ui" / p.name
    try:
        base.mkdir(parents=True, exist_ok=True)
        for name, template, color in (
            ("check", CHECK_SVG, p.on_primary),
            ("chevron", CHEVRON_SVG, p.text_muted),
        ):
            f = base / f"{name}.svg"
            f.write_text(template.format(color=color), encoding="utf-8")
            out[name] = f.as_posix()
    except OSError:
        log.warning("Could not write theme assets; using plain indicators", exc_info=True)
    return out


def detect_dark() -> bool:
    try:
        from PySide6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints()
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply_theme(app, mode: str = "auto") -> Palette:
    """mode: auto | light | dark. Returns the palette applied."""
    if mode == "dark" or (mode == "auto" and detect_dark()):
        palette = DARK
    else:
        palette = LIGHT
    t.set_active(palette)
    _apply_qpalette(app, palette)
    app.setStyleSheet(build_qss(palette))
    return palette


def _apply_qpalette(app, p: Palette) -> None:
    qp = QtPalette()
    qp.setColor(QtPalette.ColorRole.Window, QColor(p.bg))
    qp.setColor(QtPalette.ColorRole.Base, QColor(p.surface))
    qp.setColor(QtPalette.ColorRole.AlternateBase, QColor(p.surface_alt))
    qp.setColor(QtPalette.ColorRole.Text, QColor(p.text))
    qp.setColor(QtPalette.ColorRole.WindowText, QColor(p.text))
    qp.setColor(QtPalette.ColorRole.Button, QColor(p.surface))
    qp.setColor(QtPalette.ColorRole.ButtonText, QColor(p.text))
    qp.setColor(QtPalette.ColorRole.Highlight, QColor(p.selection))
    qp.setColor(QtPalette.ColorRole.HighlightedText, QColor(p.text))
    qp.setColor(QtPalette.ColorRole.PlaceholderText, QColor(p.text_subtle))
    qp.setColor(QtPalette.ColorRole.ToolTipBase, QColor(p.surface))
    qp.setColor(QtPalette.ColorRole.ToolTipText, QColor(p.text))
    app.setPalette(qp)


def build_qss(p: Palette) -> str:
    a = _ensure_assets(p)
    check = f'image: url("{a["check"]}");' if "check" in a else ""
    chevron = f'image: url("{a["chevron"]}");' if "chevron" in a else ""
    return f"""
* {{
    font-family: {t.FONT_FAMILY};
    font-size: {t.FS_BODY}px;
    color: {p.text};
}}
QWidget {{ background-color: {p.bg}; }}
QLabel {{ background: transparent; }}
QToolTip {{
    background: {p.surface}; color: {p.text};
    border: 1px solid {p.border_strong}; padding: {t.S1}px {t.S2}px;
}}

/* -- typography ------------------------------------------------------------- */
QLabel#pageTitle {{
    font-size: {t.FS_TITLE}px; font-weight: {t.FW_BOLD};
    padding: {t.S2}px 0 {t.S4}px 0;
}}
QLabel#caption {{ font-size: {t.FS_CAPTION}px; color: {p.text_subtle}; }}
QLabel#muted {{ color: {p.text_muted}; }}
QLabel#errorLabel {{ color: {p.danger}; font-weight: {t.FW_SEMIBOLD}; }}
QLabel#itemHelp, QLabel#solventInfo {{
    color: {p.text_muted}; font-size: {t.FS_CAPTION + 1}px; padding-left: {t.S6}px;
}}
QLabel#selectedUser {{
    font-size: {t.FS_H2}px; font-weight: {t.FW_SEMIBOLD};
    color: {p.primary}; padding: {t.S2}px 0;
}}

/* -- cards ------------------------------------------------------------------ */
QGroupBox {{
    font-weight: {t.FW_SEMIBOLD}; font-size: {t.FS_H3}px; color: {p.text};
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {t.R_LG}px;
    margin-top: {t.FS_H3 + 8}px;
    padding: {t.S5}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: {t.S5}px; top: 0; padding: 0 {t.S3}px; background: transparent;
}}

/* -- inputs ----------------------------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: {t.R_SM}px;
    padding: {t.S2 - 1}px {t.S2}px;
    color: {p.text};
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {p.focus_ring};
}}
QLineEdit:read-only {{ background: {p.surface_alt}; color: {p.text_muted}; }}
QComboBox::drop-down {{ border: none; width: {t.S6}px; }}
QComboBox::down-arrow {{ {chevron} width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {p.surface}; border: 1px solid {p.border_strong};
    selection-background-color: {p.selection}; selection-color: {p.text};
    outline: none;
}}

/* -- buttons ---------------------------------------------------------------- */
QPushButton {{
    background: {p.surface};
    border: 1px solid {p.border_strong};
    border-radius: {t.R_MD}px;
    padding: {t.S2 + 2}px {t.S4}px;
    color: {p.text};
}}
QPushButton:hover {{ background: {p.surface_alt}; border-color: {p.text_subtle}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.text_subtle}; border-color: {p.border}; }}

QPushButton#nextButton {{
    background: {p.primary}; border: 1px solid {p.primary};
    color: {p.on_primary}; font-weight: {t.FW_BOLD};
    padding: {t.S3}px {t.S6}px; font-size: {t.FS_BODY}px;
}}
QPushButton#nextButton:hover {{ background: {p.primary_hover}; border-color: {p.primary_hover}; }}
QPushButton#nextButton:pressed {{ background: {p.primary_pressed}; }}
QPushButton#nextButton:focus {{ border: 2px solid {p.focus_ring}; }}

QPushButton#bigYes {{
    background: {p.success}; border: 1px solid {p.success};
    color: {p.on_primary}; font-size: {t.FS_H2}px; font-weight: {t.FW_SEMIBOLD};
    padding: {t.S4}px {t.S7}px;
}}
QPushButton#bigYes:hover {{ background: {p.success_hover}; border-color: {p.success_hover}; }}

QPushButton#rosterButton {{
    font-size: {t.FS_H2}px; padding: {t.S4}px {t.S5}px;
    background: {p.surface}; border: 1px solid {p.border_strong};
    border-radius: {t.R_LG}px;
}}
QPushButton#rosterButton:hover {{ border-color: {p.primary}; color: {p.primary}; }}

QPushButton#skipLink {{
    background: transparent; border: none;
    color: {p.text_subtle}; text-decoration: underline;
    font-size: {t.FS_CAPTION}px; padding: {t.S1}px {t.S2}px;
}}
QPushButton#skipLink:hover {{ color: {p.text_muted}; }}

/* -- check / radio ---------------------------------------------------------- */
QCheckBox, QRadioButton {{ background: transparent; spacing: {t.S2}px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {p.border_strong};
    background: {p.surface};
}}
QCheckBox::indicator {{ border-radius: {t.R_SM - 1}px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {p.primary}; }}
QCheckBox::indicator:checked {{
    background: {p.primary}; border-color: {p.primary}; {check}
}}
QRadioButton::indicator:checked {{
    /* shrink the content box so the 5px ring still totals 18px -> stays circular */
    width: 8px; height: 8px;
    background: {p.on_primary}; border: 5px solid {p.primary}; border-radius: 9px;
}}

/* item-view check cells (e.g. the Junk column) follow the checkbox look */
QTableView::indicator, QTableWidget::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {p.border_strong}; border-radius: {t.R_SM - 1}px;
    background: {p.surface};
}}
QTableView::indicator:checked, QTableWidget::indicator:checked {{
    background: {p.primary}; border-color: {p.primary}; {check}
}}

/* -- tables ----------------------------------------------------------------- */
QTableView, QTableWidget {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: {t.R_MD}px;
    gridline-color: {p.border};
    selection-background-color: {p.selection};
    selection-color: {p.text};
    alternate-background-color: {p.surface_alt};
}}
QHeaderView::section {{
    background: {p.surface_alt}; color: {p.text_muted};
    border: none; border-bottom: 1px solid {p.border_strong};
    padding: {t.S2}px {t.S3}px; font-weight: {t.FW_SEMIBOLD};
}}
QTableCornerButton::section {{ background: {p.surface_alt}; border: none; }}

/* -- scrollbars ------------------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {p.border_strong}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {p.text_subtle}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* -- dialogs ---------------------------------------------------------------- */
QDialog {{ background: {p.bg}; }}
"""
