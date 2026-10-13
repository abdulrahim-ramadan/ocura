from __future__ import annotations

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCloseEvent, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ocura.application.autostart import Autostart
from ocura.application.i18n import QT_TRANSLATE_NOOP, translate
from ocura.application.presenter import SessionView
from ocura.application.settings import Settings
from ocura.application.statistics import StatisticsPresenter
from ocura.ui.motion import MOTION
from ocura.ui.settings_page import SettingsPage
from ocura.ui.statistics import StatisticsPage
from ocura.ui.theme import LAYOUT, SPACING
from ocura.ui.views import DashboardView

#: The sidebar sections, in order. Marked rather than translated here: a
#: constant translated at import is stuck in the language Python started in.
#: Marked *and* rendered with an explicit context rather than `self.tr`,
#: because `tr(variable)` extracts nothing — lupdate reads the source, it does
#: not run it, so a table of strings has to be marked where the table is
#: written and translated where the table is read.
NAV_SECTIONS = (
    QT_TRANSLATE_NOOP("MainWindow", "Dashboard"),
    QT_TRANSLATE_NOOP("MainWindow", "Statistics"),
    QT_TRANSLATE_NOOP("MainWindow", "Settings"),
)

DEFAULT_SIZE = QSize(880, 660)

#: The dashboard scrolls, so this is a comfort floor rather than a correctness
#: one. Squeezed-text overlap is prevented structurally in DashboardView, not by
#: forbidding small windows.
#:
#: The width is a floor in a second sense as well: it was measured in English,
#: and translated pages are wider, so `_fit_minimum_width` raises it to what
#: the widest page needs in the language on screen. Nothing lowers it.
MIN_SIZE = QSize(680, 520)


def page_minimum_width(page: QWidget) -> int:
    """The narrowest this page can be with nothing cut off and no sideways scroll.

    Every page is the same shape — a capped column in a scroll area, inside
    the page's own margins — so one measurement serves all of them. The
    vertical scrollbar is counted whether or not it is showing: a page that
    fits until its content grows tall enough to need one would then slide
    sideways by exactly its width.
    """
    scroller = page.findChild(QScrollArea, "Page")
    margins = page.layout().contentsMargins()
    return (
        margins.left()
        + margins.right()
        + 2 * scroller.frameWidth()
        + scroller.widget().minimumSizeHint().width()
        + scroller.verticalScrollBar().sizeHint().width()
    )


class MainWindow(QMainWindow):
    """Shell: navigation, geometry, and hide-to-tray. Renders nothing itself."""

    hidden = Signal()
    themeToggled = Signal()

    #: The index of the Statistics page in both the sidebar and the stack. One
    #: constant rather than a literal in each: they have to agree, and a pair
    #: of bare 1s is exactly the kind of agreement that quietly stops holding.
    STATISTICS = 1
    SETTINGS = 2

    def __init__(
        self,
        icon: QIcon,
        settings: QSettings,
        statistics: StatisticsPresenter | None = None,
        preferences: Settings | None = None,
        autostart: Autostart | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings

        self._theme_is_dark = True
        self.setWindowIcon(icon)
        self.setMinimumSize(MIN_SIZE)

        self.dashboard = DashboardView()
        self._pages = QStackedWidget()
        self._pages.addWidget(self.dashboard)
        self.statistics = StatisticsPage(statistics)
        self._pages.addWidget(self.statistics)
        self.settings = SettingsPage(preferences, autostart)
        self._pages.addWidget(self.settings)

        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._sidebar())
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(root)

        self.retranslate()
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
        self._tagline = _label("", "Tagline")
        layout.addWidget(self._tagline)

        self._nav = QButtonGroup(self)
        self._nav.setExclusive(True)
        for index, _name in enumerate(NAV_SECTIONS):
            button = QPushButton()
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

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("Ocura"))
        self._tagline.setText(self.tr("Better screen habits."))
        for index, name in enumerate(NAV_SECTIONS):
            button = self._nav.button(index)
            if button is not None:
                button.setText(translate("MainWindow", name))
        self._theme_button.setText(
            self.tr("Light theme") if self._theme_is_dark else self.tr("Dark theme")
        )
        self._refit_later()

    def _fit_minimum_width(self) -> None:
        """Make the window impossible to shrink past the widest page.

        Every page, not the one on screen: a minimum that suited the dashboard
        let Statistics slide sideways the moment it was opened, and in German
        Statistics is the widest page by seventy pixels. The page scrolls
        sideways if it has to — that safety net stays — but
        `tests/gui/test_minimum_width.py` holds it to never being needed.

        Polished first, because a button's width is not knowable until the
        stylesheet that pads it has been applied: unpolished, the German
        dashboard row measures 27px narrower than it draws.
        """
        self.ensurePolished()
        self.dashboard.reserve_label_widths()
        widest = max(page_minimum_width(self._pages.widget(i)) for i in range(self._pages.count()))
        self.setMinimumWidth(max(MIN_SIZE.width(), LAYOUT.sidebar_width + widest))

    def _refit_later(self) -> None:
        """Measure once the events already queued have been handled.

        A language change reaches every widget as its own posted event, and
        this window's arrives before its pages' do; measured on the spot, the
        minimum is the previous language's, which is what it used to be — one
        language behind on every switch. A style change is the same story with
        each button's cached size. Queued behind them, the measurement sees
        the text and the padding that will actually be drawn.
        """
        QTimer.singleShot(0, self._fit_minimum_width)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refit_later()

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        elif event.type() == QEvent.Type.StyleChange:
            self._refit_later()
        super().changeEvent(event)

    def set_theme_name(self, name: str) -> None:
        self._theme_is_dark = name == "dark"
        self._theme_button.setText(
            self.tr("Light theme") if self._theme_is_dark else self.tr("Dark theme")
        )
        # The footer button is a shortcut to the real setting, which is what
        # docs/architecture.md said it would become once there was one. The
        # page stays the single place that decides what a theme change means.
        self.settings.set_theme(name)

    def show_settings(self) -> None:
        self._nav.button(self.SETTINGS).setChecked(True)
        self._show_page(self.SETTINGS)

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
            # A week's totals are text, and a longer week is wider text.
            self._refit_later()
        MOTION.fade_in(self._pages.currentWidget())

    def render(self, view: SessionView) -> None:
        self.dashboard.render(view)

    def show_and_raise(self) -> None:
        # Coming back to a window left on Statistics must not show yesterday's
        # numbers: the process outlives the day it started in.
        if self._pages.currentIndex() == self.STATISTICS:
            self.statistics.refresh()
            self._refit_later()
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
