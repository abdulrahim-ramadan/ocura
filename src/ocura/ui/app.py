from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ocura.application.presenter import BreakPresenter, SessionView
from ocura.domain.schedule import DEFAULT_SCHEDULE, BreakSchedule
from ocura.infrastructure.clock import SystemMonotonicClock, SystemWallClock
from ocura.infrastructure.windows.context import build_windows_context
from ocura.ui import motion
from ocura.ui.driver import TickDriver
from ocura.ui.main_window import MainWindow
from ocura.ui.motion import Motion
from ocura.ui.overlay import OverlayManager
from ocura.ui.resources import app_icon
from ocura.ui.single_instance import SingleInstance
from ocura.ui.theme import DARK, DEFAULT_THEME, LIGHT, THEMES, stylesheet
from ocura.ui.toast import BreakToast
from ocura.ui.tray import Tray

logger = logging.getLogger(__name__)

ORGANISATION = "Ocura"
APPLICATION = "Ocura"

#: Shell state, kept apart from anything a user would call a setting. P5 moves
#: the theme into the real settings model; window geometry stays here.
THEME_KEY = "shell/theme"


def initial_theme(settings: QSettings) -> str:
    """Remembered choice, else the system's, else dark."""
    stored = settings.value(THEME_KEY)
    if isinstance(stored, str) and stored in THEMES:
        return stored

    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        match scheme():
            case Qt.ColorScheme.Light:
                return LIGHT.name
            case Qt.ColorScheme.Dark:
                return DARK.name
            case _:
                pass
    return DEFAULT_THEME


class OcuraApp:
    """Wires the shell together. Owns no break logic of any kind."""

    def __init__(
        self,
        app: QApplication,
        schedule: BreakSchedule = DEFAULT_SCHEDULE,
        settings: QSettings | None = None,
    ) -> None:
        self._app = app
        self._schedule = schedule
        self._settings = settings or QSettings(ORGANISATION, APPLICATION)

        monotonic = SystemMonotonicClock()
        presenter = BreakPresenter(
            schedule, monotonic, SystemWallClock(), build_windows_context(monotonic)
        )

        motion.configure(Motion.from_system())

        icon = app_icon()
        self.driver = TickDriver(presenter, app)
        self.window = MainWindow(icon, self._settings)
        self.tray = Tray(icon, app)
        self.toast = BreakToast()
        self.overlay = OverlayManager()

        app.setWindowIcon(icon)
        # Closing the last window must not end the process: the tray is the app.
        app.setQuitOnLastWindowClosed(False)

        self._theme_name = initial_theme(self._settings)
        self._apply_theme(self._theme_name)

        self._connect()

    def _connect(self) -> None:
        self.driver.viewChanged.connect(self._render)

        self.window.dashboard.startRequested.connect(self.driver.start)
        self.window.dashboard.pauseToggled.connect(self.driver.toggle_paused)
        self.window.dashboard.breakRequested.connect(self.driver.take_break_now)
        self.window.themeToggled.connect(self.toggle_theme)

        self.tray.openRequested.connect(self.window.show_and_raise)
        self.tray.pauseToggled.connect(self.driver.toggle_paused)
        self.tray.breakRequested.connect(self.driver.take_break_now)
        self.tray.quitRequested.connect(self.quit)

        self.toast.snoozeRequested.connect(self._on_toast_snooze)

        self.overlay.skipRequested.connect(self.driver.skip_break)
        self.overlay.snoozeRequested.connect(self.driver.snooze)

    # --- theme --------------------------------------------------------------

    @property
    def theme_name(self) -> str:
        return self._theme_name

    def toggle_theme(self) -> None:
        self._apply_theme(LIGHT.name if self._theme_name == DARK.name else DARK.name)

    def _apply_theme(self, name: str) -> None:
        self._theme_name = name
        self._app.setStyleSheet(stylesheet(THEMES[name]))
        self.window.set_theme_name(name)
        self._settings.setValue(THEME_KEY, name)

    # --- lifecycle ----------------------------------------------------------

    def _render(self, view: SessionView) -> None:
        self.window.render(view)
        self.tray.render(view, self.driver.presenter.tooltip())
        self._render_toast(view)
        self._render_overlay(view)

    def _render_overlay(self, view: SessionView) -> None:
        if view.overlay_visible and not self.overlay.is_open:
            self.overlay.open()
            self.overlay.begin(self._schedule.break_duration)
        elif not view.overlay_visible and self.overlay.is_open:
            self.overlay.close()
        if self.overlay.is_open:
            self.overlay.render(view)

    def _render_toast(self, view: SessionView) -> None:
        if view.warning_visible:
            self.toast.render(f"A break in {view.countdown_text}", can_snooze=view.can_snooze)
            if not self.toast.isVisible():
                self.toast.show_near_tray()
        elif self.toast.isVisible():
            self.toast.hide()

    def _on_toast_snooze(self) -> None:
        self.toast.hide()
        self.driver.snooze()

    def start(self) -> None:
        # Before the window: the tray is how Ocura is reached once the window is
        # hidden, so it must exist even if the window never appears.
        self.tray.show()
        self.window.show_and_raise()
        self.driver.start()

    def quit(self) -> None:
        self.driver.stop()
        self.overlay.close()
        self.toast.hide()
        self.tray.hide()
        self._app.quit()


def self_check() -> int:
    """Report whether a build can find everything it needs, then exit.

    For a packaged build handed to someone else: `Ocura.exe --self-check > out.txt`
    answers "is this a bundling problem or a code problem" without a console.
    """
    import sys as _sys

    from ocura.ui.resources import APP_ICON, ASSETS
    from ocura.ui.theme import DARK, QSS_NAME, QSS_PACKAGE, stylesheet

    frozen = getattr(_sys, "frozen", False)
    lines = [
        f"frozen: {frozen}",
        f"bundle: {getattr(_sys, '_MEIPASS', '(not frozen)')}",
        f"executable: {_sys.executable}",
        f"prefix: {_sys.prefix}",
    ]
    lines += [f"sys.path[{index}]: {entry}" for index, entry in enumerate(_sys.path)]
    # A packaged build must be self-contained: nothing on the import path may
    # point back at a source checkout that the recipient will not have.
    ocura_module = _sys.modules[__name__].__file__ or "(unknown)"
    lines.append(f"this module loaded from: {ocura_module}")

    app = QApplication([])
    try:
        icon = app_icon()
        lines.append(f"icon {ASSETS}/{APP_ICON}: {'ok' if not icon.isNull() else 'MISSING'}")
        lines.append(f"icon sizes: {[s.width() for s in icon.availableSizes()]}")
        qss = stylesheet(DARK)
        lines.append(f"stylesheet {QSS_PACKAGE}/{QSS_NAME}: {len(qss)} chars")
        lines.append(f"stylesheet resolved: {'ok' if DARK.accent in qss else 'BROKEN'}")
    finally:
        app.quit()

    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    arguments = argv if argv is not None else sys.argv
    if "--self-check" in arguments:
        return self_check()

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
        logger.info("another instance is running; asked it to show itself")
        return 0

    ocura = OcuraApp(app)
    guard.raiseRequested.connect(ocura.window.show_and_raise)
    ocura.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
