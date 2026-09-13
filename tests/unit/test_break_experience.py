"""Warning timing, snooze cap, skip, and overlay decisions — all headless."""

from __future__ import annotations

import pytest

from ocura.application.presenter import TICK_SECONDS, BreakPresenter
from ocura.domain.errors import SnoozeLimitReached, TransitionError
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import MAX_SNOOZES, BreakTimer, TimerState

from .conftest import FakeMonotonicClock, FakeWallClock, ScriptedContext


@pytest.fixture
def schedule() -> BreakSchedule:
    return BreakSchedule(
        focus_interval=600.0,
        break_duration=20.0,
        defer_interval=120.0,
        pre_break_warning=60.0,
        snooze_interval=300.0,
    )


@pytest.fixture
def presenter(schedule, clock, wall_clock) -> BreakPresenter:
    return BreakPresenter(schedule, clock, wall_clock, ScriptedContext())


def run_for(presenter: BreakPresenter, clock: FakeMonotonicClock, seconds: float):
    view = presenter.view()
    for _ in range(int(seconds / TICK_SECONDS)):
        clock.advance(TICK_SECONDS)
        view = presenter.tick()
    return view


# --- the warning --------------------------------------------------------


def test_the_warning_appears_exactly_one_warning_period_before_the_break(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    quiet = schedule.focus_interval - schedule.pre_break_warning
    presenter.start()

    view = run_for(presenter, clock, quiet - TICK_SECONDS)
    assert view.warning_visible is False

    view = run_for(presenter, clock, TICK_SECONDS)
    assert view.warning_visible is True
    assert view.headline == "Break soon"


def test_the_warning_counts_down_to_the_break(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval - schedule.pre_break_warning)
    assert view.countdown_text == "1:00"

    view = run_for(presenter, clock, 30)
    assert view.countdown_text == "0:30"


def test_the_warning_clears_when_the_break_arrives(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)

    assert view.warning_visible is False
    assert view.overlay_visible is True


# --- the overlay --------------------------------------------------------


def test_the_overlay_opens_on_the_break_and_not_before(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    for seconds in (0, schedule.focus_interval - schedule.pre_break_warning):
        view = run_for(presenter, clock, seconds)
        assert view.overlay_visible is False

    view = run_for(presenter, clock, schedule.pre_break_warning)
    assert view.state is TimerState.ON_BREAK
    assert view.overlay_visible is True


def test_the_overlay_closes_when_the_break_ends(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    view = run_for(presenter, clock, schedule.break_duration)

    assert view.overlay_visible is False
    assert view.breaks_taken == 1


def test_a_deferred_break_never_opens_the_overlay(
    clock: FakeMonotonicClock, wall_clock: FakeWallClock, schedule: BreakSchedule
):
    """break_due is a decision point. Only ON_BREAK puts a screen up."""
    from ocura.domain.context import Deferral

    context = ScriptedContext(Deferral(reason="fullscreen or presenting"))
    presenter = BreakPresenter(schedule, clock, wall_clock, context)
    presenter.start()

    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.state is TimerState.DEFERRED
    assert view.overlay_visible is False


# --- skip ----------------------------------------------------------------


def test_skip_ends_the_break_immediately(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)

    view = presenter.skip_break()
    assert view.state is TimerState.FOCUSING
    assert view.overlay_visible is False
    assert view.focus_elapsed == 0.0


def test_skipping_says_nothing_about_having_skipped(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    view = presenter.skip_break()

    words = " ".join(line.text for line in view.events).lower()
    for bad in ("skipped", "missed", "cut short", "failed"):
        assert bad not in words


def test_skip_outside_a_break_does_nothing(presenter: BreakPresenter):
    presenter.start()
    assert presenter.skip_break().state is TimerState.FOCUSING


# --- snooze --------------------------------------------------------------


def test_snooze_postpones_the_break_and_keeps_it_owed(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)

    view = presenter.snooze()
    assert view.state is TimerState.DEFERRED
    assert view.break_owed is True
    assert view.overlay_visible is False
    assert view.events[-1].text == "Break postponed"


def test_the_snooze_uses_the_snooze_interval_not_the_detector_retry(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    view = presenter.snooze()

    assert view.state is TimerState.DEFERRED
    run_for(presenter, clock, schedule.snooze_interval - TICK_SECONDS)
    assert presenter.view().break_owed is True


@pytest.mark.parametrize("state", [TimerState.PRE_BREAK, TimerState.BREAK_DUE, TimerState.ON_BREAK])
def test_the_user_can_postpone_from_the_warning_the_offer_or_the_break(
    timer_for, state: TimerState
):
    timer = timer_for(state)
    assert timer.can_snooze is True

    timer.snooze()
    assert timer.state is TimerState.DEFERRED


def test_the_cap_is_two_consecutive_postponements(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)

    for expected in range(1, MAX_SNOOZES + 1):
        view = presenter.snooze()
        assert view.snoozes_used == expected
        run_for(presenter, clock, schedule.snooze_interval)

    # The break arrives and this time it cannot be postponed again.
    view = presenter.view()
    assert view.state is TimerState.ON_BREAK
    assert view.can_snooze is False


def test_past_the_cap_the_break_is_offered_but_not_forced(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """Not postponable a third time is not the same as compulsory."""
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    for _ in range(MAX_SNOOZES):
        presenter.snooze()
        run_for(presenter, clock, schedule.snooze_interval)

    assert presenter.view().can_snooze is False
    # Still refusable: the user can take it and end it whenever they like.
    view = presenter.take_break_now()
    assert view.state is TimerState.ON_BREAK
    assert presenter.skip_break().state is TimerState.FOCUSING


def test_a_break_actually_taken_clears_the_run_of_snoozes(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """The cap is on consecutive postponements, not on a whole day of them."""
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    presenter.snooze()
    assert presenter.view().snoozes_used == 1

    # The postponed break arrives and is taken in full.
    run_for(presenter, clock, schedule.snooze_interval)
    view = run_for(presenter, clock, schedule.break_duration)
    assert view.state is TimerState.FOCUSING
    assert view.snoozes_used == 0

    # The next break is postponable again: the cap counts a run, not a day.
    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.state is TimerState.ON_BREAK
    assert view.can_snooze is True


def test_the_presenter_refuses_a_snooze_past_the_cap_rather_than_raising(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    for _ in range(MAX_SNOOZES):
        presenter.snooze()
        run_for(presenter, clock, schedule.snooze_interval)

    before = presenter.view()
    after = presenter.snooze()
    assert after.state is before.state
    assert after.snoozes_used == MAX_SNOOZES


@pytest.mark.parametrize("state", [TimerState.IDLE, TimerState.FOCUSING, TimerState.DEFERRED])
def test_snooze_is_refused_where_there_is_nothing_to_postpone(timer_for, state: TimerState):
    timer = timer_for(state)
    with pytest.raises(TransitionError):
        timer.snooze()


def test_snoozing_at_the_cap_raises_the_dedicated_error(
    schedule: BreakSchedule, clock: FakeMonotonicClock
):
    timer = BreakTimer(schedule, clock)
    timer.start()
    clock.advance(schedule.focus_interval)
    timer.tick()

    for _ in range(MAX_SNOOZES):
        timer.snooze()
        clock.advance(schedule.snooze_interval)
        timer.tick()

    with pytest.raises(SnoozeLimitReached):
        timer.snooze()
