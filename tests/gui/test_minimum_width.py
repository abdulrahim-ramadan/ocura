"""The smallest window Ocura allows is a window Ocura can actually be used in.

An invariant, in the way the colour and motion rules are: for every language,
at the window's own allowed minimum width, on every page, nothing is cut off
and no horizontal scrollbar appears. The minimum is computed, not chosen, and
nobody had ever checked the computation against the screen. When somebody did,
German allowed 723px for content that needs more, and Arabic 680px: the last
dashboard button was cut in half and Statistics slid sideways, in both.

**This drives the real `OcuraApp`, not a copy of its wiring.** Two of the
three faults that produced that were about order — the minimum measured
before the stylesheet had padded the buttons, and a language switch measured
before every widget had its new text — and a test that rebuilt the order by
hand would be testing its own reconstruction. The database is a throwaway
under `tmp_path`, the window geometry a throwaway INI, startup entries a
stand-in, and the history a fortnight of plausible days, because an empty
statistics page is narrower than a real one and would hide the widest page.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QAbstractButton, QScrollArea, QWidget

from ocura.application.session import SessionEvent, SessionEventKind
from ocura.application.settings import LANGUAGE_NAMES, Settings
from ocura.domain.timer import TimerState

#: Tall enough that the height is not what is being tested.
HEIGHT = 740

#: Longer than the page fade, so a page is measured where it settled.
SETTLE_MS = 400


def seed(path) -> None:
    """A week of history with every kind of entry the statistics page draws.

    Generous on purpose: the widest text on the page is the screen-time total,
    and a short week would measure a narrower page than a real user sees.
    """
    from ocura.infrastructure.storage import close_database, open_event_store

    connection, store = open_event_store(path)
    start = datetime.now().astimezone().replace(hour=9, minute=0, second=0, microsecond=0)
    for back in range(7):
        day = start - timedelta(days=back)
        for block in range(14):
            moment = day + timedelta(minutes=25 * block)
            store.record(
                SessionEvent(
                    kind=SessionEventKind.BREAK_DUE,
                    at=moment,
                    state=TimerState.FOCUSING,
                    duration=20 * 60.0,
                )
            )
            store.record(
                SessionEvent(
                    kind=SessionEventKind.BREAK_COMPLETED,
                    at=moment,
                    state=TimerState.FOCUSING,
                    duration=20.0,
                )
            )
        for reason in ("fullscreen or presenting", "idle for 240s", "session locked"):
            store.record(
                SessionEvent(
                    kind=SessionEventKind.BREAK_DEFERRED,
                    at=day + timedelta(hours=6),
                    state=TimerState.FOCUSING,
                    detail=reason,
                    duration=300.0,
                )
            )
    close_database(connection)


@pytest.fixture
def ocura(qapp, qtbot, tmp_path, monkeypatch):
    """A factory for the real application, in a language, and the cleanup after.

    The cleanup matters as much as the setup: the translator, the stylesheet
    and the layout direction belong to the QApplication every other test in
    the run shares.
    """
    from PySide6.QtCore import QSettings

    from ocura.infrastructure.storage import SettingsStore, close_database, open_event_store
    from ocura.ui.app import NoAutostart, OcuraApp

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    built: list[OcuraApp] = []

    def make(language: str) -> OcuraApp:
        from ocura.infrastructure.storage import default_database_path

        path = default_database_path()
        seed(path)
        connection, _ = open_event_store(path)
        SettingsStore(connection).save(Settings(language=language, introduced=True))
        close_database(connection)

        settings = QSettings(str(tmp_path / "shell.ini"), QSettings.Format.IniFormat)
        app = OcuraApp(qapp, settings=settings, autostart=NoAutostart())
        built.append(app)
        # start(), not show(): a running session is what the dashboard's first
        # button is labelled for, and "Restart session" is wider than "Start
        # session" in every language.
        app.start(first_run=False)
        qtbot.waitExposed(app.window)
        qtbot.wait(SETTLE_MS)
        return app

    yield make

    from PySide6.QtCore import QCoreApplication, QEvent

    for app in built:
        app.driver.stop()
        app.overlay.close()
        app.tray.hide()
        app.language.apply("en")
        # Deleted, not hidden: a hidden window still receives the next test's
        # LanguageChange and refreshes its statistics from a closed database.
        for widget in (app.window, app.toast, app.tray):
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        close_database(app._database)
    qapp.setStyleSheet("")
    qapp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)


def pages(window) -> list[int]:
    return [index for index in range(window._pages.count())]


def problems_on_current_page(window) -> list[str]:
    """Everything on the visible page that does not fit, in words.

    Two checks, because they fail differently. A horizontal scrollbar is the
    page admitting it is wider than the window. A widget whose right edge is
    past the viewport, or a button narrower than its own text, is clipping
    that a scrollbar policy could hide.
    """
    page = window._pages.currentWidget()
    scroller = page.findChild(QScrollArea, "Page")
    viewport = scroller.viewport()
    name = type(page).__name__
    found = []

    bar = scroller.horizontalScrollBar()
    if bar.isVisible() and bar.maximum() > 0:
        found.append(f"{name}: horizontal scrollbar, {bar.maximum()}px of overflow")

    for widget in scroller.widget().findChildren(QWidget):
        if not widget.isVisible() or widget.width() == 0:
            continue
        left = widget.mapTo(viewport, QPoint(0, 0)).x()
        if left < 0 or left + widget.width() > viewport.width():
            found.append(
                f"{name}: {type(widget).__name__} {widget.objectName()!r} spans "
                f"{left}..{left + widget.width()}, viewport is {viewport.width()} wide"
            )
        if isinstance(widget, QAbstractButton) and widget.width() < widget.sizeHint().width():
            found.append(
                f"{name}: button {widget.text()!r} is {widget.width()}px for "
                f"{widget.sizeHint().width()}px of text"
            )
    return found


def problems_at_minimum(app, qtbot) -> list[str]:
    """Every page at the allowed minimum, and the dashboard in both of the
    states that relabel its buttons: running, and paused."""
    window = app.window
    window.resize(window.minimumWidth(), HEIGHT)
    qtbot.wait(SETTLE_MS)
    found = (
        []
        if window.width() == window.minimumWidth()
        else [f"window is {window.width()}px, minimum is {window.minimumWidth()}px"]
    )
    for index in pages(window):
        window._nav.button(index).click()
        qtbot.wait(SETTLE_MS)
        found += problems_on_current_page(window)
    window._nav.button(0).click()
    qtbot.wait(SETTLE_MS)
    app.driver.toggle_paused()
    qtbot.wait(SETTLE_MS)
    found += [f"paused, {problem}" for problem in problems_on_current_page(window)]
    app.driver.toggle_paused()
    return found


@pytest.mark.parametrize("language", LANGUAGE_NAMES)
def test_the_allowed_minimum_fits_every_page(ocura, qtbot, language):
    app = ocura(language)
    window = app.window
    problems = problems_at_minimum(app, qtbot)
    assert not problems, f"at {window.minimumWidth()}px in {language}:\n" + "\n".join(problems)


@pytest.mark.parametrize(("first", "then"), [("en", "de"), ("de", "ar"), ("ar", "en")])
def test_the_minimum_follows_a_language_switch(ocura, qtbot, first, then):
    """Switched live, the way the Settings page does it. The minimum has to be
    the new language's, not the one before it."""
    app = ocura(first)
    app.apply_preferences(app.preferences.replace(language=then))
    qtbot.wait(SETTLE_MS)
    window = app.window
    problems = problems_at_minimum(app, qtbot)
    assert not problems, f"after {first} -> {then}, at {window.minimumWidth()}px:\n" + "\n".join(
        problems
    )
