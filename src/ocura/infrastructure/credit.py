"""Rest observed before a break was owed, held until a break becomes owed.

Lives here and not in the domain on purpose: the domain has no concept of
pending credit, only of a RestSatisfied arriving at a moment when a break is
owed. See docs/architecture.md, "Rest taken before a break is owed".
"""

from __future__ import annotations

from dataclasses import dataclass

from ocura.domain.clock import MonotonicClock

#: Rest from three hours ago is not rest now, and stale credit silently
#: cancelling a genuine break is worse than no credit at all.
STALENESS_WINDOW = 30 * 60.0


@dataclass(frozen=True, slots=True)
class RestCredit:
    seconds: float
    source: str


class RestCreditLedger:
    """Holds at most one credit: the most recent rest, until it is spent or expires."""

    def __init__(self, clock: MonotonicClock, staleness_window: float = STALENESS_WINDOW) -> None:
        self._clock = clock
        self._staleness_window = staleness_window
        self._credit: RestCredit | None = None
        self._recorded_at: float | None = None

    def record(self, seconds: float, source: str) -> None:
        """Named source rather than a hard-coded lock detector, so P6 can add its own.

        Only session lock feeds this today; idle deliberately does not.
        """
        if seconds <= 0:
            return
        # A newer rest replaces an older one rather than summing: two separate
        # absences are not one long break, and the later one is the honest answer
        # to "how rested is this person right now".
        self._credit = RestCredit(seconds=seconds, source=source)
        self._recorded_at = self._clock.monotonic()

    def peek(self) -> RestCredit | None:
        self._expire()
        return self._credit

    def take(self) -> RestCredit | None:
        """Consumed once, then cleared. One rest can never satisfy two breaks."""
        credit = self.peek()
        self._credit = None
        self._recorded_at = None
        return credit

    def clear(self) -> None:
        self._credit = None
        self._recorded_at = None

    def _expire(self) -> None:
        if self._recorded_at is None:
            return
        if self._clock.monotonic() - self._recorded_at >= self._staleness_window:
            self.clear()
