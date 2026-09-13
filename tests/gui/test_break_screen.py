from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from ocura.domain.timer import TimerState
from ocura.ui.break_screen import SHAPE_MIN_SCALE, BreakScreen
from ocura.ui.motion import Motion
from ocura.ui.overlay import OverlayWindow
from ocura.ui.theme import DARK, LIGHT, stylesheet

from .test_shell import a_view


def on_break(**overrides):
    base = a_view(
        state=TimerState.ON_BREAK,
        overlay_visible=True,
        break_remaining=14.0,
        countdown_text="0:14",
    )
    return replace(base, **overrides)


def test_the_message_invites_rather_than_instructs(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)
    words = screen._message.text().lower()

    assert "far away" in words
    for bad in ("must", "should", "have to", "required", "rest now"):
        assert bad not in words


def test_the_number_is_secondary_to_the_shape(qtbot, qapp):
    """The shape carries the break; the digits are for whoever wants them."""
    qapp.setStyleSheet(stylesheet(DARK))
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.resize(1200, 800)
    screen.show()
    qtbot.wait(50)

    # pixelSize, not pointSizeF: the stylesheet sets sizes in px, so points read -1.
    assert screen._countdown.font().pixelSize() < screen._message.font().pixelSize()
    assert screen.shape.height() > screen._countdown.height() * 4


@pytest.mark.parametrize("theme", [DARK, LIGHT])
def test_the_overlay_stays_dark_in_both_themes(qtbot, qapp, theme):
    """A bright break screen would undo the break it is announcing."""
    qapp.setStyleSheet(stylesheet(theme))
    window = OverlayWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)
    window.show()
    qtbot.wait(50)

    background = window.palette().color(QPalette.ColorRole.Window)
    assert background.lightness() < 40, f"{theme.name} overlay is not dark"


def test_the_shape_takes_its_colour_from_the_tokens(qtbot, qapp):
    qapp.setStyleSheet(stylesheet(DARK))
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.show()
    qtbot.wait(50)

    colour = screen.shape.palette().color(QPalette.ColorRole.WindowText)
    assert colour.name() == DARK.overlay_shape


def test_skip_and_snooze_report_intent(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.render(on_break())

    with qtbot.waitSignal(screen.skipRequested, timeout=1000):
        screen._skip.click()
    with qtbot.waitSignal(screen.snoozeRequested, timeout=1000):
        screen._snooze.click()


def test_the_snooze_control_disappears_at_the_cap(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.show()

    screen.render(on_break(can_snooze=False, snoozes_used=2))
    assert screen._snooze.isVisible() is False
    # Skip never goes away: the user must always be able to leave.
    assert screen._skip.isVisible() is True


def test_escape_ends_the_break(qtbot):
    window = OverlayWindow()
    qtbot.addWidget(window)
    window.show()

    with qtbot.waitSignal(window.skipRequested, timeout=1000):
        qtbot.keyClick(window, Qt.Key.Key_Escape)


def test_the_controls_are_keyboard_reachable(qtbot):
    """Unlike the toast, the overlay may take focus, so its buttons must."""
    screen = BreakScreen()
    qtbot.addWidget(screen)

    assert screen._skip.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert screen._snooze.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_reduced_motion_leaves_the_screen_still(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)

    Motion(enabled=False).recede(screen.shape, 20.0, SHAPE_MIN_SCALE)
    Motion(enabled=False).blink(screen.blink, 20.0)
    qtbot.wait(120)

    assert screen.shape.get_scale() == SHAPE_MIN_SCALE
    assert screen.blink.get_openness() == 1.0


def test_the_shape_recedes_and_settles(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.show()

    Motion(enabled=True).recede(screen.shape, 0.6, SHAPE_MIN_SCALE)
    qtbot.wait(150)
    assert SHAPE_MIN_SCALE < screen.shape.get_scale() < 1.0

    qtbot.waitUntil(
        lambda: screen.shape.get_scale() == pytest.approx(SHAPE_MIN_SCALE), timeout=3000
    )


def test_the_eyelid_closes_and_ends_open(qtbot):
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.show()

    seen = []
    Motion(enabled=True).blink(screen.blink, 0.9)
    for _ in range(30):
        qtbot.wait(30)
        seen.append(screen.blink.get_openness())

    assert min(seen) < 0.5, "the eyelid never closed"
    qtbot.waitUntil(lambda: screen.blink.get_openness() == 1.0, timeout=3000)


def test_the_break_screen_renders_on_a_portrait_shape(qtbot, qapp):
    """Sized by the short edge, with the leftover space left empty."""
    qapp.setStyleSheet(stylesheet(DARK))
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.resize(1080, 1920)
    screen.show()
    qtbot.wait(50)

    assert screen.shape.width() <= 1080
    # The shape does not stretch to fill the tall axis.
    assert screen.shape.height() < 1920
