"""Theme tests need no Qt: the stylesheet is a string built from a dataclass."""

from __future__ import annotations

import re
from dataclasses import asdict, fields

import pytest

from ocura.ui.theme import DARK, DEFAULT_THEME, LIGHT, THEMES, Tokens, stylesheet

QSS_TEMPLATE_WITH_UNKNOWN = "QWidget {{ color: {no_such_token}; }}"


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_every_placeholder_resolves(tokens: Tokens):
    """The output still contains CSS braces, so look for {token} shapes only."""
    leftover = re.findall(r"\{[a-z_][a-z0-9_]*\}", stylesheet(tokens))
    assert leftover == []


def test_a_missing_token_fails_loudly_rather_than_silently():
    with pytest.raises(KeyError):
        QSS_TEMPLATE_WITH_UNKNOWN.format(**asdict(DARK))


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_the_stylesheet_is_not_empty_and_mentions_the_accent(tokens: Tokens):
    qss = stylesheet(tokens)
    assert len(qss) > 500
    assert tokens.accent in qss


def test_both_themes_define_the_same_token_set():
    assert {f.name for f in fields(DARK)} == {f.name for f in fields(LIGHT)}


def test_dark_is_the_default():
    assert DEFAULT_THEME == "dark"
    assert THEMES[DEFAULT_THEME] is DARK


def test_the_two_themes_actually_differ():
    dark, light = asdict(DARK), asdict(LIGHT)
    differing = {key for key, value in dark.items() if light[key] != value}
    # Colours change, the geometry and type scale do not.
    assert "bg" in differing and "text" in differing
    assert "space_m" not in differing and "font_size_m" not in differing


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_colour_tokens_are_hex(tokens: Tokens):
    colours = ("bg", "surface", "surface_raised", "border", "text", "text_muted", "accent")
    for name in colours:
        assert re.fullmatch(r"#[0-9a-f]{6}", getattr(tokens, name)), name


def test_no_widget_module_hardcodes_a_colour():
    """P6 must be able to restyle by editing tokens, not by hunting widgets."""
    from pathlib import Path

    ui = Path(__file__).resolve().parents[2] / "src" / "ocura" / "ui"
    offenders = []
    for path in ui.glob("*.py"):
        if path.name == "theme.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{3,8}\b", line):
                offenders.append(f"{path.name}:{number} hardcoded colour")
            # app.py applies the one stylesheet; no other module may style itself.
            if "setStyleSheet" in line and path.name != "app.py":
                offenders.append(f"{path.name}:{number} inline style")
    assert offenders == []


def test_no_widget_module_hardcodes_spacing():
    """Layout margins live in Python because QSS cannot reach them.

    They still come from the token module, so P6 can retune the rhythm in one
    place. Zero is allowed: it means "no margin", not a chosen size.
    """
    from pathlib import Path

    ui = Path(__file__).resolve().parents[2] / "src" / "ocura" / "ui"
    calls = re.compile(
        r"(setContentsMargins|setSpacing|addSpacing|setFixedWidth|setMaximumWidth)\("
    )
    literal = re.compile(r"\b[1-9]\d*\b")

    offenders = []
    for path in ui.glob("*.py"):
        if path.name == "theme.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if calls.search(line) and literal.search(line.split("(", 1)[1]):
                offenders.append(f"{path.name}:{number} {line.strip()}")
    assert offenders == []


def test_the_spacing_scale_is_the_one_that_was_agreed():
    from ocura.ui.theme import SPACING

    assert [SPACING.xs, SPACING.s, SPACING.sm, SPACING.m, SPACING.lg, SPACING.xl] == [
        4,
        8,
        12,
        16,
        24,
        32,
    ]


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_selection_is_marked_quietly(tokens: Tokens):
    """The current section should be legible, not the loudest thing on screen.

    A selected pill filled with the accent competes with everything else in an
    app whose whole premise is calm, so the fill is a near-surface tint and the
    accent survives only as a 2px edge.
    """

    def distance(a: str, b: str) -> int:
        return sum(abs(int(a[i : i + 2], 16) - int(b[i : i + 2], 16)) for i in (1, 3, 5))

    to_surface = distance(tokens.nav_selected, tokens.surface)
    to_accent = distance(tokens.nav_selected, tokens.accent)
    # A tint on a white sidebar has to be visible at all, so judge the ratio
    # rather than an absolute that only suits the dark theme.
    assert 0 < to_surface < 60
    assert to_surface * 3 < to_accent

    qss = stylesheet(tokens)
    checked = qss.split("#NavButton:checked")[1].split("}")[0]
    assert f"background: {tokens.nav_selected}" in checked
    assert f"border-left: 2px solid {tokens.accent}" in checked


# --- the break overlay ----------------------------------------------------
#
# The overlay's colours are a ladder, not a palette: what matters is the order
# of the rungs and the distance between them. Asserting the ladder rather than
# the values leaves P6 free to retune every one of them and still fails the
# moment the screen's own argument stops holding.


def relative_luminance(colour: str) -> float:
    """WCAG relative luminance of a #rrggbb string. No Qt needed for arithmetic."""

    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    red, green, blue = (int(colour[start : start + 2], 16) for start in (1, 3, 5))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(first: str, second: str) -> float:
    one, other = relative_luminance(first), relative_luminance(second)
    return (max(one, other) + 0.05) / (min(one, other) + 0.05)


def lightness(colour: str) -> float:
    """HSL lightness, which is what "25% luminance" means to the eye reading it."""
    channels = [int(colour[start : start + 2], 16) for start in (1, 3, 5)]
    return (max(channels) + min(channels)) / 2 / 255


def is_warm(colour: str) -> bool:
    red, green, blue = (int(colour[start : start + 2], 16) for start in (1, 3, 5))
    return red > green > blue


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_the_overlay_is_warm_dark_rather_than_neutral_grey(tokens: Tokens):
    """Neutral grey at this lightness reads as switched-off hardware."""
    assert is_warm(tokens.overlay_bg)
    assert lightness(tokens.overlay_bg) < 0.12


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_the_focus_shape_is_visible_but_never_radiant(tokens: Tokens):
    """A quarter of the way up from black: a distant object, not a light source."""
    assert 0.25 <= lightness(tokens.overlay_shape) <= 0.30


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_the_shape_is_the_dimmest_thing_on_the_break_screen(tokens: Tokens):
    """It was the brightest, on a screen whose whole job is to rest the eye."""
    against = tokens.overlay_bg
    for brighter in (tokens.overlay_cue, tokens.overlay_text_faint):
        assert contrast(tokens.overlay_shape, against) < contrast(brighter, against)


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_the_break_text_is_a_ladder_with_the_instruction_at_the_top(tokens: Tokens):
    against = tokens.overlay_bg
    instruction = contrast(tokens.overlay_text, against)
    secondary = contrast(tokens.overlay_text_muted, against)
    tip = contrast(tokens.overlay_text_faint, against)

    assert tip < secondary < instruction
    # The instruction is muted sand, not white: presence comes from size.
    assert contrast("#ffffff", against) > instruction * 2


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda t: t.name)
def test_every_break_overlay_colour_is_warm(tokens: Tokens):
    overlay = (
        tokens.overlay_bg,
        tokens.overlay_shape,
        tokens.overlay_cue,
        tokens.overlay_text,
        tokens.overlay_text_muted,
        tokens.overlay_text_faint,
    )
    assert [colour for colour in overlay if not is_warm(colour)] == []


def test_the_overlay_ladder_is_the_same_in_both_themes():
    """The break screen is one design, not two: a break is a break in any theme."""
    dark, light = asdict(DARK), asdict(LIGHT)
    overlay = [key for key in dark if key.startswith("overlay_")]
    assert overlay
    assert [key for key in overlay if dark[key] != light[key]] == []
