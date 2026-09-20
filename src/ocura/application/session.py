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
    #: The user ended the break before it ran out. Distinct from BREAK_COMPLETED
    #: in the log and nowhere else: the dashboard says the same thing for both,
    #: because skipping says nothing about having skipped. The log keeps them
    #: apart because "did the breaks actually last twenty seconds" is the first
    #: question a tester's feedback raises, and a flattened kind cannot answer it.
    BREAK_SKIPPED = "break_skipped"
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
    #: The detector's reason, where there was one. Empty for the events that
    #: nothing had to explain.
    detail: str = ""
    #: Seconds, and None where no duration applies to this kind of event —
    #: which is a different fact from a duration of zero. Every event about a
    #: span of time carries the span it is about: how long a break lasted, how
    #: long one is postponed for, how long the rest that discharged it was, how
    #: long the stretch at the screen that earned it had run.
    duration: float | None = None


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
        return self._event(SessionEventKind.BREAK_SNOOZED, duration=self._deferred_for())

    def skip_break(self) -> SessionEvent:
        """End the break now. Ocura does not force breaks, so this is not a failure."""
        lasted = self._break_elapsed()
        self._timer.complete_break()
        return self._event(SessionEventKind.BREAK_SKIPPED, duration=lasted)

    def tick(self) -> list[SessionEvent]:
        events: list[SessionEvent] = []
        before = self._timer.state
        # Read before the tick: completing a break resets the stopwatch that
        # measures it, so afterwards there is nothing left to ask how long it was.
        lasted = self._break_elapsed()
        after = self._timer.tick()

        if before is TimerState.ON_BREAK and after is TimerState.FOCUSING:
            events.append(self._event(SessionEventKind.BREAK_COMPLETED, duration=lasted))
        if after is TimerState.BREAK_DUE and before is not TimerState.BREAK_DUE:
            # The duration on an offer is the stretch at the screen that earned
            # it, which is not the scheduled interval whenever a deferral or a
            # pause has stretched it.
            events.append(
                self._event(
                    SessionEventKind.BREAK_DUE,
                    duration=self._timer.snapshot().focus_elapsed,
                )
            )

        # Detectors are only worth waking when their answer can change something.
        if self._timer.state not in (TimerState.BREAK_DUE, TimerState.DEFERRED):
            return events

        outcome = self._policy.resolve(self._timer, self._context.assess(self._timer.snapshot()))
        match outcome:
            case BreakStarted():
                events.append(self._event(SessionEventKind.BREAK_STARTED))
            case BreakDeferred(reason=reason):
                events.append(
                    self._event(
                        SessionEventKind.BREAK_DEFERRED, reason, duration=self._deferred_for()
                    )
                )
            case BreakSatisfied(reason=reason, rested_for=rested_for):
                events.append(
                    self._event(SessionEventKind.BREAK_SATISFIED, reason, duration=rested_for)
                )
            case NoAction():
                pass
        return events

    def _event(
        self, kind: SessionEventKind, detail: str = "", duration: float | None = None
    ) -> SessionEvent:
        return SessionEvent(
            kind=kind,
            at=self._wall_clock.now(),
            state=self._timer.state,
            detail=detail,
            duration=duration,
        )

    def _break_elapsed(self) -> float | None:
        """How long the break running right now has lasted, or None if none is.

        Derived from what the snapshot already publishes rather than from a new
        accessor on the timer: the break stopwatch is the timer's business, and
        a second way to read it is a second thing that can disagree.

        The snapshot clamps at zero remaining, so a break that ran its course
        records exactly the scheduled duration however late the tick that
        noticed arrived. That is the right reading and not a rounding error: a
        pulse that lands half a second after the twenty seconds are up is
        latency in the timer that observed the break, not half a second more
        break. Only a break ended early reports a number nobody scheduled,
        which is the number worth having.
        """
        if self._timer.state is not TimerState.ON_BREAK:
            return None
        return self._timer.schedule.break_duration - self._timer.snapshot().break_remaining

    def _deferred_for(self) -> float | None:
        """How long the break just postponed stays postponed for.

        Read straight after the transition, while the deferral stopwatch is at
        zero, so what remains is the whole deadline. That deadline is the
        timer's own — it may be the schedule's, a detector's override, or the
        snooze interval — and reading it here means this does not have to know
        which.
        """
        if self._timer.state is not TimerState.DEFERRED:
            return None
        return self._timer.snapshot().deferral_remaining
