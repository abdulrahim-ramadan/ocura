from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ocura.domain.clock import MonotonicClock
from ocura.domain.errors import (
    ConfigurationError,
    InsufficientRestError,
    SnoozeLimitReached,
    TransitionError,
)
from ocura.domain.schedule import BreakSchedule


class TimerState(StrEnum):
    IDLE = "idle"
    FOCUSING = "focusing"
    #: Still focusing, but close enough to the break to say so. A state rather
    #: than a computed flag so the warning has one unambiguous moment to fire on.
    PRE_BREAK = "pre_break"
    BREAK_DUE = "break_due"
    ON_BREAK = "on_break"
    PAUSED = "paused"
    DEFERRED = "deferred"


#: DEFERRED is the owed break itself, postponed to a retry deadline. There is no
#: flag anywhere saying a break is owed; these two states are that statement.
_BREAK_OWED = frozenset({TimerState.BREAK_DUE, TimerState.DEFERRED})

#: Time at the screen keeps counting while a break goes untaken, so focus_elapsed
#: stays honest about the real stretch rather than freezing at the interval.
#: That is about a user who is still there and has not taken the offer. Whether
#: anyone is there at all is a separate question, answered by `_away`: focus
#: accrues in these states *and* only while the user is present.
_FOCUS_ACCRUING = frozenset({TimerState.FOCUSING, TimerState.PRE_BREAK, *_BREAK_OWED})

#: The user may ask for a break from any state where they are at the screen. Kept
#: separate from _FOCUS_ACCRUING despite matching it today: one is about counting
#: time, this is about who is allowed to ask.
_USER_MAY_TAKE_BREAK = frozenset({TimerState.FOCUSING, TimerState.PRE_BREAK, *_BREAK_OWED})

#: A break may be postponed twice in a row. Beyond that it is offered again
#: without the option — never forced, just not postponable a third time. Nagging
#: is not a feature and neither is a break the user cannot get away from.
MAX_SNOOZES = 2

#: Snoozing is a user's answer to "shall we do this now", so it is available
#: from the warning, from the offer, and from the break itself.
_USER_MAY_SNOOZE = frozenset({TimerState.PRE_BREAK, TimerState.BREAK_DUE, TimerState.ON_BREAK})


class _Stopwatch:
    """Banked seconds plus, when running, the seconds since the last monotonic reading."""

    __slots__ = ("_banked", "_started_at", "_stopped_at")

    def __init__(self) -> None:
        self._banked = 0.0
        self._started_at: float | None = None
        self._stopped_at: float | None = None

    @property
    def running(self) -> bool:
        return self._started_at is not None

    def elapsed(self, now: float) -> float:
        if self._started_at is None:
            return self._banked
        return self._banked + (now - self._started_at)

    def set_running(self, running: bool, now: float, at: float | None = None) -> None:
        """Start or stop, by default now, or at a moment already past.

        `at` exists for absence, which is only ever noticed after it began. It
        is clamped so the stopwatch can neither give back time from before it
        started nor take time from before it stopped: a moment in the past can
        move an edge, never invent or erase a stretch the watch was not timing.
        """
        if running == self.running:
            return
        moment = now if at is None else min(at, now)
        if running:
            if self._stopped_at is not None:
                moment = max(moment, self._stopped_at)
            self._started_at = moment
        else:
            assert self._started_at is not None
            moment = max(moment, self._started_at)
            self._banked += moment - self._started_at
            self._started_at = None
            self._stopped_at = moment

    def reset(self) -> None:
        self._banked = 0.0
        self._started_at = None
        self._stopped_at = None


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    state: TimerState
    focus_elapsed: float
    focus_remaining: float
    break_remaining: float
    deferral_remaining: float
    #: Nobody has been at the screen for longer than the idle threshold, so
    #: focus is not accruing. A view needs it: without a reason on screen, a
    #: countdown that stops reads as a frozen program.
    away: bool = False

    @property
    def break_owed(self) -> bool:
        return self.state in _BREAK_OWED


class BreakTimer:
    """The break state machine. Its only contact with time is the monotonic clock."""

    def __init__(self, schedule: BreakSchedule, clock: MonotonicClock) -> None:
        self._schedule = schedule
        self._clock = clock
        self._state = TimerState.IDLE
        self._resume_state: TimerState | None = None
        self._retry_after: float | None = None
        self._snoozes = 0
        # A stored flag, in a class that deleted its stored `break_owed` for
        # being one. The difference is where the fact comes from. `break_owed`
        # was derivable from the state, so storing it made a second source of
        # truth free to drift from the first. Absence cannot be derived from
        # anything the domain holds: it is external information the domain is
        # told, through `mark_away` and `mark_present`, and remembering what
        # it was told is the only way to have it at all.
        self._away = False
        self._focus = _Stopwatch()
        self._break = _Stopwatch()
        self._deferral = _Stopwatch()

    @property
    def schedule(self) -> BreakSchedule:
        return self._schedule

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def snoozes_used(self) -> int:
        """Consecutive snoozes. Reset by a break actually happening."""
        return self._snoozes

    @property
    def can_snooze(self) -> bool:
        return self._state in _USER_MAY_SNOOZE and self._snoozes < MAX_SNOOZES

    # --- commands ---------------------------------------------------------

    def start(self) -> None:
        """Begin (or restart) a focus block from zero."""
        self._resume_state = None
        self._retry_after = None
        self._start_focus_block(self._clock.monotonic())

    def reschedule(self, schedule: BreakSchedule) -> None:
        """Adopt a new schedule without touching a single stopwatch.

        **The elapsed time is kept and measured against the new interval.**
        That is the whole decision, and the two alternatives are both worse.
        Restarting the block would silently erase work the user has already
        done at the screen — they were there, and a setting they changed is not
        a reason to pretend otherwise. Waiting a full new interval from now
        would count the same stretch twice.

        The consequence is deliberate: shortening the interval below what has
        already accrued makes a break due on the next tick. That is not a
        glitch, it is the honest answer to "remind me every fifteen minutes"
        from someone who has been sitting there for twenty.

        No transition happens here. `tick()` is what notices that the new
        numbers have made something true, which keeps every state change in the
        one place that has always owned them.
        """
        self._schedule = schedule

    def reset(self) -> None:
        now = self._clock.monotonic()
        self._resume_state = None
        self._retry_after = None
        self._snoozes = 0
        self._reset_all()
        self._enter(TimerState.IDLE, now)

    def begin_break(self) -> None:
        if self._state is not TimerState.BREAK_DUE:
            raise TransitionError(f"cannot begin a break from {self._state}")
        now = self._clock.monotonic()
        self._break.reset()
        self._enter(TimerState.ON_BREAK, now)

    def take_break_now(self) -> None:
        """The user asked for a break.

        Deliberately not a widened guard on begin_break. That command is the
        engine accepting an owed break at a moment the context approved, and it
        stays narrow so the engine cannot drift into a break on its own. This is
        the user overriding all of that, which was never the thing being
        prevented. Clears any owed deferral: a break just taken is not still owed.
        """
        if self._state not in _USER_MAY_TAKE_BREAK:
            raise TransitionError(f"cannot take a break from {self._state}")
        now = self._clock.monotonic()
        self._retry_after = None
        self._break.reset()
        self._enter(TimerState.ON_BREAK, now)

    def complete_break(self) -> None:
        """The break was taken. Ending early is allowed; Ocura does not force breaks."""
        if self._state is not TimerState.ON_BREAK:
            raise TransitionError(f"cannot complete a break from {self._state}")
        self._retry_after = None
        self._start_focus_block(self._clock.monotonic())

    def defer(self, retry_after: float | None = None) -> None:
        """Wrong moment. Keep working; the break stays owed and returns at the deadline.

        retry_after overrides the schedule for this one deferral only.
        """
        if self._state is not TimerState.BREAK_DUE:
            raise TransitionError(f"cannot defer from {self._state}")
        if retry_after is not None and (not math.isfinite(retry_after) or retry_after <= 0):
            raise ConfigurationError(
                f"retry_after must be positive and finite, got {retry_after!r}"
            )
        now = self._clock.monotonic()
        self._retry_after = retry_after
        self._deferral.reset()
        self._enter(TimerState.DEFERRED, now)

    def snooze(self) -> None:
        """The user postpones the break. Capped, and the cap lives here.

        Unlike defer(), which is the environment saying now is a bad moment,
        this is the user saying so. Both land in DEFERRED — an owed break with a
        deadline — because that is what a postponed break is, whoever asked.
        """
        if self._state not in _USER_MAY_SNOOZE:
            raise TransitionError(f"cannot snooze from {self._state}")
        if self._snoozes >= MAX_SNOOZES:
            raise SnoozeLimitReached(
                f"already postponed {self._snoozes} times in a row; "
                "the break is offered again without the option"
            )

        now = self._clock.monotonic()
        self._snoozes += 1
        self._retry_after = self._schedule.snooze_interval
        self._deferral.reset()
        self._enter(TimerState.DEFERRED, now)

    def satisfy_break(self, rest_duration: float) -> None:
        """An external rest already gave the user the break they were owed."""
        if self._state not in _BREAK_OWED:
            raise TransitionError(f"cannot satisfy a break from {self._state}")
        if not math.isfinite(rest_duration) or rest_duration <= 0:
            raise InsufficientRestError(
                f"rest_duration must be positive and finite, got {rest_duration!r}"
            )
        if rest_duration < self._schedule.break_duration:
            raise InsufficientRestError(
                f"rest of {rest_duration}s is shorter than the "
                f"{self._schedule.break_duration}s break it would discharge"
            )
        self._retry_after = None
        self._start_focus_block(self._clock.monotonic())

    def pause(self) -> None:
        if self._state in (TimerState.IDLE, TimerState.PAUSED):
            raise TransitionError(f"cannot pause from {self._state}")
        now = self._clock.monotonic()
        self._resume_state = self._state
        self._enter(TimerState.PAUSED, now)

    def resume(self) -> None:
        if self._state is not TimerState.PAUSED or self._resume_state is None:
            raise TransitionError(f"cannot resume from {self._state}")
        now = self._clock.monotonic()
        resumed, self._resume_state = self._resume_state, None
        self._enter(resumed, now)

    def mark_away(self, since: float) -> None:
        """Nobody has been at the screen since `since`, a monotonic moment.

        Focus stops accruing from that moment, not from now: absence is only
        ever noticed after it began, and the stretch between the two was not
        time at the screen either. No state changes. Absence is not a phase of
        the break cycle — it can overlap focusing, an owed break or a deferral
        — so it is a condition on counting rather than a state of its own, and
        an owed break stays owed through it.
        """
        if self._away:
            return
        self._away = True
        self._apply_accrual(self._clock.monotonic(), at=since)

    def mark_present(self, at: float) -> None:
        """Somebody is back, as of `at`: the moment of the input that said so."""
        if not self._away:
            return
        self._away = False
        self._apply_accrual(self._clock.monotonic(), at=at)

    def tick(self) -> TimerState:
        """Apply whatever the passage of time has made true. Safe to call at any rate."""
        now = self._clock.monotonic()
        match self._state:
            case TimerState.FOCUSING | TimerState.PRE_BREAK if (
                self._focus.elapsed(now) >= self._schedule.focus_interval
            ):
                self._enter(TimerState.BREAK_DUE, now)
            case TimerState.FOCUSING if self._focus.elapsed(now) >= self._warning_at:
                self._enter(TimerState.PRE_BREAK, now)
            case TimerState.DEFERRED if self._deferral.elapsed(now) >= self._retry_deadline:
                self._enter(TimerState.BREAK_DUE, now)
            case TimerState.ON_BREAK if self._break.elapsed(now) >= self._schedule.break_duration:
                self.complete_break()
            case _:
                pass
        return self._state

    # --- observation ------------------------------------------------------

    def snapshot(self) -> TimerSnapshot:
        now = self._clock.monotonic()
        focus_elapsed = self._focus.elapsed(now)
        return TimerSnapshot(
            state=self._state,
            focus_elapsed=focus_elapsed,
            focus_remaining=max(0.0, self._schedule.focus_interval - focus_elapsed),
            break_remaining=(
                max(0.0, self._schedule.break_duration - self._break.elapsed(now))
                if self._state is TimerState.ON_BREAK
                else 0.0
            ),
            deferral_remaining=(
                max(0.0, self._retry_deadline - self._deferral.elapsed(now))
                if self._state is TimerState.DEFERRED
                else 0.0
            ),
            away=self._away,
        )

    # --- internals --------------------------------------------------------

    @property
    def _warning_at(self) -> float:
        return self._schedule.focus_interval - self._schedule.pre_break_warning

    @property
    def _retry_deadline(self) -> float:
        if self._retry_after is None:
            return self._schedule.defer_interval
        return self._retry_after

    def _start_focus_block(self, now: float) -> None:
        # A break that actually happened clears the run of snoozes: the cap is on
        # consecutive postponements, not on a whole day of them.
        self._snoozes = 0
        self._reset_all()
        self._enter(TimerState.FOCUSING, now)

    def _reset_all(self) -> None:
        self._focus.reset()
        self._break.reset()
        self._deferral.reset()

    def _enter(self, state: TimerState, now: float) -> None:
        self._state = state
        # One place decides which stopwatches run in which state, so pause and
        # resume cannot drift apart from the transitions.
        self._apply_accrual(now)
        self._break.set_running(state is TimerState.ON_BREAK, now)
        self._deferral.set_running(state is TimerState.DEFERRED, now)

    def _apply_accrual(self, now: float, at: float | None = None) -> None:
        self._focus.set_running(self._state in _FOCUS_ACCRUING and not self._away, now, at=at)
