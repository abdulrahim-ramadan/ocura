from __future__ import annotations

from PySide6.QtCore import QByteArray, QPoint, QRect, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ocura.application.presenter import SessionView
from ocura.ui.theme import LAYOUT, SPACING
from ocura.ui.views import DashboardView, PlaceholderView

DEFAULT_SIZE = QSize(880, 640)
MIN_SIZE = QSize(720, 520)


class MainWindow(QMainWindow):
    """Shell: navigation, geometry, and hide-to-tray. Renders nothing itself."""

    hidden = Signal()

    def __init__(self, icon: QIcon, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

        self.setWindowTitle("Ocura")
        self.setWindowIcon(icon)
        self.setMinimumSize(MIN_SIZE)

        self.dashboard = DashboardView()
        self._pages = QStackedWidget()
        self._pages.addWidget(self.dashboard)
        self._pages.addWidget(
            PlaceholderView(
                "Statistics",
                "Coming in P4. Ocura keeps nothing on disk yet, so there is no history "
                "to show — and inventing some would be worse than an empty page.",
            )
        )
        self._pages.addWidget(
            PlaceholderView(
                "Settings",
                "Coming in P5. Schedule and detector settings will live here once they "
                "can be saved.",
            )
        )

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(root)

        self._restore_geometry()

    def _sidebar(self) -> QWidget:
        from ocura.ui.views import _label  # same module, kept out of the public surface

        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(LAYOUT.sidebar_width)

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        layout.setSpacing(SPACING.xs)
        layout.addWidget(_label("Ocura", "Wordmark"))
        layout.addWidget(_label("Better screen habits.", "Tagline"))

        self._nav = QButtonGroup(self)
        self._nav.setExclusive(True)
        for index, name in enumerate(("Dashboard", "Statistics", "Settings")):
            button = QPushButton(name)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._nav.addButton(button, index)
            layout.addWidget(button)
        self._nav.idClicked.connect(self._pages.setCurrentIndex)

        layout.addStretch(1)
        return bar

    def render(self, view: SessionView) -> None:
        self.dashboard.render(view)

    def show_and_raise(self) -> None:
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    # --- geometry -----------------------------------------------------------

    def _restore_geometry(self) -> None:
        self.resize(DEFAULT_SIZE)
        saved = self._settings.value("window/geometry")
        if isinstance(saved, QByteArray) and self.restoreGeometry(saved):
            self._pull_onto_a_screen()
            return
        self._centre_on_primary()

    def _pull_onto_a_screen(self) -> None:
        """A saved position can point at a monitor that is no longer there.

        Restoring it blindly opens the window somewhere invisible and looks
        exactly like a crash, so anything that does not land on a real screen
        goes back to the primary one.
        """
        frame = self.frameGeometry()
        for screen in QGuiApplication.screens():
            # Require a usable overlap, not a single shared pixel.
            overlap = screen.availableGeometry().intersected(frame)
            if overlap.width() >= 120 and overlap.height() >= 80:
                return
        self._centre_on_primary()

    def _centre_on_primary(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available: QRect = screen.availableGeometry()
        size = self.frameGeometry().size().boundedTo(available.size())
        self.resize(size)
        self.move(
            available.center()
            - QPoint(self.frameGeometry().width() // 2, self.frameGeometry().height() // 2)
        )

    def _save_geometry(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())

    # --- closing ------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        """Closing hides to the tray. Quit is explicit, from the tray menu."""
        self._save_geometry()
        event.ignore()
        self.hide()
        self.hidden.emit()
