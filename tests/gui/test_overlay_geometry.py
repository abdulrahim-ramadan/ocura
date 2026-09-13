"""Overlay geometry against the real screens, plus simulated hot-plug."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

from ocura.ui.overlay import OverlayManager, OverlayWindow, overlay_geometry


def test_a_window_covers_every_screen_completely(qtbot, qapp):
    manager = OverlayManager()
    manager.open()
    try:
        screens = QGuiApplication.screens()
        assert len(manager.windows) == len(screens)

        for screen, window in manager.windows.items():
            qtbot.addWidget(window)
            assert window.geometry() == screen.geometry()
            # Nothing of the screen is left showing, taskbar strip included.
            assert window.geometry().contains(screen.geometry())
    finally:
        manager.close()


def test_the_taskbar_area_is_covered_too(qapp):
    """availableGeometry would leave a bright strip along one edge."""
    for screen in QGuiApplication.screens():
        assert overlay_geometry(screen) == screen.geometry()


def test_a_portrait_screen_keeps_its_own_shape(qapp):
    """Each window takes its screen's aspect ratio, never the primary's."""
    for screen in QGuiApplication.screens():
        target = overlay_geometry(screen)
        assert target.width() == screen.geometry().width()
        assert target.height() == screen.geometry().height()
        assert (target.height() > target.width()) == (
            screen.geometry().height() > screen.geometry().width()
        )


def test_windows_do_not_overlap_each_other(qtbot, qapp):
    manager = OverlayManager()
    manager.open()
    try:
        rects = [window.geometry() for window in manager.windows.values()]
        for window in manager.windows.values():
            qtbot.addWidget(window)
        for i, first in enumerate(rects):
            for second in rects[i + 1 :]:
                assert not first.intersects(second)
    finally:
        manager.close()


def test_the_overlay_never_takes_the_fullscreen_window_state(qtbot, qapp):
    """Exclusive fullscreen on several screens fights over the shell."""
    manager = OverlayManager()
    manager.open()
    try:
        for window in manager.windows.values():
            qtbot.addWidget(window)
            assert not window.isFullScreen()
    finally:
        manager.close()


def test_opening_twice_does_not_double_up(qtbot, qapp):
    manager = OverlayManager()
    manager.open()
    try:
        first = set(manager.windows)
        manager.open()
        assert set(manager.windows) == first
    finally:
        manager.close()


def test_closing_removes_every_window(qtbot, qapp):
    manager = OverlayManager()
    manager.open()
    manager.close()
    assert manager.windows == {}
    assert manager.is_open is False


def test_a_screen_appearing_mid_break_gets_its_own_window(qtbot, qapp, monkeypatch):
    """Simulated: unplugging a monitor cannot be arranged from a test."""
    real = QGuiApplication.screens()
    if len(real) < 2:
        import pytest

        pytest.skip("needs two screens to simulate one arriving")

    manager = OverlayManager()
    monkeypatch.setattr(QGuiApplication, "screens", staticmethod(lambda: real[:1]))
    manager.open()
    try:
        assert len(manager.windows) == 1

        monkeypatch.setattr(QGuiApplication, "screens", staticmethod(lambda: real))
        manager._on_screens_changed()

        assert set(manager.windows) == set(real)
        for screen, window in manager.windows.items():
            qtbot.addWidget(window)
            assert window.geometry() == screen.geometry()
    finally:
        manager.close()


def test_a_screen_disappearing_mid_break_closes_only_its_window(qtbot, qapp, monkeypatch):
    real = QGuiApplication.screens()
    if len(real) < 2:
        import pytest

        pytest.skip("needs two screens to simulate one leaving")

    manager = OverlayManager()
    manager.open()
    try:
        going = real[-1]
        staying = real[0]
        monkeypatch.setattr(QGuiApplication, "screens", staticmethod(lambda: [staying]))
        manager._on_screen_removed(going)

        assert set(manager.windows) == {staying}
        assert manager.windows[staying].geometry() == staying.geometry()
    finally:
        manager.close()


def test_losing_every_screen_is_survivable(qtbot, qapp, monkeypatch, caplog):
    """A remote session disconnecting takes every display with it."""
    manager = OverlayManager()
    manager.open()
    try:
        monkeypatch.setattr(QGuiApplication, "screens", staticmethod(list))
        manager._on_screens_changed()

        assert manager.windows == {}
        assert manager.is_open is True  # the break is still running
    finally:
        manager.close()


def test_a_resolution_change_moves_the_existing_window(qtbot, qapp):
    manager = OverlayManager()
    manager.open()
    try:
        screen = next(iter(manager.windows))
        window = manager.windows[screen]
        qtbot.addWidget(window)

        window.setGeometry(QRect(10, 10, 200, 200))
        manager._on_screens_changed()

        assert window.geometry() == screen.geometry()
    finally:
        manager.close()


def test_a_bare_window_carries_the_right_flags(qtbot, qapp):
    from PySide6.QtCore import Qt

    window = OverlayWindow()
    qtbot.addWidget(window)
    flags = window.windowFlags()

    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    # Esc has to reach it, so it must accept focus. The toast is the half that
    # must not.
    assert not (flags & Qt.WindowType.WindowDoesNotAcceptFocus)
