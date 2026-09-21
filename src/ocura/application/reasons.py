"""Detector vocabulary, turned into something a person reads in their language.

A detector says `session locked` or `idle for 312s`. Those are not sentences
written for anybody — they are a vocabulary the context layer speaks, and they
are deliberately stable, because they are written into the event log and read
back out of it weeks later.

So they are folded here, at the moment they are shown, into a small set of
**families** that are marked for translation. Two rules come out of that, and
both of them are the reason this module exists rather than a `translate` call
at each of the four places a reason reaches a screen:

*The log keeps the detector's words, never the reader's.* A history written in
German and read in Arabic has to still mean the same thing, so nothing
translated is ever persisted. `phrase` is called on the way to a widget and
nowhere else.

*The folding happens before the translation, never after.* The statistics page
groups and counts these, and grouping translated strings would put two
spellings of the same family in two rows — or worse, group differently
depending on what language the window happened to be in.

Unknown reasons pass through verbatim, for the same reason the storage layer
keeps an event kind it has never heard of: a detector added later must show up
as itself on the day it ships rather than disappear into a bucket.
"""

from __future__ import annotations

from ocura.application.i18n import QT_TRANSLATE_NOOP, translate

#: One context for every reason, wherever it is rendered — the dashboard, the
#: tray, the event list and the statistics page all show the same words, and a
#: translator should be asked about them once.
REASONS_CONTEXT = "Reasons"

#: Raw detector text, matched by prefix, and the family it belongs to. The idle
#: detector writes the measured seconds into its reason — "idle for 312s" — so
#: an exact match would produce one family per deferral and a statistics page
#: nobody can read.
#:
#: `session lock` covers the lock detector's two words for the same fact: it
#: defers with "session locked" while the screen is locked and credits the rest
#: with "session lock" when it is unlocked. Both are the screen having been
#: locked, and a reader should not be shown two names for that.
FAMILIES: tuple[tuple[str, str], ...] = (
    ("idle for", QT_TRANSLATE_NOOP("Reasons", "Away from the keyboard")),
    ("session lock", QT_TRANSLATE_NOOP("Reasons", "Screen locked")),
    ("fullscreen or presenting", QT_TRANSLATE_NOOP("Reasons", "Fullscreen or presenting")),
    ("screensaver running", QT_TRANSLATE_NOOP("Reasons", "Screensaver running")),
    ("postponed", QT_TRANSLATE_NOOP("Reasons", "Postponed")),
)

#: What the presenter records when the user postpones a break themselves. Source
#: text, in the detectors' register rather than the reader's, because it goes
#: down the same path as a detector's reason and must fold the same way.
POSTPONED = "postponed"


def normalise(reason: str) -> str:
    """Fold a detector's reason into its family's source text."""
    folded = reason.strip().lower()
    for prefix, family in FAMILIES:
        if folded.startswith(prefix):
            return family
    return reason.strip()


def phrase(reason: str) -> str:
    """The family, in the language now active. For a screen, never for a file."""
    return translate(REASONS_CONTEXT, normalise(reason))
