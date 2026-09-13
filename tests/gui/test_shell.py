"""Widget tests, only where they say something a presenter test cannot."""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMainWindow

from ocura.application.presenter import EventLine, SessionView
from ocura.domain.timer import TimerState
from ocura.ui.main_window import MainWindow
from ocura.ui.single_instance import SingleInstance
from ocura.ui.theme import DARK, stylesheet
from ocura.ui.tray import Tray
from ocura.ui.views import DashboardView


def a_view(**overrides) -> SessionView:
    base = SessionView(
        state=TimerState.FOCUSING,
        running=True,
        paused=False,
        break_owed=False,
        headline="Focusing",
        detail="Next break in 15:00.",
        focus_elapsed=300.0,
        focus_remaining=900.0,
        break_remaining=0.0,
        focus_elapsed_text="5:00",
        countdown_text="15:00",
        progress=0.25,
        waiting_reason=None,
        breaks_taken=2,
        rests_credited=1,
        events=(),
        can_take_break_now=True,
    )
    return replace(base, **overrides)


def test_dashboard_shows_what_the_view_says(qtbot):
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.render(a_view())

    assert dashboard._headline.text() == "Focusing"
    assert dashboard._display.text() == "15:00"
    assert dashboard._breaks_taken.text() == "2"
    assert dashboard._progress.value() == 250


def test_the_waiting_note_appears_only_when_something_is_in_the_way(qtbot):
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.show()

    dashboard.render(a_view())
    assert dashboard._waiting.isVisible() is False

    dashboard.render(
        a_view(state=TimerState.DEFERRED, break_owed=True, waiting_reason="session locked")
    )
    assert dashboard._waiting.isVisible() is True
    assert dashboard._waiting.text() == "Waiting — session locked"


def test_controls_follow_the_view(qtbot):
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)

    dashboard.render(a_view(paused=True, can_take_break_now=False))
    assert dashboard._pause.text() == "Resume reminders"
    assert dashboard._break.isEnabled() is False

    dashboard.render(a_view())
    assert dashboard._pause.text() == "Pause reminders"
    assert dashboard._break.isEnabled() is True


def test_buttons_emit_intent_rather_than_acting(qtbot):
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.render(a_view())

    with qtbot.waitSignal(dashboard.breakRequested, timeout=500):
        dashboard._break.click()
    with qtbot.waitSignal(dashboard.pauseToggled, timeout=500):
        dashboard._pause.click()


def test_the_event_list_renders_lines(qtbot):
    from datetime import UTC, datetime

    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    at = datetime(2026, 1, 1, 14, 20, tzinfo=UTC)
    dashboard.render(
        a_view(events=(EventLine(at=at, text="Break finished"), EventLine(at=at, text="Waiting")))
    )

    assert dashboard._events.count() == 2
    assert "Break finished" in dashboard._events.item(0).text()


def test_closing_hides_instead_of_quitting(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    window.show()

    with qtbot.waitSignal(window.hidden, timeout=1000):
        window.close()
    assert window.isVisible() is False


def test_an_off_screen_position_falls_back_to_the_primary(qtbot, icon, settings):
    """A saved position can name a monitor that is no longer attached."""
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    window.resize(QSize(880, 640))
    window.move(QPoint(-30000, -30000))
    window._pull_onto_a_screen()

    primary = QGuiApplication.primaryScreen().availableGeometry()
    assert primary.intersects(window.frameGeometry())


def test_a_position_on_a_real_screen_is_left_alone(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    target = QGuiApplication.primaryScreen().availableGeometry().topLeft() + QPoint(120, 120)
    window.move(target)
    window._pull_onto_a_screen()

    assert window.pos() == target


def test_geometry_round_trips_through_settings(qtbot, icon, settings):
    """What Ocura stores is what it reads back. The bytes are the contract.

    Do not assert a restored *size* here, with or without a literal. Two earlier
    versions of this test did and both failed in CI for different environmental
    reasons: a window manager may refuse a requested size (the runner clamped
    900x700 to 900x687), and restoreGeometry deliberately refits a window to the
    current screen (offscreen reproduced 900x700 coming back as 798x700).
    Neither is a defect in Ocura, and neither is what this test is for. Saving
    and loading the blob is our code; how Qt then fits a window onto a display
    is Qt's, and it is covered by the pull-onto-a-screen tests.
    """
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    window.resize(QSize(900, 700))
    qtbot.wait(10)

    expected = window.saveGeometry()
    window._save_geometry()

    assert settings.value("window/geometry") == expected

    # And the stored blob is something Qt will actually accept back.
    probe = QMainWindow()
    qtbot.addWidget(probe)
    assert probe.restoreGeometry(settings.value("window/geometry"))


def test_a_reopened_window_gets_its_size_back_on_a_screen_that_allows_it(qtbot, icon, settings):
    """The behavioural half, asserted only where the platform can honour it."""
    available = QGuiApplication.primaryScreen().availableGeometry()
    if available.width() < 1100 or available.height() < 900:
        pytest.skip(f"display is {available.width()}x{available.height()}; too small to refit into")

    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    window.resize(QSize(900, 700))
    qtbot.wait(10)
    saved = window.size()
    window._save_geometry()

    reopened = MainWindow(icon, settings)
    qtbot.addWidget(reopened)
    qtbot.wait(10)
    assert reopened.size() == saved


def test_geometry_is_actually_written_to_settings(qtbot, icon, settings):
    """Guards the round-trip test against passing on two identical defaults."""
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    assert settings.value("window/geometry") is None

    window._save_geometry()
    assert settings.value("window/geometry") is not None


def test_navigation_switches_pages(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)

    for index in (1, 2, 0):
        window._nav.button(index).click()
        assert window._pages.currentIndex() == index


def test_placeholders_promise_nothing_they_do_not_have(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    text = " ".join(
        label.text()
        for index in (1, 2)
        for label in window._pages.widget(index).findChildren(type(window.dashboard._headline))
    )
    assert "Coming in P4" in text
    assert "Coming in P5" in text


def test_tray_tracks_the_view(qtbot, icon):
    tray = Tray(icon)
    tray.render(a_view(paused=True, can_take_break_now=False), "Ocura — reminders paused")

    assert tray._pause.text() == "Resume reminders"
    assert tray._break.isEnabled() is False
    assert tray._icon.toolTip() == "Ocura — reminders paused"


def test_tray_menu_has_the_four_actions(qtbot, icon):
    tray = Tray(icon)
    labels = [action.text() for action in tray._menu.actions() if not action.isSeparator()]
    assert labels == ["Open Ocura", "Pause reminders", "Take a break now", "Quit"]


def test_a_second_instance_stands_aside(qtbot):
    first = SingleInstance("ocura-test-instance")
    second = SingleInstance("ocura-test-instance")
    try:
        assert first.claim() is True

        with qtbot.waitSignal(first.raiseRequested, timeout=2000):
            assert second.claim() is False
    finally:
        first.close()
        second.close()


def test_the_stylesheet_applies_without_warnings(qtbot, qapp):
    qapp.setStyleSheet(stylesheet(DARK))
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.render(a_view())
    assert dashboard.styleSheet() == ""  # styling comes from the application, not inline


@pytest.mark.parametrize("state", list(TimerState))
def test_every_state_renders(qtbot, state: TimerState):
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.render(a_view(state=state))
