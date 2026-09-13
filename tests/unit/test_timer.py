from __future__ import annotations

import math
from datetime import timedelta

import pytest

from ocura.domain.errors import ConfigurationError, InsufficientRestError, TransitionError
from ocura.domain.timer import BreakTimer, TimerState

from .conftest import FakeMonotonicClock, FakeWallClock


def test_starts_idle(timer: BreakTimer):
    assert timer.state is TimerState.IDLE
    assert timer.snapshot().break_owed is False


def test_start_enters_focusing_at_zero(timer: BreakTimer):
    timer.start()
    snapshot = timer.snapshot()
    assert timer.state is TimerState.FOCUSING
    assert snapshot.focus_elapsed == 0.0
    assert snapshot.focus_remaining == timer.schedule.focus_interval


def test_elapsed_is_deterministic(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(137.5)
    assert timer.snapshot().focus_elapsed == 137.5
    clock.advance(2.5)
    assert timer.snapshot().focus_elapsed == 140.0


def test_break_due_fires_at_exactly_the_configured_duration(
    timer: BreakTimer, clock: FakeMonotonicClock
):
    timer.start()
    clock.advance(timer.schedule.focus_interval - 0.001)
    # PRE_BREAK by now, but the break itself is not owed a moment early.
    assert timer.tick() is not TimerState.BREAK_DUE
    assert timer.snapshot().break_owed is False

    clock.advance(0.001)
    assert timer.tick() is TimerState.BREAK_DUE
    assert timer.snapshot().break_owed is True


def test_the_warning_fires_exactly_one_warning_period_early(
    timer: BreakTimer, clock: FakeMonotonicClock
):
    warning_at = timer.schedule.focus_interval - timer.schedule.pre_break_warning
    timer.start()

    clock.advance(warning_at - 0.001)
    assert timer.tick() is TimerState.FOCUSING

    clock.advance(0.001)
    assert timer.tick() is TimerState.PRE_BREAK
    # Still focusing as far as the count is concerned; nothing is owed yet.
    assert timer.snapshot().break_owed is False


def test_the_warning_state_keeps_accruing_focus(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(timer.schedule.focus_interval - timer.schedule.pre_break_warning)
    timer.tick()
    clock.advance(10.0)

    assert timer.state is TimerState.PRE_BREAK
    assert timer.snapshot().focus_elapsed == (
        timer.schedule.focus_interval - timer.schedule.pre_break_warning + 10.0
    )


def test_a_pause_during_the_warning_resumes_into_it(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(timer.schedule.focus_interval - timer.schedule.pre_break_warning)
    timer.tick()

    timer.pause()
    clock.advance(9999.0)
    timer.resume()
    assert timer.state is TimerState.PRE_BREAK


def test_a_long_stall_goes_straight_past_the_warning(timer: BreakTimer, clock: FakeMonotonicClock):
    """A machine asleep through the whole block should not stop to warn first."""
    timer.start()
    clock.advance(timer.schedule.focus_interval * 3)
    assert timer.tick() is TimerState.BREAK_DUE


def test_focus_keeps_accruing_while_a_break_goes_untaken(
    timer: BreakTimer, clock: FakeMonotonicClock
):
    timer.start()
    clock.advance(timer.schedule.focus_interval)
    timer.tick()
    clock.advance(60.0)

    snapshot = timer.snapshot()
    assert snapshot.focus_elapsed == timer.schedule.focus_interval + 60.0
    assert snapshot.focus_remaining == 0.0


def test_break_counts_down_and_completes(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.begin_break()
    assert due_timer.snapshot().break_remaining == due_timer.schedule.break_duration

    clock.advance(10.0)
    assert due_timer.snapshot().break_remaining == due_timer.schedule.break_duration - 10.0
    assert due_timer.tick() is TimerState.ON_BREAK

    clock.advance(due_timer.schedule.break_duration - 10.0)
    assert due_timer.tick() is TimerState.FOCUSING


def test_completed_break_resets_focus_accumulation(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    due_timer.begin_break()
    clock.advance(due_timer.schedule.break_duration)
    due_timer.tick()

    snapshot = due_timer.snapshot()
    assert snapshot.focus_elapsed == 0.0
    assert snapshot.break_owed is False


def test_break_can_be_completed_early(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.begin_break()
    clock.advance(5.0)
    due_timer.complete_break()
    assert due_timer.state is TimerState.FOCUSING
    assert due_timer.snapshot().focus_elapsed == 0.0


def test_pause_freezes_progress(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(300.0)
    timer.pause()

    clock.advance(9999.0)
    assert timer.state is TimerState.PAUSED
    assert timer.snapshot().focus_elapsed == 300.0
    assert timer.tick() is TimerState.PAUSED


def test_resume_continues_from_the_frozen_value(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(300.0)
    timer.pause()
    clock.advance(9999.0)
    timer.resume()

    assert timer.state is TimerState.FOCUSING
    assert timer.snapshot().focus_elapsed == 300.0
    clock.advance(100.0)
    assert timer.snapshot().focus_elapsed == 400.0


@pytest.mark.parametrize("state", [TimerState.BREAK_DUE, TimerState.ON_BREAK, TimerState.DEFERRED])
def test_resume_restores_the_exact_prior_state(
    due_timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    if state is TimerState.ON_BREAK:
        due_timer.begin_break()
    elif state is TimerState.DEFERRED:
        due_timer.defer()
    assert due_timer.state is state

    due_timer.pause()
    clock.advance(5000.0)
    due_timer.resume()
    assert due_timer.state is state


def test_pause_freezes_the_break_countdown(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.begin_break()
    clock.advance(10.0)
    due_timer.pause()
    clock.advance(9999.0)
    due_timer.resume()

    assert due_timer.state is TimerState.ON_BREAK
    assert due_timer.snapshot().break_remaining == due_timer.schedule.break_duration - 10.0


def test_defer_enters_deferred_and_keeps_the_break_owed(due_timer: BreakTimer):
    due_timer.defer()
    snapshot = due_timer.snapshot()
    assert due_timer.state is TimerState.DEFERRED
    assert snapshot.break_owed is True
    assert snapshot.deferral_remaining == due_timer.schedule.defer_interval


def test_retry_deadline_returns_deferred_to_break_due(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    due_timer.defer()
    clock.advance(due_timer.schedule.defer_interval - 0.001)
    assert due_timer.tick() is TimerState.DEFERRED

    clock.advance(0.001)
    assert due_timer.tick() is TimerState.BREAK_DUE
    assert due_timer.snapshot().break_owed is True


def test_deferral_does_not_reset_focus_accumulation(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    before = due_timer.snapshot().focus_elapsed
    due_timer.defer()
    clock.advance(60.0)
    assert due_timer.snapshot().focus_elapsed == before + 60.0


def test_retry_after_overrides_the_schedule(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.defer(retry_after=90.0)
    assert due_timer.snapshot().deferral_remaining == 90.0

    clock.advance(90.0)
    assert due_timer.tick() is TimerState.BREAK_DUE


def test_retry_after_applies_to_one_deferral_only(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.defer(retry_after=90.0)
    clock.advance(90.0)
    due_timer.tick()

    due_timer.defer()
    assert due_timer.snapshot().deferral_remaining == due_timer.schedule.defer_interval


@pytest.mark.parametrize("value", [0, -30.0, math.nan, math.inf])
def test_invalid_retry_after_rejected(due_timer: BreakTimer, value):
    with pytest.raises(ConfigurationError):
        due_timer.defer(retry_after=value)


def test_satisfaction_from_break_due_discharges_and_resets(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    due_timer.satisfy_break(due_timer.schedule.break_duration)

    snapshot = due_timer.snapshot()
    assert due_timer.state is TimerState.FOCUSING
    assert snapshot.break_owed is False
    assert snapshot.focus_elapsed == 0.0

    clock.advance(60.0)
    assert due_timer.snapshot().focus_elapsed == 60.0


def test_satisfaction_from_deferred_discharges_and_clears_retry_after(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    due_timer.defer(retry_after=90.0)
    clock.advance(30.0)
    due_timer.satisfy_break(600.0)

    assert due_timer.state is TimerState.FOCUSING
    assert due_timer.snapshot().focus_elapsed == 0.0

    # The override died with the deferral it belonged to.
    clock.advance(due_timer.schedule.focus_interval)
    due_timer.tick()
    due_timer.defer()
    assert due_timer.snapshot().deferral_remaining == due_timer.schedule.defer_interval


@pytest.mark.parametrize(
    "state", [TimerState.IDLE, TimerState.FOCUSING, TimerState.PAUSED, TimerState.ON_BREAK]
)
def test_satisfaction_rejected_outside_an_owed_break(
    timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    if state is TimerState.FOCUSING:
        timer.start()
    elif state is TimerState.PAUSED:
        timer.start()
        timer.pause()
    elif state is TimerState.ON_BREAK:
        timer.start()
        clock.advance(timer.schedule.focus_interval)
        timer.tick()
        timer.begin_break()
    assert timer.state is state

    with pytest.raises(TransitionError):
        timer.satisfy_break(600.0)


def test_rest_shorter_than_the_break_is_insufficient(due_timer: BreakTimer):
    with pytest.raises(InsufficientRestError, match="shorter"):
        due_timer.satisfy_break(due_timer.schedule.break_duration - 0.001)


@pytest.mark.parametrize("value", [0, -1.0, math.nan, math.inf, -math.inf])
def test_non_positive_or_non_finite_rest_is_insufficient(due_timer: BreakTimer, value):
    with pytest.raises(InsufficientRestError):
        due_timer.satisfy_break(value)


def test_rest_exactly_the_break_length_is_enough(due_timer: BreakTimer):
    due_timer.satisfy_break(due_timer.schedule.break_duration)
    assert due_timer.state is TimerState.FOCUSING


@pytest.mark.parametrize(
    "state", [TimerState.IDLE, TimerState.FOCUSING, TimerState.ON_BREAK, TimerState.DEFERRED]
)
def test_begin_break_rejected_outside_break_due(
    timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    if state is not TimerState.IDLE:
        timer.start()
    if state in (TimerState.ON_BREAK, TimerState.DEFERRED):
        clock.advance(timer.schedule.focus_interval)
        timer.tick()
        if state is TimerState.ON_BREAK:
            timer.begin_break()
        else:
            timer.defer()
    assert timer.state is state

    with pytest.raises(TransitionError):
        timer.begin_break()


@pytest.mark.parametrize(
    "state", [TimerState.IDLE, TimerState.FOCUSING, TimerState.BREAK_DUE, TimerState.DEFERRED]
)
def test_complete_break_rejected_outside_on_break(
    timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    if state is not TimerState.IDLE:
        timer.start()
    if state in (TimerState.BREAK_DUE, TimerState.DEFERRED):
        clock.advance(timer.schedule.focus_interval)
        timer.tick()
    if state is TimerState.DEFERRED:
        timer.defer()
    assert timer.state is state

    with pytest.raises(TransitionError):
        timer.complete_break()


@pytest.mark.parametrize("state", [TimerState.FOCUSING, TimerState.BREAK_DUE, TimerState.DEFERRED])
def test_the_user_may_take_a_break_from_any_state_at_the_screen(
    timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    timer.start()
    if state in (TimerState.BREAK_DUE, TimerState.DEFERRED):
        clock.advance(timer.schedule.focus_interval)
        timer.tick()
    if state is TimerState.DEFERRED:
        timer.defer()
    assert timer.state is state

    timer.take_break_now()
    assert timer.state is TimerState.ON_BREAK
    assert timer.snapshot().break_remaining == timer.schedule.break_duration


@pytest.mark.parametrize("state", [TimerState.IDLE, TimerState.ON_BREAK, TimerState.PAUSED])
def test_the_user_cannot_take_a_break_they_are_already_on_or_have_stopped(
    timer: BreakTimer, clock: FakeMonotonicClock, state: TimerState
):
    if state is not TimerState.IDLE:
        timer.start()
    if state is TimerState.ON_BREAK:
        clock.advance(timer.schedule.focus_interval)
        timer.tick()
        timer.begin_break()
    if state is TimerState.PAUSED:
        timer.pause()
    assert timer.state is state

    with pytest.raises(TransitionError):
        timer.take_break_now()


def test_taking_a_break_clears_an_owed_deferral(due_timer: BreakTimer, clock: FakeMonotonicClock):
    """A break just taken is not still owed, and its retry must not outlive it."""
    due_timer.defer(retry_after=90.0)
    due_timer.take_break_now()
    clock.advance(due_timer.schedule.break_duration)
    due_timer.tick()

    assert due_timer.state is TimerState.FOCUSING
    assert due_timer.snapshot().break_owed is False
    assert due_timer.snapshot().focus_elapsed == 0.0

    # The 90s override died with the deferral rather than shortening the next one.
    clock.advance(due_timer.schedule.focus_interval)
    due_timer.tick()
    due_timer.defer()
    assert due_timer.snapshot().deferral_remaining == due_timer.schedule.defer_interval


def test_taking_a_break_early_resets_focus_when_it_completes(
    timer: BreakTimer, clock: FakeMonotonicClock
):
    timer.start()
    clock.advance(300.0)
    timer.take_break_now()
    clock.advance(timer.schedule.break_duration)

    assert timer.tick() is TimerState.FOCUSING
    assert timer.snapshot().focus_elapsed == 0.0


def test_begin_break_stays_narrow(timer: BreakTimer):
    """take_break_now is a separate command, not a widened guard on begin_break."""
    timer.start()
    with pytest.raises(TransitionError):
        timer.begin_break()


def test_defer_rejected_outside_break_due(timer: BreakTimer):
    timer.start()
    with pytest.raises(TransitionError):
        timer.defer()


@pytest.mark.parametrize("state", [TimerState.IDLE, TimerState.PAUSED])
def test_pause_rejected_when_nothing_is_running(timer: BreakTimer, state: TimerState):
    if state is TimerState.PAUSED:
        timer.start()
        timer.pause()

    with pytest.raises(TransitionError):
        timer.pause()


def test_resume_rejected_when_not_paused(timer: BreakTimer):
    timer.start()
    with pytest.raises(TransitionError):
        timer.resume()


def test_restarting_clears_everything(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.defer(retry_after=45.0)
    clock.advance(10.0)
    due_timer.start()

    snapshot = due_timer.snapshot()
    assert due_timer.state is TimerState.FOCUSING
    assert snapshot.focus_elapsed == 0.0
    assert snapshot.break_owed is False


def test_reset_returns_to_idle_and_stops_accruing(due_timer: BreakTimer, clock: FakeMonotonicClock):
    due_timer.reset()
    clock.advance(5000.0)

    snapshot = due_timer.snapshot()
    assert due_timer.state is TimerState.IDLE
    assert snapshot.focus_elapsed == 0.0
    assert snapshot.break_owed is False
    assert due_timer.tick() is TimerState.IDLE


def test_repeated_start_and_reset_is_stable(timer: BreakTimer, clock: FakeMonotonicClock):
    for _ in range(3):
        timer.start()
        clock.advance(600.0)
        assert timer.snapshot().focus_elapsed == 600.0
        timer.reset()
        assert timer.snapshot().focus_elapsed == 0.0
    assert timer.state is TimerState.IDLE


def test_wall_clock_jump_does_not_corrupt_elapsed(
    timer: BreakTimer, clock: FakeMonotonicClock, wall_clock: FakeWallClock
):
    timer.start()
    clock.advance(600.0)

    # 09:30 -> 10:15 on the calendar while only ten monotonic minutes passed.
    wall_clock.jump(timedelta(minutes=45))
    assert timer.snapshot().focus_elapsed == 600.0
    assert timer.tick() is TimerState.FOCUSING

    wall_clock.jump(timedelta(hours=-3))
    assert timer.snapshot().focus_elapsed == 600.0
    assert timer.tick() is TimerState.FOCUSING


def test_tick_is_idempotent_between_advances(timer: BreakTimer, clock: FakeMonotonicClock):
    timer.start()
    clock.advance(timer.schedule.focus_interval)
    assert timer.tick() is TimerState.BREAK_DUE
    assert timer.tick() is TimerState.BREAK_DUE
    assert timer.tick() is TimerState.BREAK_DUE
