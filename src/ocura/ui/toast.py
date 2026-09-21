"""The pre-break warning: a small window Ocura draws itself.

Not a QSystemTrayIcon balloon. supportsMessages() is False on at least one
development machine, and a capability that varies silently by machine is the
wrong foundation for the one message that has to arrive before a break.

**This window must never take keyboard focus.** It appears while the user is
mid-sentence by definition — that is the entire point of a warning — so a
stolen keystroke here is the worst failure in the milestone. Three separate
things enforce it, because any one of them alone is easy to undo by accident:

    Qt::WindowDoesNotAcceptFocus   the window manager will not activate it
    WA_ShowWithoutActivating       showing it does not raise it to the front
    Qt::Tool                       no taskbar entry, no alt-tab stop

The buttons are reachable by mouse only, deliberately. Giving them keyboard
focus would mean taking focus.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ocura.ui.theme import LAYOUT, SPACING

TOAST_FLAGS = (
    Qt.WindowType.Tool
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
)

#: Long enough to read, short enough not to become furniture. The warning also
#: closes itself when the break arrives, whichever comes first.
DISMISS_MS = 12_000

#: Clear of the tray without touching the screen edge.
MARGIN = SPACING.lg


def toast_position(screen: QScreen, size: tuple[int, int]) -> QPoint:
    """Bottom-right of the work area: beside the tray, never over the taskbar.

    availableGeometry here, unlike the overlay — this one is a notification and
    must sit where notifications sit, not on top of the shell.
    """
    area = screen.availableGeometry()
    width, height = size
    return QPoint(area.right() - width - MARGIN + 1, area.bottom() - height - MARGIN + 1)


class BreakToast(QWidget):
    snoozeRequested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, TOAST_FLAGS)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(LAYOUT.toast_width)

        self._headline = QLabel("")
        self._headline.setObjectName("ToastHeadline")
        self._detail = QLabel()
        self._detail.setObjectName("ToastDetail")
        self._detail.setWordWrap(True)

        self._snooze = QPushButton()
        self._snooze.setObjectName("ToastAction")
        self._snooze.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._snooze.clicked.connect(self.snoozeRequested)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self._snooze)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.m, SPACING.m, SPACING.m, SPACING.m)
        layout.setSpacing(SPACING.s)
        layout.addWidget(self._headline)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)
        self.retranslate()

    def retranslate(self) -> None:
        self._detail.setText(self.tr("Look at something far away when it arrives."))
        self._snooze.setText(self.tr("Not now"))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    def render(self, headline: str, can_snooze: bool) -> None:
        self._headline.setText(headline)
        self._snooze.setVisible(can_snooze)

    def show_near_tray(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        self.adjustSize()
        self.move(toast_position(screen, (self.width(), self.height())))
        # show() rather than raise_() or activateWindow(): both would defeat
        # WA_ShowWithoutActivating and put the keystroke at risk.
        self.show()
        QTimer.singleShot(DISMISS_MS, self._auto_dismiss)

    def _auto_dismiss(self) -> None:
        if self.isVisible():
            self.hide()
            self.dismissed.emit()
