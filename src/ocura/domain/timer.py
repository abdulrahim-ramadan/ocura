from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ocura.domain.clock import MonotonicClock
from ocura.domain.errors import TransitionError
from ocura.domain.schedule import BreakSchedule


class TimerState(StrEnum):
    IDLE = "idle"
    FOCUSING = "focusing"
    BREAK_DUE = "break_due"
    ON_BREAK = "on_break"
    PAUSED = "paused"
    DEFERRED = "deferred"


#: DEFERRED is the focusing state carrying an owed break: the user kept working
#: because the moment was wrong, and the break becomes due again after
#: defer_interval rather than after a whole fresh focus block.
_FOCUS_ACCRUING = frozenset({TimerState.FOCUSING, TimerState.BREAK_DUE, TimerState.DEFERRED})


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

    def reset(self, now: float, *, running: bool = False) -> None:
        self._banked = 0.0
        self._started_at = now if running else None


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    state: TimerState
    break_owed: bool
    focus_elapsed: float
    focus_remaining: float
    break_remaining: float
    deferral_remaining: float


class BreakTimer:
    """The break state machine. Its only contact with time is the monotonic clock."""

    def __init__(self, schedule: BreakSchedule, clock: MonotonicClock) -> None:
        self._schedule = schedule
        self._clock = clock
        self._state = TimerState.IDLE
        self._break_owed = False
        self._resume_state: TimerState | None = None
        self._focus = _Stopwatch()
        self._break = _Stopwatch()
        self._deferral = _Stopwatch()
        self._defer_interval = schedule.defer_interval

    @property
    def schedule(self) -> BreakSchedule:
        return self._schedule

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def break_owed(self) -> bool:
        return self._break_owed

    # --- commands ---------------------------------------------------------

    def start(self) -> None:
        """Begin (or restart) a focus block from zero."""
        now = self._clock.monotonic()
        self._break_owed = False
        self._resume_state = None
        self._reset_all(now)
        self._enter(TimerState.FOCUSING, now)

    def reset(self) -> None:
        now = self._clock.monotonic()
        self._break_owed = False
        self._resume_state = None
        self._reset_all(now)
        self._enter(TimerState.IDLE, now)

    def begin_break(self) -> None:
        if self._state not in (TimerState.BREAK_DUE, TimerState.DEFERRED, TimerState.FOCUSING):
            raise TransitionError(f"cannot begin a break from {self._state}")
        now = self._clock.monotonic()
        self._break_owed = True
        self._break.reset(now)
        self._enter(TimerState.ON_BREAK, now)

    def complete_break(self) -> None:
        """Break taken. Ending early is allowed; Ocura does not force breaks."""
        if self._state is not TimerState.ON_BREAK:
            raise TransitionError(f"cannot complete a break from {self._state}")
        self._discharge(self._clock.monotonic())

    def defer(self) -> None:
        """Wrong moment. Keep working, keep the break owed, ask again shortly."""
        if self._state is not TimerState.BREAK_DUE:
            raise TransitionError(f"cannot defer from {self._state}")
        now = self._clock.monotonic()
        self._break_owed = True
        self._deferral.reset(now)
        self._enter(TimerState.DEFERRED, now)

    def satisfy_break(self) -> None:
        """The user genuinely rested away from the screen. The owed break is paid."""
        if self._state not in _FOCUS_ACCRUING:
            raise TransitionError(f"cannot satisfy a break from {self._state}")
        self._discharge(self._clock.monotonic())

    def set_defer_interval(self, seconds: float) -> None:
        """A detector may know a better moment to ask again than the schedule default.

        Lasts until the next discharge, then falls back to the schedule.
        """
        if seconds <= 0:
            raise ConfigurationError(f"defer interval must be positive, got {seconds}")
        self._defer_interval = seconds

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
                self._break_owed = True
                self._enter(TimerState.BREAK_DUE, now)
            case TimerState.DEFERRED if self._deferral.elapsed(now) >= self._defer_interval:
                self._enter(TimerState.BREAK_DUE, now)
            case TimerState.ON_BREAK if self._break.elapsed(now) >= self._schedule.break_duration:
                self._discharge(now)
            case _:
                pass
        return self._state

    # --- observation ------------------------------------------------------

    def snapshot(self) -> TimerSnapshot:
        now = self._clock.monotonic()
        focus_elapsed = self._focus.elapsed(now)
        return TimerSnapshot(
            state=self._state,
            break_owed=self._break_owed,
            focus_elapsed=focus_elapsed,
            focus_remaining=max(0.0, self._schedule.focus_interval - focus_elapsed),
            break_remaining=(
                max(0.0, self._schedule.break_duration - self._break.elapsed(now))
                if self._state is TimerState.ON_BREAK
                else 0.0
            ),
            deferral_remaining=(
                max(0.0, self._defer_interval - self._deferral.elapsed(now))
                if self._state is TimerState.DEFERRED
                else 0.0
            ),
        )

    # --- internals --------------------------------------------------------

    def _discharge(self, now: float) -> None:
        self._break_owed = False
        self._reset_all(now)
        self._enter(TimerState.FOCUSING, now)
        self._defer_interval = self._schedule.defer_interval

    def _reset_all(self, now: float) -> None:
        self._focus.reset(now)
        self._break.reset(now)
        self._deferral.reset(now)

    def _enter(self, state: TimerState, now: float) -> None:
        self._state = state
        # One place decides which stopwatches run in which state, so pause and
        # resume cannot drift apart from the transitions.
        self._focus.set_running(state in _FOCUS_ACCRUING, now)
        self._break.set_running(state is TimerState.ON_BREAK, now)
        self._deferral.set_running(state is TimerState.DEFERRED, now)
