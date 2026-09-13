from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ocura.domain.clock import MonotonicClock, WallClock
from ocura.domain.context import ContextSource
from ocura.domain.policy import (
    BreakDeferred,
    BreakPolicy,
    BreakSatisfied,
    BreakStarted,
    NoAction,
)
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import BreakTimer, TimerSnapshot, TimerState


class SessionEventKind(StrEnum):
    STARTED = "started"
    BREAK_DUE = "break_due"
    BREAK_STARTED = "break_started"
    #: Distinct from BREAK_STARTED so P4 can tell a break the user asked for from
    #: one the engine offered.
    BREAK_STARTED_BY_USER = "break_started_by_user"
    BREAK_COMPLETED = "break_completed"
    BREAK_DEFERRED = "break_deferred"
    #: Postponed by the user, not by a detector. P4 will want to tell them apart.
    BREAK_SNOOZED = "break_snoozed"
    BREAK_SATISFIED = "break_satisfied"
    PAUSED = "paused"
    RESUMED = "resumed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class SessionEvent:
    kind: SessionEventKind
    #: Calendar time, the one place P0 genuinely needs it: events are what P4
    #: will persist and what a UI will show as "your last break was at 14:20".
    at: datetime
    state: TimerState
    detail: str = ""


class BreakSession:
    """Drives the timer, asks the context source when a break is owed, emits events."""

    def __init__(
        self,
        schedule: BreakSchedule,
        monotonic: MonotonicClock,
        wall_clock: WallClock,
        context: ContextSource,
        policy: BreakPolicy | None = None,
    ) -> None:
        self._timer = BreakTimer(schedule, monotonic)
        self._wall_clock = wall_clock
        self._context = context
        self._policy = policy or BreakPolicy()

    @property
    def state(self) -> TimerState:
        return self._timer.state

    @property
    def can_snooze(self) -> bool:
        return self._timer.can_snooze

    @property
    def snoozes_used(self) -> int:
        return self._timer.snoozes_used

    def snapshot(self) -> TimerSnapshot:
        return self._timer.snapshot()

    def start(self) -> SessionEvent:
        self._timer.start()
        return self._event(SessionEventKind.STARTED)

    def pause(self) -> SessionEvent:
        self._timer.pause()
        return self._event(SessionEventKind.PAUSED)

    def resume(self) -> SessionEvent:
        self._timer.resume()
        return self._event(SessionEventKind.RESUMED)

    def stop(self) -> SessionEvent:
        self._timer.reset()
        return self._event(SessionEventKind.STOPPED)

    def take_break_now(self) -> SessionEvent:
        """The user asked for a break, whether or not one was owed."""
        self._timer.take_break_now()
        return self._event(SessionEventKind.BREAK_STARTED_BY_USER)

    def snooze(self) -> SessionEvent:
        """The user postpones the break. The cap is enforced in the domain."""
        self._timer.snooze()
        return self._event(SessionEventKind.BREAK_SNOOZED)

    def skip_break(self) -> SessionEvent:
        """End the break now. Ocura does not force breaks, so this is not a failure."""
        self._timer.complete_break()
        return self._event(SessionEventKind.BREAK_COMPLETED)

    def tick(self) -> list[SessionEvent]:
        events: list[SessionEvent] = []
        before = self._timer.state
        after = self._timer.tick()

        if before is TimerState.ON_BREAK and after is TimerState.FOCUSING:
            events.append(self._event(SessionEventKind.BREAK_COMPLETED))
        if after is TimerState.BREAK_DUE and before is not TimerState.BREAK_DUE:
            events.append(self._event(SessionEventKind.BREAK_DUE))

        # Detectors are only worth waking when their answer can change something.
        if self._timer.state not in (TimerState.BREAK_DUE, TimerState.DEFERRED):
            return events

        outcome = self._policy.resolve(self._timer, self._context.assess(self._timer.snapshot()))
        match outcome:
            case BreakStarted():
                events.append(self._event(SessionEventKind.BREAK_STARTED))
            case BreakDeferred(reason=reason):
                events.append(self._event(SessionEventKind.BREAK_DEFERRED, reason))
            case BreakSatisfied(reason=reason):
                events.append(self._event(SessionEventKind.BREAK_SATISFIED, reason))
            case NoAction():
                pass
        return events

    def _event(self, kind: SessionEventKind, detail: str = "") -> SessionEvent:
        return SessionEvent(
            kind=kind, at=self._wall_clock.now(), state=self._timer.state, detail=detail
        )
