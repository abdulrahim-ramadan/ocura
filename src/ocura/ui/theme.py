"""Design tokens and the stylesheet built from them.

P6 is the polish milestone. The point of this file is that P6 can restyle Ocura
by editing the token values below, without going hunting through widgets — so
there are no inline styles anywhere in the UI, and no widget names a colour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources

#: Read as package data, not as a path beside __file__: a frozen build has no
#: source tree, and this is the same route the icon takes.
QSS_PACKAGE = "ocura.ui"
QSS_NAME = "style.qss"


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

    #: The week chart's bars. A colour of their own rather than a border or a
    #: surface reused: bars are data, and P6 retuning the chrome should not
    #: silently retune the one thing on the page that is a measurement.
    #:
    #: There is exactly one bar colour. Today's column is drawn in the accent
    #: instead — which marks *which day is now*, the same job the accent does
    #: in the sidebar, and is not a judgement about the day. Nothing on this
    #: page colours a day as good or bad, because nothing on this page has an
    #: opinion about a day.
    chart_bar: str

    #: Selection is marked, not shouted: a barely-there tint plus a thin accent
    #: edge. The loudest thing on screen should never be "which tab am I on".
    nav_selected: str

    #: The break overlay is warm and dark in BOTH themes. A break screen exists
    #: to rest the eye, and a bright white one at the end of a focus block is
    #: the opposite of that — so this is the one surface the light theme does
    #: not lighten. The values live in _OVERLAY: the ladder they form is the
    #: whole design of that screen, and it is written down in one place rather
    #: than reassembled by reading widgets.
    overlay_bg: str
    overlay_shape: str
    overlay_cue: str
    overlay_text: str
    overlay_text_muted: str
    overlay_text_faint: str

    font_family: str
    font_size_s: str
    font_size_m: str
    font_size_l: str
    font_size_xl: str
    font_size_xxl: str
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
    #: The break instruction and nothing else. Between xl and display because
    #: it is the only sentence on its screen and has to carry it alone.
    "font_size_xxl": "32px",
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

#: The break overlay, identical in both themes.
#:
#: The ratios in the comments are WCAG contrast against overlay_bg, measured
#: rather than guessed, because the ordering *is* the design: the instruction
#: is the only thing meant to be read, the shape is meant to be looked past,
#: and the tip is meant to be found only if it is looked for.
_OVERLAY = {
    #: Low-saturation brown-charcoal. Neutral grey at this lightness reads as
    #: switched-off hardware; the warmth is what makes it read as dimmed.
    "overlay_bg": "#1a1512",
    #: 27% lightness — a distant object, not a light source. Painted with a
    #: radial falloff, so it has no edge for the eye to fixate on.    1.9:1
    "overlay_shape": "#4f453b",
    #: The eyelid cue, a shade brighter than the shape because it is a gesture
    #: that has to register inside a second.                          2.9:1
    "overlay_cue": "#6a5f52",
    #: Muted sand, never white. The instruction gets its presence from size,
    #: not from luminance.                                            7.6:1
    "overlay_text": "#b8a68c",
    #: The countdown and the controls: secondary by contrast as well as by
    #: size, so neither competes with the instruction.                5.1:1
    "overlay_text_muted": "#8c8172",
    #: The tip. The faintest text on the screen by a wide margin — it is there
    #: for whoever goes looking, and for nobody else.                 2.2:1
    "overlay_text_faint": "#554d43",
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
    chart_bar="#38444c",
    nav_selected="#1f2428",
    **_OVERLAY,
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
    chart_bar="#ccd7de",
    nav_selected="#eaeef1",
    **_OVERLAY,
    **_SHARED,
)

THEMES = {theme.name: theme for theme in (DARK, LIGHT)}
DEFAULT_THEME = DARK.name


#: The two directional placeholders in the stylesheet, resolved per language.
#:
#: **Qt does not mirror a stylesheet.** It mirrors layouts, alignment and the
#: direction text flows in, but `border-left` in QSS means the left border in
#: Arabic exactly as it does in English — so the accent that marks the current
#: section was drawn down the far edge of a right-hand sidebar, pointing away
#: from the words it belongs to. Every directional rule is written in terms of
#: the *reading* edges instead, and the stylesheet is rebuilt when the language
#: changes.
def _edges(rtl: bool) -> dict[str, str]:
    """`edge_start` is the edge reading begins at; `edge_end` is the other."""
    return {
        "edge_start": "right" if rtl else "left",
        "edge_end": "left" if rtl else "right",
    }


def stylesheet(tokens: Tokens, rtl: bool = False) -> str:
    """The one stylesheet, in one theme, for one reading direction.

    `rtl` defaults to False so that every caller who has no opinion — every
    test that asks about colour, and the self-check — gets what they always
    got. The application is the one caller that has an opinion.
    """
    template = (resources.files(QSS_PACKAGE) / QSS_NAME).read_text(encoding="utf-8")
    return template.format(**asdict(tokens), **_edges(rtl))
