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
class Spacing:
    """One scale, used by the stylesheet and by layout code alike.

    Layout margins live in Python because Qt layouts cannot be reached from QSS,
    so they read these values rather than carrying numbers of their own.
    """

    xs: int = 4
    s: int = 8
    sm: int = 12
    m: int = 16
    lg: int = 24
    xl: int = 32


@dataclass(frozen=True, slots=True)
class Layout:
    sidebar_width: int = 200
    #: Long lines are hard to read and a maximised window is very wide.
    content_max_width: int = 760
    #: Wide enough for one sentence, narrow enough to ignore.
    toast_width: int = 320


SPACING = Spacing()
LAYOUT = Layout()


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

    #: Selection is marked, not shouted: a barely-there tint plus a thin accent
    #: edge. The loudest thing on screen should never be "which tab am I on".
    nav_selected: str

    font_family: str
    font_size_s: str
    font_size_m: str
    font_size_l: str
    font_size_xl: str
    font_size_display: str

    space_xs: str
    space_s: str
    space_sm: str
    space_m: str
    space_lg: str
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
    "space_xs": f"{SPACING.xs}px",
    "space_s": f"{SPACING.s}px",
    "space_sm": f"{SPACING.sm}px",
    "space_m": f"{SPACING.m}px",
    "space_lg": f"{SPACING.lg}px",
    "space_xl": f"{SPACING.xl}px",
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
    accent_quiet="#243033",
    nav_selected="#1f2428",
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
    accent_quiet="#e4ecea",
    nav_selected="#eaeef1",
    **_SHARED,
)

THEMES = {theme.name: theme for theme in (DARK, LIGHT)}
DEFAULT_THEME = DARK.name


def stylesheet(tokens: Tokens) -> str:
    template = QSS_TEMPLATE.read_text(encoding="utf-8")
    return template.format(**asdict(tokens))
