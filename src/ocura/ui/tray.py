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

    def retranslate(self) -> None:
        """The tray menu, in the language now active.

        A QObject rather than a QWidget, so no LanguageChange event arrives
        here — the application calls this directly when the language changes.
        A tray menu left in the old language is the most visible thing to miss,
        because it is the one part of Ocura that is always reachable.
        """
        self._open.setText(self.tr("Open Ocura"))
        self._break.setText(self.tr("Take a break now"))
        self._quit.setText(self.tr("Quit"))
        self._pause.setText(
            self.tr("Resume reminders") if self._paused else self.tr("Pause reminders")
        )

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._icon = QSystemTrayIcon(icon, self)
        self._menu = QMenu()

        self._open = QAction(self)
        self._pause = QAction(self)
        self._break = QAction(self)
        self._quit = QAction(self)
        self._paused = False
        self.retranslate()

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
        self._paused = view.paused
        self._pause.setText(
            self.tr("Resume reminders") if view.paused else self.tr("Pause reminders")
        )
        self._pause.setEnabled(view.running)
        self._break.setEnabled(view.can_take_break_now)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.openRequested.emit()
