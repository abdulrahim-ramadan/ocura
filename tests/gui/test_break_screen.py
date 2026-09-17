from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QRegion
from PySide6.QtWidgets import QWidget

from ocura.application.presenter import BREAK_TIPS
from ocura.domain.timer import TimerState
from ocura.ui.break_screen import CUE_SPAN, SHAPE_MIN_SCALE, BlinkCue, BreakScreen
from ocura.ui.motion import OVERLAY_FADE_MS, Motion
from ocura.ui.overlay import OverlayManager, OverlayWindow
from ocura.ui.theme import DARK, LIGHT, stylesheet

from .test_shell import a_view


def on_break(**overrides):
    base = a_view(
        state=TimerState.ON_BREAK,
        overlay_visible=True,
        break_remaining=14.0,
        countdown_text="0:14",
        tip=BREAK_TIPS[0],
    )
    return replace(base, **overrides)


def shown(qtbot, qapp, width=1920, height=1080) -> BreakScreen:
    """A break screen at a realistic size, styled, laid out and rendered."""
    qapp.setStyleSheet(stylesheet(DARK))
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.resize(width, height)
    screen.render(on_break())
    screen.show()
    qtbot.wait(50)
    return screen


def painted(widget) -> QImage:
    """What a paintEvent actually puts on the surface, on a known background.

    A widget rendered onto a filled image, because the questions here are about
    one paint routine's own geometry and alpha. Anything about how the overlay
    composites with the desktop is a question QWidget.render cannot answer
    either — that one is settled by capturing the real screen.

    DrawWindowBackground is off: the background here is the overlay token the
    widget will really sit on, and letting Qt paint its own would hide exactly
    the alpha this is measuring.
    """
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(DARK.overlay_bg))
    painter = QPainter(image)
    widget.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    painter.end()
    return image


def gone(window) -> bool:
    """Hidden, or disposed of outright — either way it is off the desktop."""
    try:
        return not window.isVisible()
    except RuntimeError:
        # The C++ object has been deleted, which is as gone as a window gets.
        return True


def drawn_width(image: QImage, row: int) -> int:
    background = QColor(DARK.overlay_bg)
    marked = [x for x in range(image.width()) if image.pixelColor(x, row) != background]
    return max(marked) - min(marked) + 1 if marked else 0


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


# --- composition ----------------------------------------------------------


def test_the_shape_sits_in_the_upper_third(qtbot, qapp):
    """It floated in the middle, which left the text stranded below it."""
    screen = shown(qtbot, qapp)
    centre = screen.shape.geometry().center().y()

    assert 0.20 < centre / screen.height() < 0.40


def test_the_shape_and_the_text_are_one_optical_group(qtbot, qapp):
    """The emptiness belongs at the outer edges, not between related things."""
    screen = shown(qtbot, qapp)

    inside = screen._message.geometry().top() - screen.shape.geometry().bottom()
    above = screen.shape.geometry().top()
    below = screen._tip.geometry().top() - screen.actions.geometry().bottom()

    assert inside < above, "more space inside the group than above it"
    assert inside < below, "more space inside the group than below it"


def test_the_tip_is_the_last_thing_on_the_screen(qtbot, qapp):
    """At the foot of the screen, and well clear of the controls."""
    screen = shown(qtbot, qapp)

    controls = screen.actions.geometry()
    assert screen._tip.geometry().top() > controls.bottom()
    assert screen.height() - screen._tip.geometry().bottom() < screen.height() * 0.1
    # Further from the buttons than the buttons are from the countdown.
    to_tip = screen._tip.geometry().top() - controls.bottom()
    to_countdown = controls.top() - screen._countdown.geometry().bottom()
    assert to_tip > to_countdown


# --- typography and controls ----------------------------------------------


def test_the_instruction_outweighs_everything_else_on_the_screen(qtbot, qapp):
    screen = shown(qtbot, qapp)
    instruction = screen._message.font().pixelSize()

    for quieter in (screen._countdown, screen._tip, screen._skip, screen._snooze):
        assert quieter.font().pixelSize() < instruction


def test_the_controls_are_padded_enough_to_look_deliberate(qtbot, qapp):
    """Too small to look intentional reads as an accident, not as an offer."""
    screen = shown(qtbot, qapp)

    for button in (screen._skip, screen._snooze):
        assert button.height() >= button.font().pixelSize() * 2.5
        assert button.width() >= button.height() * 1.5


# --- the evidence line ----------------------------------------------------


def test_the_tip_reaches_the_screen(qtbot, qapp):
    """It never had a widget to land in, and no view ever carried one to put there."""
    screen = shown(qtbot, qapp)

    assert screen._tip.text() == BREAK_TIPS[0]
    assert screen._tip.isVisible()
    assert screen._tip.geometry().height() > 0


def test_the_tip_is_the_faintest_text_on_the_screen(qtbot, qapp):
    screen = shown(qtbot, qapp)
    background = QColor(DARK.overlay_bg)

    def distance(label) -> int:
        colour = label.palette().color(QPalette.ColorRole.WindowText)
        return abs(colour.lightness() - background.lightness())

    assert distance(screen._tip) < distance(screen._countdown)
    assert distance(screen._tip) < distance(screen._message)


# --- the blink cue --------------------------------------------------------


def test_the_cue_is_a_third_of_the_width_rather_than_a_rule(qtbot, qapp):
    """A full-width hairline is a separator, and separators are furniture."""
    qapp.setStyleSheet(stylesheet(DARK))
    cue = BlinkCue()
    qtbot.addWidget(cue)
    cue.resize(1200, cue.height())
    cue.set_openness(1.0)

    assert drawn_width(painted(cue), cue.height() // 2) == pytest.approx(1200 * CUE_SPAN, rel=0.05)


def test_the_cue_closes_from_both_ends_towards_its_centre(qtbot, qapp):
    """A lid meets in the middle. Fading one out is not the same gesture."""
    qapp.setStyleSheet(stylesheet(DARK))
    cue = BlinkCue()
    qtbot.addWidget(cue)
    cue.resize(1200, cue.height())
    row = cue.height() // 2
    background = QColor(DARK.overlay_bg)

    widths = []
    for openness in (1.0, 0.6, 0.2):
        cue.set_openness(openness)
        image = painted(cue)
        widths.append(drawn_width(image, row))
        marked = [x for x in range(image.width()) if image.pixelColor(x, row) != background]
        # Still centred: it closes inwards, it does not retract to one side.
        assert (min(marked) + max(marked)) / 2 == pytest.approx(1200 / 2, abs=2)

    assert widths[0] > widths[1] > widths[2]


def test_the_cue_is_nearly_invisible_between_blinks(qtbot, qapp):
    """A line sitting there at full strength is read once and then ignored."""
    qapp.setStyleSheet(stylesheet(DARK))
    cue = BlinkCue()
    qtbot.addWidget(cue)
    cue.resize(1200, cue.height())
    row = cue.height() // 2
    background = QColor(DARK.overlay_bg)

    cue.set_openness(1.0)
    at_rest = painted(cue).pixelColor(600, row)
    cue.set_openness(0.3)
    closing = painted(cue).pixelColor(600, row)

    assert abs(at_rest.lightness() - background.lightness()) <= 6
    assert abs(closing.lightness() - background.lightness()) > 20


def test_the_cue_is_thicker_than_a_hairline(qtbot, qapp):
    qapp.setStyleSheet(stylesheet(DARK))
    cue = BlinkCue()
    qtbot.addWidget(cue)
    cue.resize(1200, cue.height())
    cue.set_openness(0.5)

    image = painted(cue)
    background = QColor(DARK.overlay_bg)
    rows = [y for y in range(cue.height()) if image.pixelColor(600, y) != background]

    assert len(rows) >= 6


# --- the focus shape ------------------------------------------------------


def test_the_shape_has_no_edge_to_fixate_on(qtbot, qapp):
    """A hard circle is a luminance step, which is exactly what pulls the eye."""
    screen = shown(qtbot, qapp)
    shape = screen.shape
    image = painted(shape)

    row = shape.height() // 2
    background = QColor(DARK.overlay_bg)
    marked = [x for x in range(shape.width()) if image.pixelColor(x, row) != background]
    assert marked, "the shape drew nothing"

    # Walk inwards from the rim: the step between neighbouring pixels stays
    # small the whole way, which is what "no edge" means in measurable terms.
    edge = min(max(marked), shape.width() - 2)
    steps = [
        abs(image.pixelColor(x, row).lightness() - image.pixelColor(x - 1, row).lightness())
        for x in range(edge - 40, edge + 2)
    ]
    assert max(steps) <= 4, f"a {max(steps)}-step edge is a thing to look at"


# --- arriving and leaving -------------------------------------------------


def test_the_overlay_fades_in_rather_than_appearing(qtbot, qapp, still):
    """A full screen changing in one frame is itself a shock to the eye."""
    still.enabled = True
    manager = OverlayManager()
    manager.open()
    try:
        windows = list(manager.windows.values())
        assert windows
        for window in windows:
            qtbot.addWidget(window)
            assert window.windowOpacity() < 1.0
        qtbot.waitUntil(
            lambda: all(w.windowOpacity() == pytest.approx(1.0) for w in windows),
            timeout=OVERLAY_FADE_MS * 5,
        )
    finally:
        manager.close()


def test_the_overlay_fades_out_and_is_gone_afterwards(qtbot, qapp, still):
    still.enabled = True
    manager = OverlayManager()
    manager.open()
    # Deliberately not handed to qtbot: the manager disposes of these itself,
    # and that disposal is what the test is about.
    windows = list(manager.windows.values())
    qtbot.wait(OVERLAY_FADE_MS + 100)

    manager.close()
    # The manager's own state never waits on an animation.
    assert manager.windows == {}
    assert manager.is_open is False

    qtbot.waitUntil(lambda: all(gone(window) for window in windows), timeout=OVERLAY_FADE_MS * 5)


def test_reduced_motion_opens_the_overlay_at_full_opacity(qtbot, qapp, still):
    """No fade, and above all no window left invisible on top of the desktop."""
    still.enabled = False
    manager = OverlayManager()
    manager.open()
    windows = list(manager.windows.values())
    try:
        for window in windows:
            assert window.windowOpacity() == pytest.approx(1.0)
    finally:
        manager.close()

    assert all(gone(window) for window in windows)
