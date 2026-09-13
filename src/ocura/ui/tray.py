from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ocura.application.presenter import SessionView

logger = logging.getLogger(__name__)


class Tray(QObject):
    openRequested = Signal()
    pauseToggled = Signal()
    breakRequested = Signal()
    quitRequested = Signal()

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._icon = QSystemTrayIcon(icon, self)
        self._menu = QMenu()

        self._open = QAction("Open Ocura", self)
        self._pause = QAction("Pause reminders", self)
        self._break = QAction("Take a break now", self)
        self._quit = QAction("Quit", self)

        self._open.triggered.connect(self.openRequested)
        self._pause.triggered.connect(self.pauseToggled)
        self._break.triggered.connect(self.breakRequested)
        self._quit.triggered.connect(self.quitRequested)

        self._menu.addAction(self._open)
        self._menu.addSeparator()
        self._menu.addAction(self._pause)
        self._menu.addAction(self._break)
        self._menu.addSeparator()
        self._menu.addAction(self._quit)

        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)

    def show(self) -> bool:
        """Show the icon, reporting whether it actually appeared.

        A QSystemTrayIcon that is constructed but never shown, or whose owner is
        collected, fails silently and leaves no way to reach the app once the
        window is hidden. Windows also files new icons into the hidden overflow
        area by default, which looks identical to a bug.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.error("no system tray available; Ocura will have no tray icon")
            return False

        self._icon.show()
        if not self._icon.isVisible():
            logger.error("the tray icon was shown but is not visible")
            return False

        logger.info("tray icon shown")
        return True

    def hide(self) -> None:
        self._icon.hide()

    def render(self, view: SessionView, tooltip: str) -> None:
        self._icon.setToolTip(tooltip)
        self._pause.setText("Resume reminders" if view.paused else "Pause reminders")
        self._pause.setEnabled(view.running)
        self._break.setEnabled(view.can_take_break_now)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.openRequested.emit()
