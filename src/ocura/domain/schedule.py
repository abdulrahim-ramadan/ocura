from __future__ import annotations

import math
from dataclasses import dataclass

from ocura.domain.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class BreakSchedule:
    """All durations in seconds; the domain has no opinion about minutes."""

    focus_interval: float
    break_duration: float
    defer_interval: float
    #: How long before a break is due to warn that it is coming.
    pre_break_warning: float = 60.0
    #: How long a user-initiated snooze postpones an owed break.
    snooze_interval: float = 300.0

    def __post_init__(self) -> None:
        for field, value in (
            ("focus_interval", self.focus_interval),
            ("break_duration", self.break_duration),
            ("defer_interval", self.defer_interval),
            ("pre_break_warning", self.pre_break_warning),
            ("snooze_interval", self.snooze_interval),
        ):
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ConfigurationError(f"{field} must be a number, got {value!r}")
            if not math.isfinite(value):
                raise ConfigurationError(f"{field} must be finite, got {value!r}")
            if value <= 0:
                raise ConfigurationError(f"{field} must be positive, got {value!r}")

        # A break at least as long as the work block, or a deferral longer than a
        # fresh focus block, would make the schedule meaningless rather than gentle.
        if self.break_duration >= self.focus_interval:
            raise ConfigurationError(
                "break_duration must be shorter than focus_interval "
                f"({self.break_duration} >= {self.focus_interval})"
            )
        if self.defer_interval >= self.focus_interval:
            raise ConfigurationError(
                "defer_interval must be shorter than focus_interval "
                f"({self.defer_interval} >= {self.focus_interval})"
            )
        # A warning that starts before the focus block does is not a warning.
        if self.pre_break_warning >= self.focus_interval:
            raise ConfigurationError(
                "pre_break_warning must be shorter than focus_interval "
                f"({self.pre_break_warning} >= {self.focus_interval})"
            )
        if self.snooze_interval >= self.focus_interval:
            raise ConfigurationError(
                "snooze_interval must be shorter than focus_interval "
                f"({self.snooze_interval} >= {self.focus_interval})"
            )

    @classmethod
    def from_minutes(
        cls,
        focus_interval: float,
        break_duration: float,
        defer_interval: float,
        pre_break_warning: float = 1.0,
        snooze_interval: float = 5.0,
    ) -> BreakSchedule:
        return cls(
            focus_interval * 60.0,
            break_duration * 60.0,
            defer_interval * 60.0,
            pre_break_warning * 60.0,
            snooze_interval * 60.0,
        )


#: Twenty minutes of focus, twenty seconds of rest: the 20-20-20 guideline the
#: whole product is shaped around.
DEFAULT_SCHEDULE = BreakSchedule(
    focus_interval=20 * 60.0,
    break_duration=20.0,
    defer_interval=5 * 60.0,
    pre_break_warning=60.0,
    snooze_interval=5 * 60.0,
)
