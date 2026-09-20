from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ocura.domain.context import ContextAssessment, Interruptible
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import BreakTimer, TimerSnapshot

#: The language rule, in one place because it applies to every surface Ocura
#: has. Ocura reports what happened and never grades it: there is no target to
#: fall short of, so there is nothing to have missed and nothing to keep up.
#:
#: Shared by the dashboard's `test_no_event_text_is_accusatory` and the
#: statistics page's, because a rule enforced on one screen and not the other
#: is a rule the next screen will quietly break.
ACCUSATORY_WORDS = (
    "missed",
    "failed",
    "should",
    "streak",
    "skipped",
    "overdue",
    "too long",
    "goal",
    "target",
    "achieved",
    "on track",
    "behind",
    "well done",
)


class FakeMonotonicClock:
    """Time moves only when a test says so, so nothing here ever sleeps."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise AssertionError("a monotonic clock cannot go backwards")
        self._now += seconds
        return self._now


class FakeWallClock:
    """Calendar time that can jump forwards or backwards, exactly like a real one."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 9, 30, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def jump(self, delta: timedelta) -> None:
        self._now += delta


class ScriptedContext:
    """Replays a queued list of assessments; falls back to Interruptible."""

    def __init__(self, *assessments: ContextAssessment) -> None:
        self.queue = list(assessments)
        self.calls: list[TimerSnapshot] = []

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        self.calls.append(snapshot)
        if not self.queue:
            return Interruptible()
        return self.queue.pop(0)


@pytest.fixture
def schedule() -> BreakSchedule:
    return BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=300.0)


@pytest.fixture
def clock() -> FakeMonotonicClock:
    return FakeMonotonicClock()


@pytest.fixture
def wall_clock() -> FakeWallClock:
    return FakeWallClock()


@pytest.fixture
def timer(schedule: BreakSchedule, clock: FakeMonotonicClock) -> BreakTimer:
    return BreakTimer(schedule, clock)


@pytest.fixture
def due_timer(timer: BreakTimer, clock: FakeMonotonicClock) -> BreakTimer:
    """A timer parked in BREAK_DUE, the entry point for both context outcomes."""
    timer.start()
    clock.advance(timer.schedule.focus_interval)
    timer.tick()
    return timer


@pytest.fixture
def timer_for(schedule: BreakSchedule, clock: FakeMonotonicClock):
    """A timer parked in a requested state, for tests that care about one."""
    from ocura.domain.timer import TimerState

    def build(state: TimerState) -> BreakTimer:
        timer = BreakTimer(schedule, clock)
        if state is TimerState.IDLE:
            return timer
        timer.start()
        if state is TimerState.FOCUSING:
            return timer
        clock.advance(schedule.focus_interval - schedule.pre_break_warning)
        timer.tick()
        if state is TimerState.PRE_BREAK:
            return timer
        clock.advance(schedule.pre_break_warning)
        timer.tick()
        if state is TimerState.BREAK_DUE:
            return timer
        if state is TimerState.ON_BREAK:
            timer.begin_break()
            return timer
        if state is TimerState.DEFERRED:
            timer.defer()
            return timer
        if state is TimerState.PAUSED:
            timer.pause()
            return timer
        raise AssertionError(f"no recipe for {state}")

    return build
