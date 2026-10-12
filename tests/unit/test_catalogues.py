"""Every string in the source reaches every catalogue, with every plural form.

**lupdate fails silently, so its output is checked against the source.** Its
Python parser extracts a counted call only when the count is a single token,
a name or a number: `int(x)`, `x.count`, `x // 2`, `x + 1`, `x[0]` and a
keyword `n=` each make it skip that message without a word. And
`update_translations.py --check` cannot notice, because it compares lupdate's
output with lupdate's output. So the strings are found here by walking the
AST, and one lupdate never extracted fails as missing. That would otherwise
reach the screen as English in a language that is not English, with nothing
anywhere saying so.

A count goes through Qt's numerus machinery (see `ocura.application.i18n`):
the source holds `%n`, the catalogue holds one form per plural category, and
Qt picks by the language's rule. Arabic has six — zero, one, two, few (3-10),
many (11-99), other — and German and English two each.

**Nothing in the toolchain guarantees that on its own.** lupdate cannot flag
a counted message from Python, strips a flag it did not set along with all
but the first form, and silently skips a counted call whose count is an
expression. `scripts/update_translations.py` works around all of it;
this is what notices when the workaround stops working. So the counted
messages are found by reading the source, not by trusting the catalogue to
list them, and a message lupdate dropped fails here as missing.

No Qt: the catalogues are XML and the source is Python.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "ocura"
CATALOGUES = SRC / "ui" / "i18n"

#: Plural categories per language, in Qt's order.
FORMS = {"ar": 6, "de": 2, "en": 2}

ARABIC_TWO, ARABIC_FEW, ARABIC_MANY = 2, 3, 4

#: Calls lupdate extracts a source from: (context, text) are the first two.
MARKERS = frozenset({"translate", "QT_TRANSLATE_NOOP"})

#: A count spliced into a sentence by hand, which is the thing numerus replaces.
SPLICED = re.compile(r"%\d (hours?|minutes?|seconds?|times|days?|breaks?)\b|^1 [a-z]")

#: The one exemption: a fraction of a second has no plural category, because
#: Qt's count is an integer, and takes the single form a decimal takes.
FRACTION = "a fraction, never a whole number"


def _name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def translatable_calls() -> list[tuple[str, ast.Call, Path]]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _name(node) in MARKERS and len(node.args) >= 2:
                text = _literal(node.args[1])
                if text is not None:
                    found.append((text, node, path))
    return found


def counted_in_source() -> set[tuple[str, str]]:
    return {
        (_literal(call.args[0]) or "", text)
        for text, call, _ in translatable_calls()
        if "%n" in text
    }


def catalogue(language: str) -> dict[tuple[str, str], ElementTree.Element]:
    root = ElementTree.parse(CATALOGUES / f"ocura_{language}.ts").getroot()
    return {
        (context.findtext("name") or "", message.findtext("source") or ""): message
        for context in root
        for message in context.findall("message")
    }


@pytest.mark.parametrize("language", ["ar", "de"])
def test_every_string_in_the_source_is_in_the_catalogue(language):
    """English is the source and its catalogue holds counts only; see below."""
    messages = catalogue(language)
    missing = sorted(
        f"{path.relative_to(SRC)}:{call.lineno} [{_literal(call.args[0])}] {text!r}"
        for text, call, path in translatable_calls()
        if (_literal(call.args[0]) or "", text) not in messages
    )
    assert not missing, "lupdate did not extract these:\n" + "\n".join(missing)


def test_the_scan_finds_the_strings():
    """A guard on the AST walk itself: one that silently stopped matching would
    make the test above pass over nothing."""
    assert len(translatable_calls()) > 100


def test_the_counted_messages_are_found():
    """A guard on the scan itself: an AST walk that silently stopped matching
    would make every test below pass over nothing."""
    counted = counted_in_source()
    assert ("Units", "%n minutes") in counted
    assert ("Statistics", next(s for c, s in counted if c == "Statistics")) in counted
    assert len(counted) >= 5


@pytest.mark.parametrize("language", sorted(FORMS))
def test_every_counted_message_has_every_plural_form(language):
    messages = catalogue(language)
    problems = []
    for key in sorted(counted_in_source()):
        message = messages.get(key)
        if message is None:
            problems.append(f"missing {key}")
            continue
        forms = [form.text or "" for form in message.iter("numerusform")]
        translation = message.find("translation")
        if message.get("numerus") != "yes":
            problems.append(f"not flagged as counted {key}")
        if len(forms) != FORMS[language] or not all(forms):
            written = sum(1 for form in forms if form)
            problems.append(f"{written} of {FORMS[language]} forms {key}")
        if translation is not None and translation.get("type") == "unfinished":
            problems.append(f"unfinished {key}")
    assert not problems, "\n".join(problems)


def test_the_arabic_forms_are_not_one_form_copied_six_times():
    """The dual and the 3-10 plural are the two forms a hand-rolled rule gets
    wrong, so a catalogue that fills six slots with the 11-99 form passes the
    count above and is still wrong."""
    messages = catalogue("ar")
    for key in counted_in_source():
        forms = [form.text for form in messages[key].iter("numerusform")]
        assert forms[ARABIC_TWO] != forms[ARABIC_MANY], f"dual is the 11-99 form: {key}"
        assert forms[ARABIC_FEW] != forms[ARABIC_MANY], f"3-10 is the 11-99 form: {key}"


def test_the_english_catalogue_holds_only_counted_messages():
    """Every other English sentence is the source itself; a copy in the
    catalogue would be free to disagree with it."""
    stray = [key for key in catalogue("en") if "%n" not in key[1]]
    assert not stray


def test_no_count_is_spliced_into_a_sentence_by_hand():
    """`"%1 minutes".replace("%1", ...)` and a separate `"1 minute"` are the
    hand-rolled plural this file exists to prevent coming back."""
    spliced = []
    for text, call, path in translatable_calls():
        disambiguation = _literal(call.args[2]) if len(call.args) > 2 else None
        if SPLICED.search(text) and disambiguation != FRACTION:
            spliced.append(f"{path.relative_to(SRC)}:{call.lineno} {text!r}")
    assert not spliced, "\n".join(spliced)


def test_a_count_reaches_translate_as_a_plain_name_or_number():
    """lupdate's Python parser skips a counted call whose count is itself an
    expression, without a word. The catalogue test would catch the result;
    this names the line that caused it."""
    bad = []
    for text, call, path in translatable_calls():
        if "%n" in text and _name(call) == "translate":
            count = call.args[3] if len(call.args) > 3 else None
            if not isinstance(count, ast.Name | ast.Constant):
                bad.append(f"{path.relative_to(SRC)}:{call.lineno} {text!r}")
    assert not bad, "\n".join(bad)
