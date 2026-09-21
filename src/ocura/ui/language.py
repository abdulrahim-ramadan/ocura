"""Loading a catalogue, and changing the language of a running application.

The Qt half of the port in `ocura.application.i18n`. A `QTranslator` is
installed on the application so that every `tr()` in a widget picks it up, and
the same catalogue is put behind `i18n.translate` so the application layer —
which cannot import Qt — reads from exactly the same file.

**The switch is live, and that is not a claim made lightly.** Installing a
translator makes Qt post `LanguageChange` to every widget, and every widget
here answers it by re-setting the strings it owns; everything else is computed
per render by a presenter, so the next tick carries it.
"""

from __future__ import annotations

import logging
from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from ocura.application import i18n
from ocura.application.settings import LANGUAGE_NAMES, SYSTEM_LANGUAGE

logger = logging.getLogger(__name__)

#: Where the compiled catalogues live, read as package data rather than as a
#: path beside __file__ — the same route the icon and the stylesheet take, and
#: the one that survives being packaged into a single executable.
CATALOGUE_PACKAGE = "ocura.ui.i18n"

#: English is the source language. There is no ocura_en.qm and there should not
#: be: the strings in the code are already English, and a catalogue that
#: translated English to English would be a second copy of every sentence,
#: free to disagree with the first.
SOURCE_LANGUAGE = "en"


def system_language() -> str:
    """The language Windows is set to, if Ocura has it, else English.

    `uiLanguages` rather than `QLocale.system().name()`: a machine set to
    Swiss German reports "de_CH", and the point is to match "de".
    """
    for tag in QLocale.system().uiLanguages():
        candidate = tag.replace("-", "_").split("_")[0].lower()
        if candidate in LANGUAGE_NAMES:
            return candidate
    return SOURCE_LANGUAGE


def resolve(language: str) -> str:
    """Turn a stored setting into the language that will actually be used."""
    if language == SYSTEM_LANGUAGE:
        return system_language()
    if language in LANGUAGE_NAMES:
        return language
    # A catalogue this build does not have. English rather than a refusal: an
    # unreadable interface is not improved by failing to start.
    logger.warning("no catalogue for %r; falling back to %s", language, SOURCE_LANGUAGE)
    return SOURCE_LANGUAGE


class QtTranslator:
    """`i18n.Translator` backed by Qt, so both layers read one catalogue."""

    def __init__(self, translator: QTranslator | None = None) -> None:
        self._translator = translator

    def translate(self, context: str, text: str) -> str:
        if self._translator is None:
            return text
        # An empty result means this catalogue has no entry, which is normal
        # for English and for anything added since the last lupdate run. The
        # source string is the answer in both cases.
        return self._translator.translate(context, text) or text


class Language:
    """Owns the translators installed on one QApplication.

    Holds them as attributes because Qt does not: `installTranslator` keeps a
    borrowed pointer, and a translator that Python garbage-collects takes the
    whole language with it on the next repaint.
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._ours: QTranslator | None = None
        self._qt: QTranslator | None = None
        self.current = SOURCE_LANGUAGE

    def resolve_current(self, language: str) -> str:
        """What `apply` would settle on, without applying it.

        So a caller can skip the work when nothing would change — switching
        from "follow Windows" to "German" on a German machine is not a change,
        and rebuilding every string for it would be a visible flicker for
        nothing.
        """
        return resolve(language)

    def apply(self, language: str) -> str:
        """Switch to this language now. Returns the one actually applied."""
        resolved = resolve(language)
        self._remove_existing()

        if resolved != SOURCE_LANGUAGE:
            self._ours = self._load_ours(resolved)
            self._qt = self._load_qt(resolved)

        i18n.install(QtTranslator(self._ours))
        self.current = resolved
        return resolved

    # --- internals ---------------------------------------------------------

    def _remove_existing(self) -> None:
        for translator in (self._ours, self._qt):
            if translator is not None:
                self._app.removeTranslator(translator)
        self._ours = self._qt = None

    def _load_ours(self, language: str) -> QTranslator | None:
        translator = QTranslator(self._app)
        name = f"ocura_{language}.qm"
        try:
            data = (resources.files(CATALOGUE_PACKAGE) / name).read_bytes()
        except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
            logger.warning("catalogue %s is missing: %s", name, exc)
            return None

        # Loading from bytes rather than from a path: package data has no
        # filesystem path once Ocura is packaged into one executable.
        if not translator.load(data, name):
            logger.warning("catalogue %s could not be read", name)
            return None

        # **The buffer is not copied.** QTranslator keeps a pointer into it and
        # reads from it for the rest of its life, so the bytes have to outlive
        # the translator. Letting `data` fall out of scope here is a
        # use-after-free whose only symptom is an interface that quietly stays
        # English — load() still returns True, isEmpty() still returns False,
        # and every translate() returns the empty string. It cost an hour to
        # find, because every step of it works when tried on its own in a
        # shell, where the buffer happens to still be referenced.
        translator._ocura_catalogue = data

        self._app.installTranslator(translator)
        return translator

    def _load_qt(self, language: str) -> QTranslator | None:
        """Qt's own strings, for the handful of places Qt speaks for itself.

        Missing on some installs, and not worth a warning louder than a debug
        line: what it covers is standard dialog buttons, and Ocura has almost
        none. Absent, they stay English while everything Ocura wrote does not.
        """
        translator = QTranslator(self._app)
        path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load(QLocale(language), "qtbase", "_", path):
            self._app.installTranslator(translator)
            return translator
        logger.debug("no Qt catalogue for %s in %s", language, path)
        return None


def install_language(app: QApplication, language: str) -> Language:
    handle = Language(app)
    handle.apply(language)
    return handle
