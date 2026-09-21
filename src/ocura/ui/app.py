from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ocura.application.autostart import Autostart, AutostartUnavailable, NoAutostart
from ocura.application.i18n import QT_TRANSLATE_NOOP, translate
from ocura.application.journal import NullJournal, SessionJournal
from ocura.application.onboarding import Onboarding, needs_introduction
from ocura.application.presenter import BreakPresenter, SessionView
from ocura.application.settings import (
    MemorySettings,
    Settings,
    SettingsRepository,
    migrate_from_shell,
)
from ocura.application.statistics import (
    NullStatistics,
    StatisticsPresenter,
    StatisticsSource,
)
from ocura.infrastructure.clock import SystemMonotonicClock, SystemWallClock
from ocura.infrastructure.storage import (
    Connection,
    EventStore,
    SettingsStore,
    StatisticsStore,
    StorageError,
    close_database,
    default_database_path,
    open_event_store,
)
from ocura.infrastructure.windows.autostart import build_autostart, startup_command
from ocura.infrastructure.windows.context import build_windows_context
from ocura.ui import motion
from ocura.ui.driver import TickDriver
from ocura.ui.language import Language
from ocura.ui.main_window import MainWindow
from ocura.ui.motion import Motion
from ocura.ui.onboarding import OnboardingDialog
from ocura.ui.overlay import OverlayManager
from ocura.ui.resources import app_icon
from ocura.ui.single_instance import SingleInstance
from ocura.ui.theme import DARK, DEFAULT_THEME, LIGHT, THEMES, stylesheet
from ocura.ui.toast import BreakToast
from ocura.ui.tray import Tray

logger = logging.getLogger(__name__)

ORGANISATION = "Ocura"
APPLICATION = "Ocura"


class _ShellKeys:
    """QSettings, narrowed to the three calls `migrate_from_shell` needs.

    The migration itself is in the application layer and knows nothing about
    Qt, which is what lets it be tested without one — a one-way door is exactly
    the thing worth being sure fires once and leaves nothing behind.
    """

    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    def value(self, key: str) -> object:
        return self._settings.value(key)

    def remove(self, key: str) -> None:
        self._settings.remove(key)

    def contains(self, key: str) -> bool:
        return self._settings.contains(key)


@dataclass(frozen=True, slots=True)
class History:
    """Everything that comes out of the one database file, or its stand-ins."""

    connection: Connection | None
    journal: SessionJournal
    statistics: StatisticsSource
    settings: SettingsRepository


def open_history(path: Path | None = None) -> History:
    """Open the history database, or carry on without one and say so.

    Ocura does not fail to start because a disk did. Everything the product
    actually does — time a focus block, read the context, cover the screen —
    works with no database at all, so an unopenable one costs the user their
    history and nothing else. The alternative, a start-up error dialog about
    SQLite on a machine where the timer would have run perfectly well, is worse
    than the problem it reports.
    """
    try:
        connection, store = open_event_store(path)
    except StorageError as exc:
        logger.warning("history is unavailable, continuing without it: %s", exc)
        # Every seam, not just the journal: a statistics page with nothing
        # behind it says there is nothing to show, which is true, rather than
        # failing to open, and settings that cannot be saved still apply to
        # the session the user is in.
        return History(None, NullJournal(), NullStatistics(), MemorySettings())

    logger.info("history at %s, run %d", path or default_database_path(), store.run)
    return History(connection, store, StatisticsStore(connection), SettingsStore(connection))


def _autostart() -> Autostart:
    """The real one, or a stand-in that says it cannot help.

    `winreg` exists only on Windows and `build_autostart` binds it on the way
    in. Ocura is a Windows application, but it is imported by tests and tools
    that are not, and a start-up preference is not worth an import error at
    launch.
    """
    try:
        return build_autostart()
    except (ImportError, OSError) as exc:
        logger.warning("startup entries are unavailable here: %s", exc)
        return NoAutostart()


def system_theme() -> str:
    """What Windows is set to, else dark.

    Only consulted for someone who has never chosen. Once there is a stored
    preference it wins, because a person who picked light did so knowing what
    their system was set to.
    """
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
        settings: QSettings | None = None,
        autostart: Autostart | None = None,
    ) -> None:
        self._app = app
        #: Shell state only, now that P5 has moved the preferences out: window
        #: geometry, and nothing a user would call a setting.
        self._settings = settings or QSettings(ORGANISATION, APPLICATION)

        monotonic = SystemMonotonicClock()
        self._history = open_history()
        self._database = self._history.connection
        self.journal = self._history.journal
        self.autostart = autostart or _autostart()
        self.preferences = self._load_preferences()
        # Before any widget is built. A widget reads its strings once at
        # construction and again on LanguageChange, and starting in English to
        # switch a moment later would be a visible flicker on every launch.
        self.language = Language(app)
        self.language.apply(self.preferences.language)
        self._schedule = schedule = self.preferences.schedule()

        self._context = build_windows_context(
            monotonic, idle_threshold=self.preferences.idle_threshold
        )
        presenter = BreakPresenter(
            schedule,
            monotonic,
            SystemWallClock(),
            self._context,
            journal=self.journal,
            settings=self.preferences,
        )

        motion.configure(Motion.from_system())

        icon = app_icon()
        self.driver = TickDriver(presenter, app)
        self.window = MainWindow(
            icon,
            self._settings,
            StatisticsPresenter(self._history.statistics, schedule),
            self.preferences,
            self.autostart,
        )
        self.tray = Tray(icon, app)
        self.toast = BreakToast()
        self.overlay = OverlayManager()

        app.setWindowIcon(icon)
        # Closing the last window must not end the process: the tray is the app.
        app.setQuitOnLastWindowClosed(False)

        self._theme_name = ""
        self._apply_theme(self.preferences.theme)

        self._connect()

    def _connect(self) -> None:
        self.driver.viewChanged.connect(self._render)

        self.window.dashboard.startRequested.connect(self.driver.start)
        self.window.dashboard.pauseToggled.connect(self.driver.toggle_paused)
        self.window.dashboard.breakRequested.connect(self.driver.take_break_now)
        self.window.themeToggled.connect(self.toggle_theme)
        self.window.settings.settingsChanged.connect(self.apply_preferences)

        self.tray.openRequested.connect(self.window.show_and_raise)
        self.tray.pauseToggled.connect(self.driver.toggle_paused)
        self.tray.breakRequested.connect(self.driver.take_break_now)
        self.tray.quitRequested.connect(self.quit)

        self.toast.snoozeRequested.connect(self._on_toast_snooze)

        self.overlay.skipRequested.connect(self.driver.skip_break)
        self.overlay.snoozeRequested.connect(self.driver.snooze)

    # --- preferences ---------------------------------------------------------

    def _load_preferences(self) -> Settings:
        """Read them, carry the theme out of the shell namespace, save if it moved."""
        try:
            preferences = self._history.settings.load()
        except StorageError as exc:
            logger.warning("settings could not be read, using the defaults: %s", exc)
            preferences = MemorySettings().load()

        preferences, moved = migrate_from_shell(preferences, _ShellKeys(self._settings))
        if moved:
            logger.info("moved the theme out of the shell namespace into settings")
        elif not preferences.introduced:
            # Nobody has ever chosen, so follow the system rather than imposing
            # a default that fights it.
            preferences = preferences.replace(theme=system_theme())

        if moved:
            self._save_preferences(preferences)
        return preferences

    def apply_preferences(self, preferences: Settings) -> None:
        """Save, then apply to everything already running. Order matters.

        Saving first means a change survives a crash in whatever it is about to
        reconfigure. Nothing below can refuse: a `Settings` that exists has
        already been validated, which is the point of validating at the
        boundary rather than here.
        """
        self._save_preferences(preferences)
        self.preferences = preferences

        self._schedule = preferences.schedule()
        self.driver.presenter.apply(preferences)
        self._context.set_idle_threshold(preferences.idle_threshold)
        self._apply_language(preferences.language)
        self._apply_theme(preferences.theme)
        # The change is visible at once rather than at the next tick, which for
        # a twenty-minute interval would be a second of a control looking dead.
        self.driver.refresh()

    def _apply_language(self, language: str) -> None:
        """Switch language live. Qt tells the widgets; the presenters recompute.

        No restart, and no pretending. Installing a translator makes Qt post
        LanguageChange to every widget, and each answers by re-setting the
        strings it owns; everything else on screen is rendered from a presenter
        on the next tick. The tray is the one thing Qt does not reach — it is a
        QObject, not a widget — so it is told directly.
        """
        if self.language.resolve_current(language) == self.language.current:
            return
        self.language.apply(language)
        self.tray.retranslate()
        self.window.statistics.refresh()

    def _save_preferences(self, preferences: Settings) -> None:
        try:
            self._history.settings.save(preferences)
        except StorageError as exc:
            # The same bargain as the event log: a disk that cannot be written
            # costs the user their stored choice and never their ability to
            # make one. It applies to this session either way.
            logger.warning("settings could not be saved: %s", exc)

    # --- theme ---------------------------------------------------------------

    @property
    def theme_name(self) -> str:
        return self._theme_name

    def toggle_theme(self) -> None:
        """The sidebar footer. A shortcut to the setting, not a second owner of it."""
        self.apply_preferences(
            self.preferences.replace(
                theme=LIGHT.name if self._theme_name == DARK.name else DARK.name
            )
        )

    def _apply_theme(self, name: str) -> None:
        if name == self._theme_name:
            return
        self._theme_name = name
        self._app.setStyleSheet(stylesheet(THEMES[name]))
        self.window.set_theme_name(name)

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
            self.toast.render(view.warning_text, can_snooze=view.can_snooze)
            if not self.toast.isVisible():
                self.toast.show_near_tray()
        elif self.toast.isVisible():
            self.toast.hide()

    def _on_toast_snooze(self) -> None:
        self.toast.hide()
        self.driver.snooze()

    def start(self, first_run: bool = False) -> None:
        """Introduce Ocura if it has not been, then run.

        The introduction comes first and blocks, so the window behind it opens
        already configured rather than rearranging itself under the user the
        moment they finish reading. Nothing is timed while it is up: a focus
        block that started before they had been told what a focus block is
        would be the product interrupting the explanation of why it interrupts.
        """
        if needs_introduction(self.preferences, first_run):
            self.introduce()

        # Before the window: the tray is how Ocura is reached once the window is
        # hidden, so it must exist even if the window never appears.
        self.tray.show()
        self.window.show_and_raise()
        self.driver.start()

    def introduce(self) -> None:
        """Run the three first-run screens and apply what they produced."""
        dialog = OnboardingDialog(Onboarding(self.preferences))
        dialog.completed.connect(self._on_introduced)
        dialog.exec()

    def _on_introduced(self, preferences: Settings) -> None:
        # The startup entry is written here rather than inside the flow: the
        # flow records an answer, and the only place that touches the registry
        # is the one that can report a refusal to the user later, in Settings.
        if preferences.autostart:
            try:
                self.autostart.set_enabled(True)
            except AutostartUnavailable as exc:
                logger.warning("could not add the startup entry: %s", exc)
                preferences = preferences.replace(autostart=False)

        self.apply_preferences(preferences)
        self.window.settings.load(preferences)

    def quit(self) -> None:
        # Stop first: stopping emits a STOPPED event, and that event is part of
        # the history this then closes the file on.
        self.driver.stop()
        self.overlay.close()
        self.toast.hide()
        self.tray.hide()
        close_database(self._database)
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
        lines.extend(_catalogue_report(app))

        # A packaged build on someone else's machine is exactly where a
        # permissions problem under %LOCALAPPDATA% shows up, and the log it
        # would appear in is the one a windowed build does not have.
        lines.append(f"history path: {default_database_path()}")
        history = open_history()
        if isinstance(history.journal, EventStore):
            lines.append(
                f"history: ok, run {history.journal.run}, {history.journal.count()} events"
            )
        else:
            lines.append("history: UNAVAILABLE (see the warning above)")
        lines.append(f"settings: {history.settings.load()}")
        lines.append(f"autostart command: {startup_command()}")
        close_database(history.connection)
    finally:
        app.quit()

    print("\n".join(lines))
    return 0


#: A string every catalogue has, used only to ask whether one is really
#: loaded. Marked rather than typed twice: if the tray's wording changes, this
#: follows it, and a probe that silently stopped matching the catalogue would
#: report every language as MISSING.
TRAY_PROBE = QT_TRANSLATE_NOOP("Tray", "Ocura — not running")


def _catalogue_report(app: QApplication) -> list[str]:
    """One line per language, for the part of a build that fails silently.

    A missing or unreadable .qm costs nothing at startup: Ocura runs in
    English and says nothing about it, on a machine whose owner asked for
    Arabic. So the check is not "is the file in the bundle" but "does a string
    come back translated" — which is also the only thing that catches a
    catalogue whose buffer was garbage-collected out from under QTranslator.
    """
    from ocura.application.settings import LANGUAGE_NAMES
    from ocura.ui.language import SOURCE_LANGUAGE, Language

    probe = translate("Tray", TRAY_PROBE)
    handle = Language(app)
    lines = []
    for language in LANGUAGE_NAMES:
        if language == SOURCE_LANGUAGE:
            continue
        handle.apply(language)
        translated = translate("Tray", TRAY_PROBE)
        # ascii(), not repr(): this report is redirected to a file from a
        # console that is very often cp1252, and a self-check that dies
        # printing Arabic is a self-check that reports nothing at all.
        lines.append(
            f"catalogue {language}: {'ok' if translated != probe else 'MISSING'} {translated!a}"
        )
    handle.apply(SOURCE_LANGUAGE)
    return lines


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    arguments = argv if argv is not None else sys.argv
    if "--self-check" in arguments:
        return self_check()

    # A flag rather than a button. Re-running the introduction is something
    # developers and testers need and users do not, and a "show me the welcome
    # again" control in Settings would be clutter that earns its place once per
    # install.
    first_run = "--first-run" in arguments

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
    ocura.start(first_run=first_run)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
