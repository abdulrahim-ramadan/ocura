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
    #: long one is postponed for, how long the rest that discharged it was.
    duration: float | None = None
    #: The focus block this event closed, in seconds at the screen, and None on
    #: every event that closes nothing. A block is measured once, when it ends —
    #: a break finished or skipped, a rest credited, the session stopped or
    #: restarted — so it is counted whole and exactly once, however many times
    #: its break was offered and put off on the way. A separate field rather
    #: than `duration`, because the row that closes a block is usually about a
    #: span of its own: the break that ended it.
    #:
    #: The cost: a block that never closes is never counted. A clean quit
    #: writes STOPPED, so that is a crash or a power cut losing at most the
    #: block that was running. Acceptable for statistics, and stated here
    #: rather than found later.
    focus: float | None = None


#: How far apart two readings of the last-input moment may land with no input
#: between them. The moment is worked out as monotonic time minus the idle
#: count, and those come from two different counters: they were measured
#: 0.02 to 0.05 s apart on 2026-10-30, drifting by about 0.014 s over six
#: minutes. A real return after an absence moves it by at least the idle
#: threshold, so a second of tolerance cannot hide one.
INPUT_JITTER = 1.0


class BreakSession:
    """Drives the timer, asks the context source when a break is owed, emits events.

    **What gets written, and what does not.** The log records things that
    happened, not the engine re-asking. When a deferral's retry runs out, the
    owed break is offered again and usually deferred again, every thirty
    seconds for as long as the user is away. Those re-offers are the engine at
    work, not events: BREAK_DUE is written once per focus block, the first time
    its break comes due, and a detector's BREAK_DEFERRED once on entering a
    deferral, with the reason that caused it. Staying deferred is a state. One
    of each per real occurrence is what makes the statistics page a count of
    occurrences rather than of ticks.
    """

    def __init__(
        self,
        schedule: BreakSchedule,
        monotonic: MonotonicClock,
        wall_clock: WallClock,
        context: ContextSource,
        policy: BreakPolicy | None = None,
    ) -> None:
        self._timer = BreakTimer(schedule, monotonic)
        self._monotonic = monotonic
        self._wall_clock = wall_clock
        self._context = context
        self._policy = policy or BreakPolicy()
        #: This block's break has been offered at least once.
        self._offered = False
        #: The owed break is being held back by a detector, and that has been
        #: written down. Cleared by anything that is not a detector deferring.
        self._deferring = False
        self._deferral_reason: str | None = None
        #: The latest input moment seen, on the monotonic clock.
        self._last_input: float | None = None

    @property
    def state(self) -> TimerState:
        return self._timer.state

    @property
    def deferral_reason(self) -> str | None:
        """Why a detector is holding the owed break back right now, if one is.

        Live, unlike the log: a deferral is written once, with the reason it
        began with, but a view should say why Ocura is waiting *now*.
        """
        return self._deferral_reason if self._deferring else None

    def observe_input(self, last_input: float, away_after: float) -> None:
        """Tell the timer whether anyone is at the screen. Call before `tick`.

        `last_input` is the monotonic moment of the latest keyboard or mouse
        input, and `away_after` the idle threshold: the one definition of away,
        which serves both "do not interrupt" and "do not count". Away begins
        `away_after` seconds after the last input, and ends at the next input.

        The rule is written over input moments rather than over the idle count,
        because of sleep. The input that wakes a machine resets the idle count
        before Ocura ticks again — measured on 2026-10-30: idle read 1.9 s on
        the first sample after a 39 s sleep — so the count alone never sees the
        sleep. Two consecutive input moments further apart than the threshold
        bound an absence, whether Ocura was ticking through it or not.
        """
        seen = self._last_input
        self._last_input = last_input if seen is None else max(seen, last_input)
        if seen is None:
            seen = last_input
        if last_input - seen > INPUT_JITTER:
            if last_input - seen >= away_after:
                self._timer.mark_away(since=seen + away_after)
            self._timer.mark_present(at=last_input)
        elif self._monotonic.monotonic() - seen >= away_after:
            self._timer.mark_away(since=seen + away_after)

    @property
    def can_snooze(self) -> bool:
        return self._timer.can_snooze

    @property
    def snoozes_used(self) -> int:
        return self._timer.snoozes_used

    def snapshot(self) -> TimerSnapshot:
        return self._timer.snapshot()

    def reschedule(self, schedule: BreakSchedule) -> None:
        """Apply a new schedule to the running timer. Emits nothing.

        A settings change is not something that happened to the session, so it
        is not a session event. What follows from it — a break becoming due
        because the interval shrank — arrives through the next tick as the
        ordinary event it is.
        """
        self._timer.reschedule(schedule)

    def start(self) -> SessionEvent:
        # A start while running is a restart, and ends the block that was open.
        closed = self._open_block()
        self._timer.start()
        self._new_block()
        return self._event(SessionEventKind.STARTED, focus=closed)

    def pause(self) -> SessionEvent:
        self._timer.pause()
        return self._event(SessionEventKind.PAUSED)

    def resume(self) -> SessionEvent:
        self._timer.resume()
        return self._event(SessionEventKind.RESUMED)

    def stop(self) -> SessionEvent:
        closed = self._open_block()
        self._timer.reset()
        self._new_block()
        return self._event(SessionEventKind.STOPPED, focus=closed)

    def take_break_now(self) -> SessionEvent:
        """The user asked for a break, whether or not one was owed."""
        self._timer.take_break_now()
        self._deferring = False
        return self._event(SessionEventKind.BREAK_STARTED_BY_USER)

    def snooze(self) -> SessionEvent:
        """The user postpones the break. The cap is enforced in the domain.

        Always written: it is the user deciding, and each decision counts
        towards the cap. A detector deferring after it is a new deferral.
        """
        self._timer.snooze()
        self._deferring = False
        return self._event(SessionEventKind.BREAK_SNOOZED, duration=self._deferred_for())

    def skip_break(self) -> SessionEvent:
        """End the break now. Ocura does not force breaks, so this is not a failure."""
        lasted = self._break_elapsed()
        closed = self._open_block()
        self._timer.complete_break()
        self._new_block()
        return self._event(SessionEventKind.BREAK_SKIPPED, duration=lasted, focus=closed)

    def tick(self) -> list[SessionEvent]:
        events: list[SessionEvent] = []
        before = self._timer.state
        # Read before the tick: completing a break resets the stopwatches that
        # measure it and the block before it, so afterwards there is nothing
        # left to ask how long either was.
        lasted = self._break_elapsed()
        closed = self._open_block()
        after = self._timer.tick()

        if before is TimerState.ON_BREAK and after is TimerState.FOCUSING:
            self._new_block()
            events.append(
                self._event(SessionEventKind.BREAK_COMPLETED, duration=lasted, focus=closed)
            )
        if after is TimerState.BREAK_DUE and not self._offered:
            # Once per block. A retry re-offering a break already owed is the
            # engine asking again, not a break coming due.
            self._offered = True
            events.append(self._event(SessionEventKind.BREAK_DUE))

        # Detectors are only worth waking when their answer can change something.
        if self._timer.state not in (TimerState.BREAK_DUE, TimerState.DEFERRED):
            return events

        closed = self._open_block()
        outcome = self._policy.resolve(self._timer, self._context.assess(self._timer.snapshot()))
        match outcome:
            case BreakStarted():
                self._deferring = False
                events.append(self._event(SessionEventKind.BREAK_STARTED))
            case BreakDeferred(reason=reason):
                self._deferral_reason = reason
                if not self._deferring:
                    self._deferring = True
                    events.append(
                        self._event(
                            SessionEventKind.BREAK_DEFERRED, reason, duration=self._deferred_for()
                        )
                    )
            case BreakSatisfied(reason=reason, rested_for=rested_for):
                self._new_block()
                events.append(
                    self._event(
                        SessionEventKind.BREAK_SATISFIED, reason, duration=rested_for, focus=closed
                    )
                )
            case NoAction():
                pass
        return events

    def _event(
        self,
        kind: SessionEventKind,
        detail: str = "",
        duration: float | None = None,
        focus: float | None = None,
    ) -> SessionEvent:
        return SessionEvent(
            kind=kind,
            at=self._wall_clock.now(),
            state=self._timer.state,
            detail=detail,
            duration=duration,
            focus=focus,
        )

    def _open_block(self) -> float | None:
        """The running block's time at the screen, or None if no block is open."""
        if self._timer.state is TimerState.IDLE:
            return None
        return self._timer.snapshot().focus_elapsed

    def _new_block(self) -> None:
        self._offered = False
        self._deferring = False
        self._deferral_reason = None

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
