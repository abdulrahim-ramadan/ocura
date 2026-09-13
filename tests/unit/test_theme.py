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
