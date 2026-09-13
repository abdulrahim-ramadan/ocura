"""The pre-break toast, and the one guarantee that matters most in P3."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLineEdit

from ocura.ui.toast import MARGIN, BreakToast, toast_position


def test_showing_the_toast_does_not_steal_the_keystroke(qtbot, qapp):
    """The whole point of a warning is that it arrives mid-sentence.

    A user typing when the toast appears must keep typing into their own
    window. This is the single most important behaviour in the milestone.
    """
    editor = QLineEdit()
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()
    qtbot.waitUntil(editor.hasFocus, timeout=2000)
    qtbot.keyClicks(editor, "half a sen")

    toast = BreakToast()
    qtbot.addWidget(toast)
    toast.render("A break in 0:45", can_snooze=True)
    toast.show_near_tray()
    qtbot.wait(150)

    assert editor.hasFocus(), "the toast took focus away from the user"
    assert not toast.isActiveWindow()

    qtbot.keyClicks(editor, "tence")
    assert editor.text() == "half a sentence"


def test_the_toast_carries_all_three_focus_defences(qtbot):
    toast = BreakToast()
    qtbot.addWidget(toast)
    flags = toast.windowFlags()

    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.Tool
    assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert toast.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_no_control_on_the_toast_can_be_focused(qtbot):
    """A focusable button would mean a focusable window."""
    toast = BreakToast()
    qtbot.addWidget(toast)

    from PySide6.QtWidgets import QPushButton

    for button in toast.findChildren(QPushButton):
        assert button.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_it_sits_in_the_work_area_near_the_tray(qtbot, qapp):
    screen = QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    position = toast_position(screen, (320, 120))

    assert area.contains(position)
    assert area.right() - (position.x() + 320) == MARGIN - 1
    assert area.bottom() - (position.y() + 120) == MARGIN - 1


def test_it_never_covers_the_taskbar(qtbot, qapp):
    """availableGeometry, unlike the overlay: a notification sits beside the
    shell, not on top of it."""
    screen = QGuiApplication.primaryScreen()
    position = toast_position(screen, (320, 120))
    assert screen.availableGeometry().contains(position)


def test_the_snooze_button_reports_intent(qtbot):
    toast = BreakToast()
    qtbot.addWidget(toast)
    toast.render("A break in 0:45", can_snooze=True)

    with qtbot.waitSignal(toast.snoozeRequested, timeout=1000):
        toast._snooze.click()


def test_the_snooze_button_disappears_once_the_cap_is_reached(qtbot):
    toast = BreakToast()
    qtbot.addWidget(toast)
    toast.show()

    toast.render("A break in 0:45", can_snooze=False)
    assert toast._snooze.isVisible() is False

    toast.render("A break in 0:45", can_snooze=True)
    assert toast._snooze.isVisible() is True


def test_it_says_what_is_coming_without_instructing(qtbot):
    toast = BreakToast()
    qtbot.addWidget(toast)
    toast.render("A break in 0:45", can_snooze=True)

    words = f"{toast._headline.text()} {toast._detail.text()}".lower()
    for bad in ("must", "should", "need to", "required", "failed", "missed"):
        assert bad not in words
