"""What the user can change, what it is allowed to be, and where it is kept.

One immutable `Settings` value, validated at the boundary and never clamped.
A value the user typed is either accepted or refused with a reason; quietly
rounding it to something legal is worse than both, because the user then
believes something that is not true about their own configuration.

`SettingsRepository` is the seam, the same shape as `SessionJournal` and
`StatisticsSource`: a protocol named here, implemented over SQLite in
`ocura.infrastructure.storage`, and satisfied by an in-memory stand-in when
there is nowhere to save. Settings that cannot be saved still apply to the
running session — losing them at quit is a smaller harm than refusing to
change them at all.

**Why these live in the database and window geometry does not.** A setting is
something the user chose and would be annoyed to lose; geometry is where a
window happened to be. `docs/architecture.md` promised the `shell/` QSettings
namespace would make that split a move rather than an excavation, and this is
the move: theme and the break-screen tips leave it, geometry stays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from ocura.domain.errors import ConfigurationError
from ocura.domain.schedule import DEFAULT_SCHEDULE, BreakSchedule

#: The themes the settings model will accept. Named here rather than imported
#: from `ocura.ui.theme`, which this layer is banned from reaching, and checked
#: against the real theme table by a test so the two cannot drift apart.
THEME_NAMES = ("dark", "light")

#: The rhythms offered on the first-run screen, in minutes. Twenty is the
#: guideline the product is shaped around; the longer two exist because a
#: guideline nobody follows helps nobody, and someone who will take a break
#: every forty-five minutes is better served than someone who turns Ocura off.
#: See docs/EVIDENCE.md.
RHYTHM_MINUTES = (20, 30, 45)

#: Bounds that exist to catch a typo rather than to express a preference. A
#: four-second focus block or a nine-hour one is a slip of the keyboard, and
#: refusing it with a reason is kinder than accepting it and behaving oddly.
MIN_FOCUS_SECONDS = 60.0
MAX_FOCUS_SECONDS = 8 * 3600.0
MIN_BREAK_SECONDS = 5.0
MAX_IDLE_SECONDS = 3600.0


class InvalidSettings(ConfigurationError):
    """A settings value or combination that cannot be honoured.

    A `ConfigurationError`, because that is what the domain already raises for
    exactly these conditions and inventing a parallel hierarchy for the same
    fact would mean two things to catch. What this adds is the field it is
    about, so a page can put the message next to the control that caused it,
    and wording a person can act on: the domain's own message names internal
    field names and compares raw seconds, which is right for a log and wrong
    for someone who just typed a number into a box.
    """

    def __init__(self, message: str, field: str = "") -> None:
        super().__init__(message)
        self.field = field


def _minutes(seconds: float) -> str:
    """For error messages, where "1200 seconds" is not what the user typed.

    Rounded to one decimal, because the alternative is a sentence containing
    "11.6667 minutes" — which is arithmetic showing its working, not an
    explanation of what went wrong.
    """
    if seconds < 60:
        return f"{round(seconds, 1):g} seconds"
    value = round(seconds / 60, 1)
    return f"{value:g} minute" if value == 1 else f"{value:g} minutes"


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the user can change. Seconds throughout, like the domain.

    The UI shows minutes where minutes are what a person thinks in, and
    converts at its own edge. Two units in the model would mean a conversion
    somewhere in the middle, which is where the off-by-sixty lives.
    """

    focus_interval: float = DEFAULT_SCHEDULE.focus_interval
    break_duration: float = DEFAULT_SCHEDULE.break_duration
    pre_break_warning: float = DEFAULT_SCHEDULE.pre_break_warning
    #: How long without input before an offer is pointless. Not a schedule
    #: field: it configures a detector, not the timer.
    idle_threshold: float = 120.0
    autostart: bool = False
    theme: str = "dark"
    #: The evidence line at the foot of the break screen.
    tips: bool = True
    #: Set once the first-run screens have been through. Persisted with the
    #: settings rather than beside them: "has this person been introduced to
    #: Ocura" is a fact about them, and it belongs wherever their choices are.
    introduced: bool = False

    def replace(self, **changes: object) -> Settings:
        return replace(self, **changes)  # type: ignore[arg-type]

    # --- validation -------------------------------------------------------

    def validate(self) -> Settings:
        """Return self if every value and every combination is honourable.

        Raises `InvalidSettings` otherwise, and never returns something other
        than what it was given: this does not repair, round or clamp.
        """
        self._check_numbers()
        self._check_combinations()
        if self.theme not in THEME_NAMES:
            raise InvalidSettings(
                f"{self.theme!r} is not a theme Ocura has. "
                f"Choose one of: {', '.join(THEME_NAMES)}.",
                "theme",
            )
        # The backstop. Everything above names a condition in the user's own
        # terms; this catches anything the domain refuses that the list has not
        # learned about yet, so a new rule in BreakSchedule cannot slip through
        # here unenforced.
        self.schedule()
        return self

    def _check_numbers(self) -> None:
        fields = (
            ("focus_interval", self.focus_interval, "The break interval"),
            ("break_duration", self.break_duration, "The break length"),
            ("pre_break_warning", self.pre_break_warning, "The warning lead time"),
            ("idle_threshold", self.idle_threshold, "The idle threshold"),
        )
        for field, value, name in fields:
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise InvalidSettings(f"{name} must be a number.", field)
            if not math.isfinite(value) or value <= 0:
                raise InvalidSettings(f"{name} must be longer than nothing.", field)

        if self.focus_interval < MIN_FOCUS_SECONDS:
            raise InvalidSettings(
                f"An interval of {_minutes(self.focus_interval)} would mean almost "
                "continuous interruption. The shortest Ocura will accept is "
                f"{_minutes(MIN_FOCUS_SECONDS)}.",
                "focus_interval",
            )
        if self.focus_interval > MAX_FOCUS_SECONDS:
            raise InvalidSettings(
                f"An interval of {_minutes(self.focus_interval)} is longer than Ocura "
                f"will accept ({_minutes(MAX_FOCUS_SECONDS)}). If you meant to stop "
                "the reminders, pause them instead.",
                "focus_interval",
            )
        if self.break_duration < MIN_BREAK_SECONDS:
            raise InvalidSettings(
                f"A break of {_minutes(self.break_duration)} is too short to rest "
                f"anything. The shortest Ocura will accept is "
                f"{_minutes(MIN_BREAK_SECONDS)}.",
                "break_duration",
            )
        if self.idle_threshold > MAX_IDLE_SECONDS:
            raise InvalidSettings(
                f"An idle threshold of {_minutes(self.idle_threshold)} is longer than "
                f"Ocura will accept ({_minutes(MAX_IDLE_SECONDS)}).",
                "idle_threshold",
            )

    def _check_combinations(self) -> None:
        """The impossible pairs, each named in terms of what the user set.

        These are the same conditions `BreakSchedule` refuses. They are stated
        again here only to be stated *readably* — the domain's message compares
        two raw second counts under their internal field names, which is the
        right thing for a log to say and the wrong thing to put beside a spin
        box someone is looking at.
        """
        if self.break_duration >= self.focus_interval:
            raise InvalidSettings(
                f"A break of {_minutes(self.break_duration)} does not fit inside an "
                f"interval of {_minutes(self.focus_interval)}. The break has to be "
                "shorter than the time between breaks.",
                "break_duration",
            )
        if self.pre_break_warning >= self.focus_interval:
            raise InvalidSettings(
                f"A warning {_minutes(self.pre_break_warning)} ahead would start before "
                f"the interval of {_minutes(self.focus_interval)} it is warning about. "
                "The lead time has to be shorter than the interval.",
                "pre_break_warning",
            )

    # --- what the rest of the application takes ----------------------------

    def schedule(self) -> BreakSchedule:
        """The domain object. Raises ConfigurationError if it cannot be built.

        `defer_interval` and `snooze_interval` are derived rather than
        configured. Both must be shorter than the focus interval or the domain
        refuses the schedule outright, and a user who sets a five-minute
        interval should get a working five-minute rhythm rather than an error
        about two fields no screen has ever shown them. Deriving is not
        clamping: nobody typed these.
        """
        ceiling = self.focus_interval / 2
        return BreakSchedule(
            focus_interval=self.focus_interval,
            break_duration=self.break_duration,
            defer_interval=min(DEFAULT_SCHEDULE.defer_interval, ceiling),
            pre_break_warning=self.pre_break_warning,
            snooze_interval=min(DEFAULT_SCHEDULE.snooze_interval, ceiling),
        )


DEFAULTS = Settings()


# --- persistence -----------------------------------------------------------


@runtime_checkable
class SettingsRepository(Protocol):
    """Somewhere durable for settings to live."""

    def load(self) -> Settings: ...

    def save(self, settings: Settings) -> None: ...


class MemorySettings:
    """Nowhere to save to. Everything still works until the process ends.

    The same bargain as `NullJournal`: a disk that cannot be written costs the
    user their stored preferences and never their ability to change one.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or DEFAULTS

    def load(self) -> Settings:
        return self._settings

    def save(self, settings: Settings) -> None:
        self._settings = settings


@runtime_checkable
class ShellNamespace(Protocol):
    """The `shell/` QSettings keys, reduced to what a migration needs.

    A protocol rather than a QSettings, so the move out of the shell namespace
    is testable without a Qt application — the migration is a one-way door and
    the thing worth being sure about is that it fires once, takes the value
    with it, and leaves nothing behind to be read again next launch.
    """

    def value(self, key: str) -> object: ...

    def remove(self, key: str) -> None: ...

    def contains(self, key: str) -> bool: ...


#: Where the theme used to live. P4 put it here deliberately so that P5 would
#: have a namespace to move rather than a registry to excavate.
LEGACY_THEME_KEY = "shell/theme"


def migrate_from_shell(settings: Settings, shell: ShellNamespace) -> tuple[Settings, bool]:
    """Carry the theme out of the shell namespace, once.

    Returns the settings to use and whether anything moved. The legacy key is
    removed on the way, so a later launch cannot resurrect a stale choice over
    one the user has since made in Settings.

    Only the theme moves, because only the theme was ever there. The tips
    toggle is new in P5 and has no legacy value to rescue.
    """
    if settings.introduced or not shell.contains(LEGACY_THEME_KEY):
        # Already migrated, or nothing to migrate. `introduced` is the marker
        # that this database has been written by a P5 build, which is the only
        # thing that distinguishes "no stored theme" from "never had one".
        if shell.contains(LEGACY_THEME_KEY):
            shell.remove(LEGACY_THEME_KEY)
        return settings, False

    stored = shell.value(LEGACY_THEME_KEY)
    shell.remove(LEGACY_THEME_KEY)
    if not isinstance(stored, str) or stored not in THEME_NAMES:
        return settings, False
    return settings.replace(theme=stored), True
