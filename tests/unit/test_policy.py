from __future__ import annotations

from ocura.domain.context import Deferral, Interruptible, RestSatisfied
from ocura.domain.policy import (
    BreakDeferred,
    BreakPolicy,
    BreakSatisfied,
    BreakStarted,
    NoAction,
)
from ocura.domain.timer import BreakTimer, TimerState

from .conftest import FakeMonotonicClock


def test_interruptible_starts_the_break(due_timer: BreakTimer):
    outcome = BreakPolicy().resolve(due_timer, Interruptible())
    assert isinstance(outcome, BreakStarted)
    assert due_timer.state is TimerState.ON_BREAK


def test_deferral_and_satisfaction_are_different_outcomes(
    due_timer: BreakTimer, timer: BreakTimer, clock: FakeMonotonicClock
):
    deferred = BreakPolicy().resolve(due_timer, Deferral(reason="fullscreen"))
    assert isinstance(deferred, BreakDeferred)
    assert due_timer.state is TimerState.DEFERRED
    assert due_timer.snapshot().break_owed is True

    timer.start()
    clock.advance(timer.schedule.focus_interval)
    timer.tick()
    satisfied = BreakPolicy().resolve(timer, RestSatisfied(reason="locked", rested_for=600.0))
    assert isinstance(satisfied, BreakSatisfied)
    assert timer.state is TimerState.FOCUSING
    assert timer.snapshot().break_owed is False


def test_deferral_carries_its_retry_after_to_the_timer(due_timer: BreakTimer):
    outcome = BreakPolicy().resolve(due_timer, Deferral(reason="call", retry_after=120.0))
    assert outcome == BreakDeferred(reason="call", retry_after=120.0)
    assert due_timer.snapshot().deferral_remaining == 120.0


def test_rest_during_a_deferral_still_satisfies(due_timer: BreakTimer):
    due_timer.defer()
    outcome = BreakPolicy().resolve(due_timer, RestSatisfied(reason="locked", rested_for=900.0))
    assert isinstance(outcome, BreakSatisfied)
    assert due_timer.state is TimerState.FOCUSING


def test_deferred_ignores_everything_but_rest(due_timer: BreakTimer):
    due_timer.defer()
    outcome = BreakPolicy().resolve(due_timer, Interruptible())
    assert isinstance(outcome, NoAction)
    assert due_timer.state is TimerState.DEFERRED


def test_too_short_a_rest_changes_nothing(due_timer: BreakTimer):
    short = due_timer.schedule.break_duration / 2
    outcome = BreakPolicy().resolve(due_timer, RestSatisfied(reason="blink", rested_for=short))
    assert isinstance(outcome, NoAction)
    assert due_timer.state is TimerState.BREAK_DUE
    assert due_timer.snapshot().break_owed is True


def test_context_is_ignored_while_no_break_is_owed(timer: BreakTimer):
    timer.start()
    outcome = BreakPolicy().resolve(timer, RestSatisfied(reason="locked", rested_for=900.0))
    assert isinstance(outcome, NoAction)
    assert timer.state is TimerState.FOCUSING
