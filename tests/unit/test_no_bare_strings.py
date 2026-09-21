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

Three rules, because one of them was not enough. The first — no literal into a
Qt text setter — is the obvious one, and it is the one that missed three real
defects found by running Ocura in German:

    self.toast.render(f"A break in {view.countdown_text}", ...)
    row.show_problem("Ocura cannot manage startup entries on this machine.")
    raise AutostartUnavailable("Windows would not let Ocura change ...")

None of those is a Qt setter. The first two are Ocura's own widget methods and
the third is an exception whose message the settings page prints under the
control that raised it. So:

*Rule 1* — no untranslated literal into a Qt text setter or a labelled widget.

*Rule 2* — in the two layers whose job is what the user reads, no
**sentence-shaped** literal anywhere in a call at all, translated or not. Two
or more letters and a space is a sentence written for a person; `"dark"`,
`"window/geometry"` and `"%1"` are not. This catches a sentence on its way
into any function, including one this codebase invented last week.

*Rule 3* — the message of an exception the interface **shows** must be
translated, wherever it is raised. `AutostartUnavailable` and `InvalidSettings`
are that list; every other error in Ocura goes to the log, where English is
correct and a translator would be a liability.
"""

from __future__ import annotations

import ast
import re
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


#: Sentence-shaped: two letters somewhere, and a space. `"Break soon"` is a
#: sentence; `"dark"`, `"%1"`, `"window/geometry"` and `"px"` are not.
SENTENCE = re.compile(r"[A-Za-z]{2}.*\s|\s.*[A-Za-z]{2}")

#: Log lines. English on purpose: they are read by whoever is debugging, and a
#: translated log is a log that cannot be searched for the string in the bug
#: report.
LOG_CALLS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})

#: Not language either. `basicConfig` is given a logging format, and the
#: self-check writes a console report for whoever is holding a broken build —
#: neither is ever rendered by a widget. The report is two functions rather
#: than one because the catalogue check needs a QApplication to say anything;
#: the category is "printed to a console, never shown in the interface", not
#: "a name that was convenient".
NOT_LANGUAGE_CALLS = frozenset({"basicConfig"})
NOT_LANGUAGE_FUNCTIONS = frozenset({"self_check", "_catalogue_report"})

#: The two exceptions whose message is put in front of a person rather than
#: into a log. Both are raised in layers that have no widgets, which is how
#: their text stayed English through a whole translation pass.
USER_FACING_ERRORS = frozenset({"AutostartUnavailable", "InvalidSettings"})


def call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


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


def not_language_in(tree: ast.Module) -> set[int]:
    """Node ids under a call or a function whose strings are not language.

    Returned as ids rather than as a filtered tree because the exemption is
    about where a literal sits, not about what it says: the same sentence is a
    source string inside `translate(...)` and a defect outside it.
    """
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in NOT_LANGUAGE_FUNCTIONS:
            exempt.update(id(child) for child in ast.walk(node))
        if isinstance(node, ast.Call) and (
            call_name(node) in TRANSLATORS | LOG_CALLS | NOT_LANGUAGE_CALLS
        ):
            exempt.update(id(child) for child in ast.walk(node))
        # `f"{seconds:02d}"` — a format spec is machine punctuation that
        # happens to be spelled with letters.
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue) and part.format_spec is not None:
                    exempt.update(id(child) for child in ast.walk(part.format_spec))
    return exempt


def sentences_in(path: Path) -> list[str]:
    """Rule 2: a sentence for a person, passed to anything at all."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    exempt = not_language_in(tree)
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if id(argument) in exempt:
                continue
            text = literal_in(argument)
            if text and SENTENCE.search(text):
                found.append(f"{path.name}:{argument.lineno} {call_name(node)}({text!r})")

    return found


def untranslated_errors_in(path: Path) -> list[str]:
    """Rule 3: the message of an error the interface shows.

    A `raise` whose argument holds no literal at all passes: the message came
    from somewhere else, and that somewhere is covered by the other two rules.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if call_name(node.exc) not in USER_FACING_ERRORS or not node.exc.args:
            continue
        message = node.exc.args[0]
        if is_translated(message):
            continue
        text = literal_in(message)
        if text:
            found.append(f"{path.name}:{node.lineno} {call_name(node.exc)}({text!r})")

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


# --- rule 2: a sentence, anywhere in a call --------------------------------


@pytest.mark.parametrize("path", modules(), ids=lambda path: path.name)
def test_no_module_assembles_a_sentence_outside_a_translation_call(path: Path):
    """The rule that would have caught the pre-break toast.

    `self.toast.render(f"A break in {countdown}")` is not a Qt setter, so rule
    one never looked at it, and the one message that has to arrive before a
    break stayed English in every language for a whole milestone.
    """
    assert sentences_in(path) == []


def test_rule_two_catches_a_sentence_handed_to_a_method_of_our_own(tmp_path: Path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        "def build(self, view, row):\n"
        "    self.toast.render(f'A break in {view.countdown_text}')\n"
        "    row.show_problem('Ocura cannot manage startup entries here.')\n",
        encoding="utf-8",
    )

    assert len(sentences_in(probe)) == 2


def test_rule_two_leaves_the_shapes_that_are_not_language_alone(tmp_path: Path):
    """Each line here is a category, not a string that was inconvenient."""
    probe = tmp_path / "ok.py"
    probe.write_text(
        "import logging\n"
        "def build(self, w, seconds, name):\n"
        "    logging.getLogger(__name__).warning('could not read the counter: %s', name)\n"
        "    w.setText(translate('Status', 'Break owed.'))\n"
        "    w.setText(self.tr('%1 left. Look somewhere far away.'))\n"
        "    w.setObjectName('BreakCountdown')\n"
        "    self._settings.value('window/geometry')\n"
        "    return f'{seconds:02d}'\n",
        encoding="utf-8",
    )

    assert sentences_in(probe) == []


# --- rule 3: the errors the interface shows --------------------------------


@pytest.mark.parametrize(
    "path", sorted(SRC.rglob("*.py")), ids=lambda path: f"{path.parent.name}/{path.name}"
)
def test_every_user_facing_error_is_raised_with_translated_text(path: Path):
    assert untranslated_errors_in(path) == []


def test_rule_three_catches_an_untranslated_message(tmp_path: Path):
    probe = tmp_path / "probe.py"
    probe.write_text(
        "def go(bad):\n"
        "    if bad:\n"
        "        raise AutostartUnavailable('Windows would not let Ocura change it.')\n"
        "    raise InvalidSettings(translate('Settings', 'Not a theme.'), 'theme')\n"
        "    raise StorageError('could not open history: %s' % bad)\n",
        encoding="utf-8",
    )

    offenders = untranslated_errors_in(probe)

    assert len(offenders) == 1
    assert "AutostartUnavailable" in offenders[0]
