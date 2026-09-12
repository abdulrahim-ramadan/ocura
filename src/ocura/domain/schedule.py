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

    def __post_init__(self) -> None:
        for field, value in (
            ("focus_interval", self.focus_interval),
            ("break_duration", self.break_duration),
            ("defer_interval", self.defer_interval),
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

    @classmethod
    def from_minutes(
        cls, focus_interval: float, break_duration: float, defer_interval: float
    ) -> BreakSchedule:
        return cls(focus_interval * 60.0, break_duration * 60.0, defer_interval * 60.0)


DEFAULT_SCHEDULE = BreakSchedule.from_minutes(
    focus_interval=20.0, break_duration=0.5, defer_interval=5.0
)
