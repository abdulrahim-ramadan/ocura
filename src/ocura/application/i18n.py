"""Translation, as a port, so the language does not drag Qt up the layers.

Most of Ocura's language lives in the application layer, on purpose: the rules
about it — calm, informational, never accusatory — are a product decision, and
`tests/unit/` asserts them without a display. That layer is banned from
importing PySide6, so `QObject.tr` and `QCoreApplication.translate` cannot be
used here.

**`translate` below is the seam.** It is an ordinary function that delegates to
whatever translator has been installed, and `QtTranslator` in the UI is the one
that knows about Qt. `NullTranslator` returns the source text, which is
English, which is why every existing headless test kept passing unchanged when
the strings were wrapped.

**It is also the name Qt Linguist looks for.** `pyside6-lupdate` extracts a
bare `translate("Context", "text")` call from a file that never imports
PySide6 — verified before any of this was written, because the whole design
rests on it. So the real Linguist workflow runs over the application layer
too, and no parallel extraction tool had to be invented.

Strings are translated **when they are rendered, never at import**. A module
constant translated at import is fixed to whatever the language was when Python
first read the file, which is the bug that makes a language switch look like it
half-worked. Constants are marked with `QT_TRANSLATE_NOOP` — extracted, not
translated — and passed through `translate` at the point of use.

**A count goes through Qt's numerus machinery, never through an `if`.** A
source containing `%n` is a counted message: `translate("Units", "%n minutes",
None, count)`, Qt's own argument order. The catalogue carries one form per
plural category of the language — six for Arabic, two for German and English —
and `QTranslator` picks by that language's rule. A hand-written `if n == 1`
gets English right and Arabic wrong in five cases out of six.

lupdate cannot flag these itself: its Python parser marks `numerus` only for
`self.tr(text, "", n)`, and a later run strips a flag set by hand along with
five of the six forms (both measured). `scripts/update_translations.py` sets
the flag on every `%n` source after extraction and carries the forms across,
and `tests/unit/test_plurals.py` fails if a catalogue loses one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Translator(Protocol):
    """Turns a source string into the active language."""

    def translate(
        self, context: str, text: str, disambiguation: str | None = None, n: int = -1
    ) -> str: ...


class NullTranslator:
    """No translation: the source string is the answer.

    Which is not a degraded mode. The source strings are English, so this is
    exactly what an English user gets, and it is what runs in every test that
    is not about translation.

    Except for a count. A `%n` source is written in its English plural, and
    the singular lives in the English catalogue, so without one "1 minutes" is
    what this produces — Qt's own behaviour with no catalogue loaded.
    """

    def translate(
        self, context: str, text: str, disambiguation: str | None = None, n: int = -1
    ) -> str:
        del context, disambiguation, n
        return text


_active: Translator = NullTranslator()


def install(translator: Translator | None) -> None:
    """Make this the translator every later `translate` call goes through."""
    global _active
    _active = translator or NullTranslator()


def active() -> Translator:
    return _active


def translate(context: str, text: str, disambiguation: str | None = None, n: int = -1) -> str:
    """Translate, and mark the literal for extraction.

    Called as a bare `translate("Context", "literal")`, which is the form
    `pyside6-lupdate` recognises. A call whose text is a variable still works
    at runtime — it is how a `QT_TRANSLATE_NOOP` constant is rendered — it just
    contributes nothing to extraction, which is correct, because the constant
    was already extracted where it was marked.

    With `n`, the source holds `%n` and the catalogue picks the plural form for
    that count; the number is substituted here, once, for every translator.
    Western digits, for the reason `clock_text` gives.
    """
    result = _active.translate(context, text, disambiguation, n)
    if n >= 0:
        result = result.replace("%n", str(n))
    return result


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:
    """Mark a literal for extraction without translating it yet.

    Qt's name, because that is the one lupdate recognises, and Qt's meaning.
    Used for module-level constants, which must hold source text so that the
    translation happens at render time and a language change is visible without
    a restart.
    """
    del context
    return text


#: Units, abbreviated, for figures that stand alone: a chart column, a tile, a
#: spin box. An abbreviation is a symbol rather than a counted noun and has one
#: form in all three languages — "3 س 40 د" is right for every number — so
#: these stay plain `%1` messages. A duration inside a sentence is words, and
#: goes through `duration_words`, which counts.


def duration_text(seconds: float | None) -> str:
    """Hours and minutes, abbreviated, with the whole pattern translated.

    The pattern rather than the unit, so each language owns its own spacing and
    word order: English renders "2h 15m", German "2 Std. 15 Min.", Arabic its
    own. Handing a translator a bare "h" to glue on would decide the spacing
    for them in a language they know better than this file does.

    Seconds of detail only below a minute. Above that these are totals over a
    day or a week, and forty seconds of screen time is false precision.
    """
    if seconds is None or seconds <= 0:
        return "—"
    if seconds < 60:
        return translate("Units", "%1s").replace("%1", str(round(seconds)))

    minutes = int(seconds / 60 + 0.5)
    if minutes < 60:
        return translate("Units", "%1m").replace("%1", str(minutes))

    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return translate("Units", "%1h").replace("%1", str(hours))
    return translate("Units", "%1h %2m").replace("%1", str(hours)).replace("%2", str(rest))


def duration_words(seconds: float) -> str:
    """A duration inside a sentence, spelled out: "20 minutes", "1 hour".

    Separate from `duration_text` because the two jobs pull opposite ways. A
    chart column wants "2h 15m" and seven of them across a card; a sentence
    wants words, and "appears here about 20m after you start" reads like a
    telegram.

    **Never rounds two different values into the same words.** A duration that
    is not a whole number of minutes is said in seconds instead. Rounding 610
    seconds to "10 minutes" beside an interval of 600 would produce "a warning
    10 minutes ahead would start before the interval of 10 minutes", which is a
    refusal that reads as a contradiction and tells the user nothing.

    Whole numbers are counted messages, so Arabic gets its dual and its 3-10
    plural: "5 ثوانٍ", not "5 ثانية". A fraction of a second has no plural
    category to pick — Qt's count is an integer — and takes the one form a
    decimal takes in all three languages.
    """
    if seconds <= 0:
        return duration_text(seconds)

    # Every count is a plain name by the time it reaches `translate`. lupdate's
    # Python parser silently skips a counted call whose count is itself a call,
    # and reads floor division as the start of a C++ comment, losing the
    # closing brackets and every call after it in the function. Both measured.
    exact = round(seconds, 3)
    hours, minutes, whole = int(seconds / 3600), int(seconds / 60), int(exact)

    if seconds % 3600 == 0:
        return translate("Units", "%n hours", None, hours)

    if seconds % 60 == 0:
        return translate("Units", "%n minutes", None, minutes)

    if exact == whole:
        return translate("Units", "%n seconds", None, whole)
    return translate("Units", "%1 seconds", "a fraction, never a whole number").replace(
        "%1", f"{exact:g}"
    )


def clock_text(seconds: float) -> str:
    """A countdown, as digits and colons.

    Not translated and not localised. The digits stay Western in every
    language: Ocura's countdown is read at a glance from the corner of the eye,
    and a script the reader has to parse is not a glance. Arabic-Indic digits
    are correct for prose in Arabic and wrong for a timer, which is why this
    formats with Python rather than QLocale.
    """
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
