from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ocura.application.presenter import SessionView


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

    def show(self) -> None:
        self._icon.show()

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
