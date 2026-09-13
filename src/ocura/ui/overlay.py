"""Screen enumeration and geometry for the break overlay.

One window per screen, kept in step with whatever screens exist at the moment.
The visuals live elsewhere; this module decides only where windows go and when
they come and go.

Two ideas carry the whole design:

*Reconciliation, not bookkeeping.* Every screen event — added, removed,
resolution changed, primary changed — runs the same idempotent `_sync`, which
compares the windows that exist against the screens that exist and fixes the
difference. Bespoke add and remove paths drift out of step with each other the
first time two events arrive together; one function that can be called at any
time from any event cannot.

*Cover, do not capture.* The overlay is deliberately not a kiosk. It sets no
keyboard hook, holds no grab, runs no timer to re-assert itself above other
windows, and never takes the fullscreen window state. It covers the desktop and
that is all, so Ctrl+Alt+Del, the lock screen and the task switcher behave
exactly as they would if Ocura were not running — the secure desktop is a
separate desktop, and nothing here tries to follow it there.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QScreen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ocura.application.presenter import SessionView
from ocura.ui.break_screen import BreakScreen

logger = logging.getLogger(__name__)

OVERLAY_FLAGS = (
    Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
    # No WindowDoesNotAcceptFocus: Esc has to reach the overlay. The pre-break
    # toast is the half that must never take focus; by the time the overlay
    # appears the user has had their warning.
)


def plan[K](existing: Iterable[K], current: Iterable[K]) -> tuple[list[K], list[K]]:
    """Return (to_open, to_close) for a set of screens.

    Pure and key-agnostic so the reconciliation rule can be tested without a
    display, a QScreen, or a monitor to unplug.
    """
    have = list(existing)
    want = list(current)
    to_open = [key for key in want if key not in have]
    to_close = [key for key in have if key not in want]
    return to_open, to_close


def overlay_geometry(screen: QScreen) -> QRect:
    """The full screen rectangle, taskbar included.

    geometry() rather than availableGeometry(): a break screen that politely
    leaves the taskbar visible is a break screen with a bright strip along one
    edge, which is exactly the contrast the overlay exists to avoid.
    """
    return screen.geometry()


class OverlayWindow(QWidget):
    """One screen's worth of break overlay."""

    skipRequested = Signal()
    snoozeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, OVERLAY_FLAGS)
        self.setObjectName("Overlay")
        # Explicit geometry rather than showFullScreen(). The fullscreen window
        # state is per-window and Windows treats it as an exclusive mode, which
        # makes several of them fight over the shell and can leave one screen
        # uncovered.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAutoFillBackground(True)

        self.screen_content = BreakScreen(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.screen_content)

    def begin(self, seconds: float) -> None:
        self.screen_content.begin(seconds)

    def render(self, view: SessionView) -> None:
        self.screen_content.render(view)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Esc ends the break. The overlay covers the screen; it does not trap."""
        if event.key() == Qt.Key.Key_Escape:
            self.skipRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def place_on(self, screen: QScreen) -> None:
        """Bind to a screen before showing, so DPI is right from the first frame."""
        handle = self.windowHandle()
        if handle is None:
            self.createWinId()
            handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
        self.setGeometry(overlay_geometry(screen))


class OverlayManager(QObject):
    """Keeps exactly one overlay window on every screen, for as long as it is open."""

    skipRequested = Signal()
    snoozeRequested = Signal()

    def __init__(
        self,
        build: Callable[[], OverlayWindow] = OverlayWindow,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._build = build
        self._windows: dict[QScreen, OverlayWindow] = {}
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def windows(self) -> dict[QScreen, OverlayWindow]:
        return dict(self._windows)

    def open(self) -> None:
        if self._open:
            return
        self._open = True

        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screen_removed)
            app.primaryScreenChanged.connect(self._on_screens_changed)

        self._sync()

    def close(self) -> None:
        if not self._open:
            return
        self._open = False

        app = QGuiApplication.instance()
        if app is not None:
            app.screenAdded.disconnect(self._on_screens_changed)
            app.screenRemoved.disconnect(self._on_screen_removed)
            app.primaryScreenChanged.disconnect(self._on_screens_changed)

        for screen in list(self._windows):
            self._discard(screen)

    # --- reconciliation -----------------------------------------------------

    def _sync(self) -> None:
        if not self._open:
            return

        screens = QGuiApplication.screens()
        to_open, to_close = plan(self._windows, screens)

        for screen in to_close:
            self._discard(screen)
        for screen in to_open:
            self._create(screen)

        # Existing windows may have moved or changed resolution underneath us.
        for screen, window in self._windows.items():
            target = overlay_geometry(screen)
            if window.geometry() != target:
                window.place_on(screen)

        if not self._windows:
            # Every display went away: a remote session disconnected, or a
            # laptop lid closed with nothing else attached. Nothing to cover,
            # and the break carries on regardless — it is being timed by the
            # engine, not by this window.
            logger.warning("break overlay is open but no screens are available")

    def _on_screens_changed(self, *_: object) -> None:
        self._sync()

    def _on_screen_removed(self, screen: QScreen) -> None:
        # Drop this one explicitly before reconciling. Qt emits the signal while
        # the QScreen is still alive but about to be destroyed, and reading the
        # screen list here is not guaranteed to have caught up yet.
        self._discard(screen)
        self._sync()

    # --- window lifetime ----------------------------------------------------

    def render(self, view: SessionView) -> None:
        for window in self._windows.values():
            window.render(view)

    def begin(self, seconds: float) -> None:
        """Run the break animations on every window, once."""
        for window in self._windows.values():
            window.begin(seconds)

    def _create(self, screen: QScreen) -> None:
        window = self._build()
        window.skipRequested.connect(self.skipRequested)
        window.snoozeRequested.connect(self.snoozeRequested)
        self._windows[screen] = window
        screen.geometryChanged.connect(self._on_screens_changed)
        window.place_on(screen)
        window.show()
        window.raise_()
        # Only the first window takes focus, so Esc has somewhere to land
        # without the windows fighting each other for activation.
        if len(self._windows) == 1:
            window.activateWindow()
        logger.info("overlay opened on %s %s", screen.name(), overlay_geometry(screen))

    def _discard(self, screen: QScreen) -> None:
        window = self._windows.pop(screen, None)
        if window is None:
            return
        # The QScreen may already be gone, taking the connection with it.
        with contextlib.suppress(RuntimeError):
            screen.geometryChanged.disconnect(self._on_screens_changed)
        window.hide()
        window.deleteLater()
