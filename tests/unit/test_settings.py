"""The settings model: what it accepts, what it refuses, and what it says why.

Every refusal here is checked for its message as well as its type. The whole
point of `InvalidSettings` over a bare `ConfigurationError` is that somebody
reads the sentence, so a test that only asserts `pytest.raises` would be
checking the half that does not matter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ocura.application.presenter import TICK_SECONDS, BreakPresenter
from ocura.application.settings import (
    DEFAULTS,
    LEGACY_THEME_KEY,
    MAX_FOCUS_SECONDS,
    MIN_FOCUS_SECONDS,
    THEME_NAMES,
    InvalidSettings,
    MemorySettings,
    Settings,
    SettingsRepository,
    migrate_from_shell,
)
from ocura.domain.errors import ConfigurationError
from ocura.domain.timer import TimerState
from ocura.infrastructure.storage import (
    SettingsStore,
    StorageError,
    close_database,
    open_database,
)

from .conftest import FakeMonotonicClock, FakeWallClock, ScriptedContext


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "history" / "ocura.db"


@pytest.fixture
def store(database_path: Path):
    connection = open_database(database_path)
    try:
        yield SettingsStore(connection)
    finally:
        close_database(connection)


class FakeShell:
    """The `shell/` QSettings namespace, without a Qt application."""

    def __init__(self, **values: object) -> None:
        self.values = dict(values)
        self.removed: list[str] = []

    def value(self, key: str) -> object:
        return self.values.get(key)

    def remove(self, key: str) -> None:
        self.removed.append(key)
        self.values.pop(key, None)

    def contains(self, key: str) -> bool:
        return key in self.values


# --- what is accepted ------------------------------------------------------


def test_the_defaults_are_honourable():
    """They are what a first-run user gets, so they had better validate."""
    assert DEFAULTS.validate() == DEFAULTS
    assert DEFAULTS.schedule().focus_interval == 20 * 60


def test_validate_returns_what_it_was_given_and_repairs_nothing():
    """The whole rule in one assertion: no rounding, no clamping, no fixing."""
    settings = Settings(focus_interval=1337.0, break_duration=17.0)

    assert settings.validate() is settings


def test_a_settings_is_immutable_and_replace_makes_a_new_one():
    changed = DEFAULTS.replace(theme="light")

    assert changed.theme == "light"
    assert DEFAULTS.theme == "dark", "the original was mutated"


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_every_theme_name_is_accepted(theme: str):
    assert DEFAULTS.replace(theme=theme).validate().theme == theme


def test_the_theme_names_match_the_themes_that_exist():
    """The application layer cannot import the UI's theme table, so it keeps
    its own list. This is the test that stops the two drifting apart."""
    from ocura.ui.theme import THEMES

    assert set(THEME_NAMES) == set(THEMES)


# --- what is refused, and what it says -------------------------------------


def test_a_break_longer_than_the_interval_is_refused_in_the_users_own_terms():
    with pytest.raises(InvalidSettings) as raised:
        Settings(focus_interval=20 * 60.0, break_duration=25 * 60.0).validate()

    message = str(raised.value)
    assert raised.value.field == "break_duration"
    assert "25 minutes" in message
    assert "20 minutes" in message
    # Not the domain's wording: no internal field names, no raw seconds.
    assert "break_duration" not in message
    assert "1500" not in message


def test_a_warning_longer_than_the_interval_is_refused():
    with pytest.raises(InvalidSettings) as raised:
        Settings(focus_interval=600.0, pre_break_warning=700.0).validate()

    assert raised.value.field == "pre_break_warning"
    assert "lead time" in str(raised.value)


def test_a_refusal_is_a_configuration_error_the_domain_already_had():
    """One thing to catch, not a parallel hierarchy for the same fact."""
    with pytest.raises(ConfigurationError):
        Settings(break_duration=99999.0).validate()


@pytest.mark.parametrize(
    "field", ["focus_interval", "break_duration", "pre_break_warning", "idle_threshold"]
)
@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_nothing_may_be_zero_negative_or_not_a_number(field: str, value: float):
    with pytest.raises(InvalidSettings) as raised:
        DEFAULTS.replace(**{field: value}).validate()

    assert raised.value.field == field


def test_a_boolean_is_not_a_duration():
    """True is an int in Python and would otherwise pass as one second."""
    with pytest.raises(InvalidSettings):
        DEFAULTS.replace(focus_interval=True).validate()


def test_an_absurdly_short_interval_is_refused_with_the_limit_named():
    with pytest.raises(InvalidSettings) as raised:
        DEFAULTS.replace(focus_interval=MIN_FOCUS_SECONDS - 1).validate()

    assert "1 minute" in str(raised.value)


def test_an_absurdly_long_interval_suggests_pausing_instead():
    with pytest.raises(InvalidSettings) as raised:
        DEFAULTS.replace(focus_interval=MAX_FOCUS_SECONDS + 60).validate()

    assert "pause" in str(raised.value).lower()


def test_an_unknown_theme_is_refused_and_the_real_ones_are_listed():
    with pytest.raises(InvalidSettings) as raised:
        DEFAULTS.replace(theme="chartreuse").validate()

    assert raised.value.field == "theme"
    for name in THEME_NAMES:
        assert name in str(raised.value)


def test_a_message_does_not_show_its_arithmetic():
    """ "11.6667 minutes" is a calculation showing its working, not a sentence.

    A duration that is not a whole number of minutes is said in seconds rather
    than rounded into them.
    """
    with pytest.raises(InvalidSettings) as raised:
        Settings(focus_interval=600.0, pre_break_warning=700.0).validate()

    message = str(raised.value)
    assert "700 seconds" in message
    assert "11.6" not in message


def test_a_message_never_rounds_two_values_into_the_same_words():
    """610 seconds and 600 rounded to minutes both read "10 minutes", and the
    refusal becomes "a warning 10 minutes ahead would start before the interval
    of 10 minutes" — a contradiction that explains nothing."""
    with pytest.raises(InvalidSettings) as raised:
        Settings(focus_interval=600.0, pre_break_warning=610.0).validate()

    message = str(raised.value)
    assert "610 seconds" in message
    assert message.count("10 minutes") == 1


# --- the derived schedule fields -------------------------------------------


def test_a_short_rhythm_is_accepted_rather_than_refused_over_hidden_fields():
    """A five-minute rhythm must not fail on defer_interval, which is not a
    setting, has no control, and would name itself in the error if it did."""
    settings = Settings(focus_interval=300.0, break_duration=20.0, pre_break_warning=30.0)

    schedule = settings.validate().schedule()
    assert schedule.defer_interval < schedule.focus_interval
    assert schedule.snooze_interval < schedule.focus_interval


def test_a_normal_rhythm_keeps_the_schedule_defaults():
    """Deriving is a floor for short intervals, not a redefinition."""
    from ocura.domain.schedule import DEFAULT_SCHEDULE

    schedule = DEFAULTS.schedule()
    assert schedule.defer_interval == DEFAULT_SCHEDULE.defer_interval
    assert schedule.snooze_interval == DEFAULT_SCHEDULE.snooze_interval


# --- persistence -----------------------------------------------------------


def test_an_empty_database_reads_as_the_defaults(store: SettingsStore):
    assert store.load() == DEFAULTS


def test_settings_round_trip(store: SettingsStore):
    settings = DEFAULTS.replace(
        focus_interval=2700.0,
        break_duration=30.0,
        pre_break_warning=90.0,
        idle_threshold=240.0,
        autostart=True,
        theme="light",
        tips=False,
        introduced=True,
    )
    store.save(settings)

    assert store.load() == settings


def test_booleans_survive_as_booleans(store: SettingsStore):
    """bool is an int in Python; written naively, False comes back as 0.0."""
    store.save(DEFAULTS.replace(tips=False, autostart=True, introduced=True))
    loaded = store.load()

    assert loaded.tips is False
    assert loaded.autostart is True
    assert loaded.introduced is True


def test_saving_twice_replaces_rather_than_accumulates(store: SettingsStore, database_path: Path):
    store.save(DEFAULTS.replace(theme="light"))
    store.save(DEFAULTS.replace(theme="dark"))

    assert store.load().theme == "dark"


def test_a_value_that_is_not_a_number_falls_back_to_its_default(store, caplog):
    """A half-written row is not a value the user typed, so the no-clamping
    rule does not apply to it — and refusing to start would leave them with no
    way back into the application that owns the file."""
    store._connection.execute(
        "INSERT OR REPLACE INTO settings (name, value) VALUES ('focus_interval', 'soon')"
    )

    assert store.load().focus_interval == DEFAULTS.focus_interval
    assert any("not a number" in record.message for record in caplog.records)


def test_a_stored_combination_that_cannot_be_honoured_falls_back_whole(store, caplog):
    store._connection.execute(
        "INSERT OR REPLACE INTO settings (name, value) VALUES ('break_duration', '99999')"
    )

    assert store.load() == DEFAULTS
    assert any("not usable" in record.message for record in caplog.records)


def test_a_setting_written_by_a_newer_ocura_is_ignored_and_not_dropped(store):
    """Saving must not quietly delete the other build's preferences."""
    store._connection.execute(
        "INSERT OR REPLACE INTO settings (name, value) VALUES ('posture_alerts', '1')"
    )

    assert store.load() == DEFAULTS
    store.save(DEFAULTS.replace(theme="light"))

    rows = dict(store._connection.execute("SELECT name, value FROM settings").fetchall())
    assert rows["posture_alerts"] == "1"


def test_a_closed_database_reports_a_storage_error(database_path: Path):
    connection = open_database(database_path)
    store = SettingsStore(connection)
    close_database(connection)

    with pytest.raises(StorageError):
        store.load()


def test_the_memory_stand_in_is_a_repository_and_keeps_what_it_is_given():
    stand_in = MemorySettings()

    assert isinstance(stand_in, SettingsRepository)
    stand_in.save(DEFAULTS.replace(theme="light"))
    assert stand_in.load().theme == "light"


def test_the_real_store_satisfies_the_protocol(store: SettingsStore):
    assert isinstance(store, SettingsRepository)


# --- the move out of the shell namespace -----------------------------------


def test_the_theme_moves_out_of_the_shell_namespace_once():
    shell = FakeShell(**{LEGACY_THEME_KEY: "light"})

    settings, moved = migrate_from_shell(DEFAULTS, shell)

    assert moved is True
    assert settings.theme == "light"
    assert LEGACY_THEME_KEY in shell.removed, "the old key was left to be read again"
    assert not shell.contains(LEGACY_THEME_KEY)


def test_a_second_launch_finds_nothing_left_to_move():
    shell = FakeShell(**{LEGACY_THEME_KEY: "light"})
    settings, _ = migrate_from_shell(DEFAULTS, shell)

    again, moved = migrate_from_shell(settings.replace(introduced=True), shell)

    assert moved is False
    assert again.theme == "light", "the migrated choice was lost on the second pass"


def test_a_stale_shell_key_never_overrides_a_choice_made_since():
    """Someone who has used P5 and picked dark must not be given light back by
    a registry value left over from P4."""
    chosen = DEFAULTS.replace(theme="dark", introduced=True)
    shell = FakeShell(**{LEGACY_THEME_KEY: "light"})

    settings, moved = migrate_from_shell(chosen, shell)

    assert moved is False
    assert settings.theme == "dark"
    assert LEGACY_THEME_KEY in shell.removed


def test_an_unreadable_legacy_value_is_dropped_rather_than_adopted():
    shell = FakeShell(**{LEGACY_THEME_KEY: "chartreuse"})

    settings, moved = migrate_from_shell(DEFAULTS, shell)

    assert moved is False
    assert settings.theme == DEFAULTS.theme
    assert LEGACY_THEME_KEY in shell.removed


def test_nothing_to_migrate_is_not_a_migration():
    shell = FakeShell()

    settings, moved = migrate_from_shell(DEFAULTS, shell)

    assert moved is False
    assert settings == DEFAULTS
    assert shell.removed == []


def test_only_the_theme_ever_lived_in_the_shell_namespace():
    """Geometry stays there; it is shell state, not a preference."""
    shell = FakeShell(**{LEGACY_THEME_KEY: "light", "window/geometry": b"..."})

    migrate_from_shell(DEFAULTS, shell)

    assert shell.contains("window/geometry"), "window geometry was taken too"


# --- applying to a session that is already running -------------------------
#
# The decision under test is BreakTimer.reschedule's: the elapsed focus time is
# kept and measured against the new interval. Restarting the block would erase
# work the user really did at the screen; waiting a fresh interval from now
# would count the same stretch twice.


def a_presenter(settings: Settings, clock: FakeMonotonicClock) -> BreakPresenter:
    return BreakPresenter(
        settings.schedule(),
        clock,
        FakeWallClock(),
        ScriptedContext(),
        settings=settings,
    )


def run_for(presenter: BreakPresenter, clock: FakeMonotonicClock, seconds: float):
    view = presenter.view()
    for _ in range(int(seconds / TICK_SECONDS)):
        clock.advance(TICK_SECONDS)
        view = presenter.tick()
    return view


@pytest.fixture
def running():
    """A presenter twelve minutes into a twenty-minute block."""
    settings = DEFAULTS.replace(focus_interval=20 * 60.0, pre_break_warning=60.0)
    clock = FakeMonotonicClock()
    presenter = a_presenter(settings, clock)
    presenter.start()
    run_for(presenter, clock, 12 * 60.0)
    return presenter, clock, settings


def test_changing_the_interval_keeps_the_elapsed_time(running):
    presenter, _, settings = running
    assert presenter.view().focus_elapsed == pytest.approx(12 * 60.0)

    view = presenter.apply(settings.replace(focus_interval=30 * 60.0))

    assert view.focus_elapsed == pytest.approx(12 * 60.0), "the block was restarted"
    assert view.focus_remaining == pytest.approx(18 * 60.0)


def test_a_longer_interval_pushes_the_break_out_rather_than_forward(running):
    presenter, clock, settings = running
    presenter.apply(settings.replace(focus_interval=30 * 60.0))

    # The eight minutes that were left under the old interval pass, and no
    # break arrives: eighteen are owed now, not eight.
    view = run_for(presenter, clock, 8 * 60.0)
    assert view.state is TimerState.FOCUSING

    view = run_for(presenter, clock, 10 * 60.0)
    assert view.state is TimerState.ON_BREAK


def test_shortening_the_interval_below_what_has_accrued_makes_a_break_due_now(running):
    """The honest answer to "remind me every ten minutes" from somebody who has
    been sitting there for twelve. Not a glitch — the alternative is pretending
    the twelve minutes did not happen."""
    presenter, clock, settings = running

    view = presenter.apply(settings.replace(focus_interval=10 * 60.0))
    assert view.state is TimerState.FOCUSING, "apply must not transition by itself"

    view = run_for(presenter, clock, TICK_SECONDS)
    assert view.break_owed or view.state is TimerState.ON_BREAK


def test_applying_settings_transitions_nothing_on_its_own(running):
    """Every state change stays in tick(), which has always owned them."""
    presenter, _, settings = running
    before = presenter.view().state

    assert presenter.apply(settings.replace(focus_interval=10 * 60.0)).state is before


def test_a_shorter_break_shortens_a_break_already_running(running):
    presenter, clock, settings = running
    presenter.take_break_now()
    run_for(presenter, clock, 5.0)
    assert presenter.view().state is TimerState.ON_BREAK

    presenter.apply(settings.replace(break_duration=6.0))
    view = run_for(presenter, clock, 2 * TICK_SECONDS)

    assert view.state is TimerState.FOCUSING


def test_the_progress_bar_follows_the_new_interval_immediately(running):
    """The view is recomputed against the new schedule, not the one it was
    built with — a progress bar still measuring the old interval would be the
    one visible thing that had not noticed."""
    presenter, _, settings = running
    assert presenter.view().progress == pytest.approx(0.6)

    view = presenter.apply(settings.replace(focus_interval=40 * 60.0))

    assert view.progress == pytest.approx(0.3)


def test_turning_tips_off_takes_the_evidence_line_off_the_break_screen(running):
    presenter, _, settings = running
    assert presenter.view().tip

    assert presenter.apply(settings.replace(tips=False)).tip == ""
    assert presenter.apply(settings.replace(tips=True)).tip


def test_the_presenter_reports_the_settings_it_is_running_on(running):
    presenter, _, settings = running
    changed = settings.replace(idle_threshold=300.0)

    presenter.apply(changed)
    assert presenter.settings == changed


def test_a_session_that_has_not_started_still_takes_new_settings():
    clock = FakeMonotonicClock()
    presenter = a_presenter(DEFAULTS, clock)

    view = presenter.apply(DEFAULTS.replace(focus_interval=45 * 60.0))

    assert view.state is TimerState.IDLE
    presenter.start()
    assert presenter.view().focus_remaining == pytest.approx(45 * 60.0)
