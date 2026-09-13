"""Design tokens and the stylesheet built from them.

P6 is the polish milestone. The point of this file is that P6 can restyle Ocura
by editing the token values below, without going hunting through widgets — so
there are no inline styles anywhere in the UI, and no widget names a colour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

QSS_TEMPLATE = Path(__file__).with_name("style.qss")


@dataclass(frozen=True, slots=True)
class Tokens:
    name: str

    bg: str
    surface: str
    surface_raised: str
    border: str

    text: str
    text_muted: str
    text_faint: str

    accent: str
    accent_text: str
    accent_quiet: str

    font_family: str
    font_size_s: str
    font_size_m: str
    font_size_l: str
    font_size_xl: str
    font_size_display: str

    space_xs: str
    space_s: str
    space_m: str
    space_l: str
    space_xl: str

    radius_s: str
    radius_m: str
    radius_l: str


_FONT = '"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'

_SHARED = {
    "font_family": _FONT,
    "font_size_s": "12px",
    "font_size_m": "14px",
    "font_size_l": "17px",
    "font_size_xl": "22px",
    "font_size_display": "44px",
    "space_xs": "4px",
    "space_s": "8px",
    "space_m": "16px",
    "space_l": "24px",
    "space_xl": "36px",
    "radius_s": "4px",
    "radius_m": "8px",
    "radius_l": "14px",
}

DARK = Tokens(
    name="dark",
    bg="#14171a",
    surface="#1b1f23",
    surface_raised="#22272c",
    border="#2c3238",
    text="#e6eaee",
    text_muted="#9aa5b1",
    text_faint="#6b7681",
    accent="#6ec6b8",
    accent_text="#0f1416",
    accent_quiet="#2f4f4a",
    **_SHARED,
)

LIGHT = Tokens(
    name="light",
    bg="#f4f6f8",
    surface="#ffffff",
    surface_raised="#ffffff",
    border="#dde3e9",
    text="#1b2126",
    text_muted="#5a6672",
    text_faint="#8a949e",
    accent="#2f6f67",
    accent_text="#ffffff",
    accent_quiet="#cfe6e1",
    **_SHARED,
)

THEMES = {theme.name: theme for theme in (DARK, LIGHT)}
DEFAULT_THEME = DARK.name


def stylesheet(tokens: Tokens) -> str:
    template = QSS_TEMPLATE.read_text(encoding="utf-8")
    return template.format(**asdict(tokens))
