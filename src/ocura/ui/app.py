from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from ocura.application.presenter import BreakPresenter, SessionView
from ocura.domain.schedule import DEFAULT_SCHEDULE, BreakSchedule
from ocura.infrastructure.clock import SystemMonotonicClock, SystemWallClock
from ocura.infrastructure.windows.context import build_windows_context
from ocura.ui.driver import TickDriver
from ocura.ui.main_window import MainWindow
from ocura.ui.single_instance import SingleInstance
from ocura.ui.theme import DEFAULT_THEME, THEMES, stylesheet
from ocura.ui.tray import Tray

ICON_PATH = Path(__file__).resolve().parents[3] / "assets" / "icons" / "ocura.ico"
ORGANISATION = "Ocura"
APPLICATION = "Ocura"


class OcuraApp:
    """Wires the shell together. Owns no break logic of any kind."""

    def __init__(
        self,
        app: QApplication,
        schedule: BreakSchedule = DEFAULT_SCHEDULE,
        theme_name: str = DEFAULT_THEME,
    ) -> None:
        self._app = app
        monotonic = SystemMonotonicClock()
        presenter = BreakPresenter(
            schedule, monotonic, SystemWallClock(), build_windows_context(monotonic)
        )

        icon = QIcon(str(ICON_PATH))
        settings = QSettings(ORGANISATION, APPLICATION)

        self.driver = TickDriver(presenter, app)
        self.window = MainWindow(icon, settings)
        self.tray = Tray(icon, app)

        app.setWindowIcon(icon)
        app.setStyleSheet(stylesheet(THEMES[theme_name]))
        # Closing the last window must not end the process: the tray is the app.
        app.setQuitOnLastWindowClosed(False)

        self._connect()

    def _connect(self) -> None:
        self.driver.viewChanged.connect(self._render)

        self.window.dashboard.startRequested.connect(self.driver.start)
        self.window.dashboard.pauseToggled.connect(self.driver.toggle_paused)
        self.window.dashboard.breakRequested.connect(self.driver.take_break_now)

        self.tray.openRequested.connect(self.window.show_and_raise)
        self.tray.pauseToggled.connect(self.driver.toggle_paused)
        self.tray.breakRequested.connect(self.driver.take_break_now)
        self.tray.quitRequested.connect(self.quit)

    def _render(self, view: SessionView) -> None:
        self.window.render(view)
        self.tray.render(view, self.driver.presenter.tooltip())

    def start(self) -> None:
        self.tray.show()
        self.window.show_and_raise()
        self.driver.start()

    def quit(self) -> None:
        self.driver.stop()
        self.tray.hide()
        self._app.quit()


def main(argv: list[str] | None = None) -> int:
    # Per-monitor DPI: PassThrough keeps fractional scales such as 150% exact
    # instead of rounding them to whole factors and blurring everything.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setOrganizationName(ORGANISATION)
    QApplication.setApplicationName(APPLICATION)

    app = QApplication(argv if argv is not None else sys.argv)

    guard = SingleInstance(parent=app)
    if not guard.claim():
        # The running instance has been told to show itself; nothing left to do.
        return 0

    ocura = OcuraApp(app)
    guard.raiseRequested.connect(ocura.window.show_and_raise)
    ocura.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
