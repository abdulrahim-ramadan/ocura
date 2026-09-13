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
