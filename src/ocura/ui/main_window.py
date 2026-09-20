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
from ocura.application.statistics import StatisticsPresenter
from ocura.ui.motion import MOTION
from ocura.ui.statistics import StatisticsPage
from ocura.ui.theme import LAYOUT, SPACING
from ocura.ui.views import DashboardView, PlaceholderView

DEFAULT_SIZE = QSize(880, 660)

#: The dashboard scrolls, so this is a comfort floor rather than a correctness
#: one. Squeezed-text overlap is prevented structurally in DashboardView, not by
#: forbidding small windows.
MIN_SIZE = QSize(680, 520)


class MainWindow(QMainWindow):
    """Shell: navigation, geometry, and hide-to-tray. Renders nothing itself."""

    hidden = Signal()
    themeToggled = Signal()

    #: The index of the Statistics page in both the sidebar and the stack. One
    #: constant rather than a literal in each: they have to agree, and a pair
    #: of bare 1s is exactly the kind of agreement that quietly stops holding.
    STATISTICS = 1

    def __init__(
        self,
        icon: QIcon,
        settings: QSettings,
        statistics: StatisticsPresenter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings

        self.setWindowTitle("Ocura")
        self.setWindowIcon(icon)
        self.setMinimumSize(MIN_SIZE)

        self.dashboard = DashboardView()
        self._pages = QStackedWidget()
        self._pages.addWidget(self.dashboard)
        self.statistics = StatisticsPage(statistics)
        self._pages.addWidget(self.statistics)
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
        self._nav.idClicked.connect(self._show_page)

        layout.addStretch(1)

        # Sidebar footer, not Settings: Settings is P5 and stays empty until it
        # has a real settings model to write into.
        self._theme_button = QPushButton()
        self._theme_button.setObjectName("NavButton")
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.clicked.connect(self.themeToggled)
        layout.addWidget(self._theme_button)
        return bar

    def set_theme_name(self, name: str) -> None:
        self._theme_button.setText("Light theme" if name == "dark" else "Dark theme")

    def _show_page(self, index: int) -> None:
        if index == self._pages.currentIndex():
            return
        self._pages.setCurrentIndex(index)
        # Read on arrival rather than on a timer. The window is hidden most of
        # the time and the page is a query over a file somebody may have been
        # writing to all day; refreshing it when it is not on screen is work
        # nobody asked for, and refreshing it while it is read is a page that
        # rearranges itself under the reader.
        if index == self.STATISTICS:
            self.statistics.refresh()
        MOTION.fade_in(self._pages.currentWidget())

    def render(self, view: SessionView) -> None:
        self.dashboard.render(view)

    def show_and_raise(self) -> None:
        # Coming back to a window left on Statistics must not show yesterday's
        # numbers: the process outlives the day it started in.
        if self._pages.currentIndex() == self.STATISTICS:
            self.statistics.refresh()
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
