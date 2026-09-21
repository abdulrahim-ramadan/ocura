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
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Translator(Protocol):
    """Turns a source string into the active language."""

    def translate(self, context: str, text: str) -> str: ...


class NullTranslator:
    """No translation: the source string is the answer.

    Which is not a degraded mode. The source strings are English, so this is
    exactly what an English user gets, and it is what runs in every test that
    is not about translation.
    """

    def translate(self, context: str, text: str) -> str:
        del context
        return text


_active: Translator = NullTranslator()


def install(translator: Translator | None) -> None:
    """Make this the translator every later `translate` call goes through."""
    global _active
    _active = translator or NullTranslator()


def active() -> Translator:
    return _active


def translate(context: str, text: str) -> str:
    """Translate, and mark the literal for extraction.

    Called as a bare `translate("Context", "literal")`, which is the form
    `pyside6-lupdate` recognises. A call whose text is a variable still works
    at runtime — it is how a `QT_TRANSLATE_NOOP` constant is rendered — it just
    contributes nothing to extraction, which is correct, because the constant
    was already extracted where it was marked.
    """
    return _active.translate(context, text)


def QT_TRANSLATE_NOOP(context: str, text: str) -> str:
    """Mark a literal for extraction without translating it yet.

    Qt's name, because that is the one lupdate recognises, and Qt's meaning.
    Used for module-level constants, which must hold source text so that the
    translation happens at render time and a language change is visible without
    a restart.
    """
    del context
    return text


#: Units, abbreviated. Ocura never writes "20 minutes" in a sentence it has to
#: translate, because plural forms do not survive the trip: lupdate cannot tell
#: which argument of a plain Python call is the count, so it marks nothing as
#: `numerus`, and Arabic has six plural forms that would then have nowhere to
#: live. An abbreviation has one form in all three languages, and every
#: sentence that needs a duration takes it through a `%1` placeholder instead.
UNITS_CONTEXT = "Units"


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
        return translate(UNITS_CONTEXT, "%1s").replace("%1", str(round(seconds)))

    minutes = int(seconds / 60 + 0.5)
    if minutes < 60:
        return translate(UNITS_CONTEXT, "%1m").replace("%1", str(minutes))

    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return translate(UNITS_CONTEXT, "%1h").replace("%1", str(hours))
    return translate(UNITS_CONTEXT, "%1h %2m").replace("%1", str(hours)).replace("%2", str(rest))


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

    **A known limit, stated rather than hidden.** Singular and plural are two
    source strings here, which is right for English and German and coarse for
    Arabic, where a dual and a small-number plural are also distinct. Qt's real
    plural machinery needs lupdate to mark a message `numerus`, and it cannot:
    it has no way to tell which argument of a plain Python call is the count.
    These are configured durations, so an Arabic translator can phrase the
    plural to read acceptably across the range a person would actually set.
    """
    if seconds <= 0:
        return duration_text(seconds)

    if seconds % 3600 == 0:
        hours = int(seconds // 3600)
        if hours == 1:
            return translate(UNITS_CONTEXT, "1 hour")
        return translate(UNITS_CONTEXT, "%1 hours").replace("%1", str(hours))

    if seconds % 60 == 0:
        minutes = int(seconds // 60)
        if minutes == 1:
            return translate(UNITS_CONTEXT, "1 minute")
        return translate(UNITS_CONTEXT, "%1 minutes").replace("%1", str(minutes))

    exact = round(seconds, 3)
    whole = int(exact) if exact == int(exact) else exact
    if whole == 1:
        return translate(UNITS_CONTEXT, "1 second")
    return translate(UNITS_CONTEXT, "%1 seconds").replace("%1", f"{whole:g}")


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
