from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ocura.domain.clock import MonotonicClock
from ocura.domain.errors import ConfigurationError, InsufficientRestError, TransitionError
from ocura.domain.schedule import BreakSchedule


class TimerState(StrEnum):
    IDLE = "idle"
    FOCUSING = "focusing"
    BREAK_DUE = "break_due"
    ON_BREAK = "on_break"
    PAUSED = "paused"
    DEFERRED = "deferred"


#: DEFERRED is the owed break itself, postponed to a retry deadline. There is no
#: flag anywhere saying a break is owed; these two states are that statement.
_BREAK_OWED = frozenset({TimerState.BREAK_DUE, TimerState.DEFERRED})

#: Time at the screen keeps counting while a break goes untaken, so focus_elapsed
#: stays honest about the real stretch rather than freezing at the interval.
_FOCUS_ACCRUING = frozenset({TimerState.FOCUSING, *_BREAK_OWED})

#: The user may ask for a break from any state where they are at the screen. Kept
#: separate from _FOCUS_ACCRUING despite matching it today: one is about counting
#: time, this is about who is allowed to ask.
_USER_MAY_TAKE_BREAK = frozenset({TimerState.FOCUSING, *_BREAK_OWED})


class _Stopwatch:
    """Banked seconds plus, when running, the seconds since the last monotonic reading."""

    __slots__ = ("_banked", "_started_at")

    def __init__(self) -> None:
        self._banked = 0.0
        self._started_at: float | None = None

    @property
    def running(self) -> bool:
        return self._started_at is not None

    def elapsed(self, now: float) -> float:
        if self._started_at is None:
            return self._banked
        return self._banked + (now - self._started_at)

    def set_running(self, running: bool, now: float) -> None:
        if running == self.running:
            return
        if running:
            self._started_at = now
        else:
            self._banked = self.elapsed(now)
            self._started_at = None

    def reset(self) -> None:
        self._banked = 0.0
        self._started_at = None


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    state: TimerState
    focus_elapsed: float
    focus_remaining: float
    break_remaining: float
    deferral_remaining: float

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
        self._focus = _Stopwatch()
        self._break = _Stopwatch()
        self._deferral = _Stopwatch()

    @property
    def schedule(self) -> BreakSchedule:
        return self._schedule

    @property
    def state(self) -> TimerState:
        return self._state

    # --- commands ---------------------------------------------------------

    def start(self) -> None:
        """Begin (or restart) a focus block from zero."""
        self._resume_state = None
        self._retry_after = None
        self._start_focus_block(self._clock.monotonic())

    def reset(self) -> None:
        now = self._clock.monotonic()
        self._resume_state = None
        self._retry_after = None
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

    def tick(self) -> TimerState:
        """Apply whatever the passage of time has made true. Safe to call at any rate."""
        now = self._clock.monotonic()
        match self._state:
            case TimerState.FOCUSING if self._focus.elapsed(now) >= self._schedule.focus_interval:
                self._enter(TimerState.BREAK_DUE, now)
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
        )

    # --- internals --------------------------------------------------------

    @property
    def _retry_deadline(self) -> float:
        if self._retry_after is None:
            return self._schedule.defer_interval
        return self._retry_after

    def _start_focus_block(self, now: float) -> None:
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
        self._focus.set_running(state in _FOCUS_ACCRUING, now)
        self._break.set_running(state is TimerState.ON_BREAK, now)
        self._deferral.set_running(state is TimerState.DEFERRED, now)
