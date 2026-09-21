"""No user-facing string reaches a screen without going through translation.

The same mechanical approach as the colour and spacing tests: the rule is
checked against the source that exists rather than against the intention, by
walking the AST of every module that can put text on a screen and finding the
literals that are handed to a widget or returned as language.

**Why an AST and not a grep.** A grep cannot tell `setText("Focusing")` from
`setObjectName("Headline")`, and the second is not language — it is the name a
stylesheet rule matches on, and translating it would unstyle the widget. Every
exemption below is a category like that, named and argued, rather than a list
of strings somebody appended to until the test went quiet.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "ocura"

#: Widget calls that put text in front of a person. `setSuffix` is here
#: because a spin box suffix is a unit, and a unit is a word in a language.
TEXT_SETTERS = frozenset(
    {
        "setText",
        "setWindowTitle",
        "setToolTip",
        "setPlaceholderText",
        "setSuffix",
        "setPrefix",
        "setStatusTip",
        "setWhatsThis",
        "setItemText",
        "setTitle",
        "setLabel",
        "setAccessibleName",
        "setAccessibleDescription",
    }
)

#: Constructors that take their label as the first argument.
TEXT_CONSTRUCTORS = frozenset(
    {"QPushButton", "QLabel", "QCheckBox", "QRadioButton", "QAction", "QGroupBox"}
)

#: Calls whose result is already translated, so a literal inside them is a
#: source string and exactly where it should be.
TRANSLATORS = frozenset({"tr", "translate", "QT_TRANSLATE_NOOP"})

#: Object names, stylesheet selectors and settings keys. Not language: an
#: object name is what a QSS rule matches on, and translating one would
#: silently unstyle the widget it names.
IDENTIFIER_SETTERS = frozenset({"setObjectName", "setValue", "value", "setProperty", "contains"})


def modules() -> list[Path]:
    """Every module that can put text on a screen: the UI and the layers whose
    job is to decide what the UI says."""
    return sorted(
        path
        for path in SRC.rglob("*.py")
        if path.parent.name in ("ui", "application") or path.parent.parent.name == "storage"
    )


def is_translated(node: ast.AST) -> bool:
    """True if this expression is, or is built from, a translation call."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in TRANSLATORS:
            return True
        # `translate(...).replace("%1", value)` — the literal is a placeholder
        # in a string that was translated a call earlier.
        if name == "replace" and isinstance(func, ast.Attribute):
            return is_translated(func.value)
        return False
    if isinstance(node, ast.IfExp):
        return is_translated(node.body) and is_translated(node.orelse)
    if isinstance(node, ast.BinOp):
        return is_translated(node.left) or is_translated(node.right)
    return False


def literal_in(node: ast.AST) -> str | None:
    """The user-visible literal in an expression, if it holds one.

    An f-string counts: it is a sentence with a value glued into it, which is
    the shape a translator cannot move around and the reason placeholders
    exist.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value or None
    if isinstance(node, ast.JoinedStr):
        return (
            "".join(part.value for part in node.values if isinstance(part, ast.Constant))
            or "<f-string>"
        )
    if isinstance(node, ast.IfExp):
        return literal_in(node.body) or literal_in(node.orelse)
    return None


def offenders_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue

        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")

        if name in IDENTIFIER_SETTERS or name in TRANSLATORS:
            continue

        if name in TEXT_SETTERS:
            argument = node.args[-1] if name == "setItemText" else node.args[0]
        elif name in TEXT_CONSTRUCTORS:
            argument = node.args[0]
        else:
            continue

        if is_translated(argument):
            continue
        text = literal_in(argument)
        if text:
            found.append(f"{path.name}:{node.lineno} {name}({text!r})")

    return found


def test_no_user_facing_string_reaches_a_widget_untranslated():
    """A literal handed straight to a widget is a string no translator will
    ever see, and the only way to find out is to run Ocura in German."""
    offenders = [problem for path in modules() for problem in offenders_in(path)]

    assert offenders == []


def test_the_check_would_actually_catch_one(tmp_path: Path):
    """A test that cannot fail is a test that proves nothing.

    Both shapes: the literal handed straight in, and the f-string that glues a
    value into a sentence.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from PySide6.QtWidgets import QLabel\n"
        "def build(w, n):\n"
        "    w.setText('Focusing')\n"
        "    w.setWindowTitle(f'{n} of 3')\n"
        "    return QLabel('Break soon')\n",
        encoding="utf-8",
    )

    offenders = offenders_in(probe)

    assert len(offenders) == 3
    assert any("Focusing" in problem for problem in offenders)
    assert any("of 3" in problem for problem in offenders)


def test_the_check_accepts_every_shape_the_codebase_actually_uses(tmp_path: Path):
    """The exemptions are categories, not a list of strings that went quiet."""
    probe = tmp_path / "ok.py"
    probe.write_text(
        "from PySide6.QtWidgets import QLabel\n"
        "def build(self, w, view, n):\n"
        "    w.setObjectName('Headline')\n"
        "    w.setText(self.tr('Focusing'))\n"
        "    w.setText(translate('Status', 'Focusing'))\n"
        "    w.setText(self.tr('%1 of %2').replace('%1', str(n)))\n"
        "    w.setText(self.tr('Stop') if n else self.tr('Start'))\n"
        "    w.setText(view.headline)\n"
        "    return QLabel(self.tr('Break soon'))\n",
        encoding="utf-8",
    )

    assert offenders_in(probe) == []


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_each_module_is_clean(path: Path):
    """Reported per module, so a failure names the file rather than a list."""
    assert offenders_in(path) == []
