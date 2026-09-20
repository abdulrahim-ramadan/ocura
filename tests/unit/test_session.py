from __future__ import annotations

from datetime import timedelta

import pytest

from ocura.application.session import BreakSession, SessionEvent, SessionEventKind
from ocura.domain.context import Deferral, RestSatisfied
from ocura.domain.errors import TransitionError
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerState

from .conftest import FakeMonotonicClock, FakeWallClock, ScriptedContext


@pytest.fixture
def context() -> ScriptedContext:
    return ScriptedContext()


@pytest.fixture
def session(
    schedule: BreakSchedule,
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
) -> BreakSession:
    return BreakSession(schedule, clock, wall_clock, context)


def test_events_are_stamped_with_calendar_time(session: BreakSession, wall_clock: FakeWallClock):
    event = session.start()
    assert event.kind is SessionEventKind.STARTED
    assert event.at == wall_clock.now()

    wall_clock.jump(timedelta(hours=1))
    assert session.stop().at == wall_clock.now()


def test_break_due_then_started_without_detectors(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    session.start()
    clock.advance(schedule.focus_interval)

    kinds = [event.kind for event in session.tick()]
    assert kinds == [SessionEventKind.BREAK_DUE, SessionEventKind.BREAK_STARTED]
    assert session.state is TimerState.ON_BREAK

    clock.advance(schedule.break_duration)
    assert [event.kind for event in session.tick()] == [SessionEventKind.BREAK_COMPLETED]
    assert session.state is TimerState.FOCUSING


def test_deferral_reports_its_reason(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen"))
    session.start()
    clock.advance(schedule.focus_interval)

    events = session.tick()
    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_DEFERRED,
    ]
    assert events[-1].detail == "fullscreen"
    assert session.snapshot().break_owed is True


def test_satisfaction_discharges_the_owed_break(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(RestSatisfied(reason="session locked", rested_for=1800.0))
    session.start()
    clock.advance(schedule.focus_interval)

    events = session.tick()
    # break_due is announced even though the break is discharged on the same tick;
    # P3 opens the overlay on break_started, never on break_due.
    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_SATISFIED,
    ]
    assert events[-1].detail == "session locked"
    assert session.state is TimerState.FOCUSING
    assert session.snapshot().focus_elapsed == 0.0


def test_rest_at_the_retry_deadline_satisfies_in_one_tick(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen"))
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()

    # DEFERRED -> BREAK_DUE by the deadline, then BREAK_DUE -> FOCUSING by the rest.
    context.queue.append(RestSatisfied(reason="session locked", rested_for=900.0))
    clock.advance(schedule.defer_interval)
    events = session.tick()

    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_SATISFIED,
    ]
    assert session.state is TimerState.FOCUSING
    assert session.snapshot().focus_elapsed == 0.0


def test_still_unsuitable_at_the_retry_deadline_defers_again(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen"))
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()

    context.queue.append(Deferral(reason="still fullscreen", retry_after=60.0))
    clock.advance(schedule.defer_interval)
    events = session.tick()

    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_DEFERRED,
    ]
    assert session.state is TimerState.DEFERRED
    assert session.snapshot().deferral_remaining == 60.0


def test_the_context_source_is_consulted_once_per_tick(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen"))
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()
    assert len(context.calls) == 1

    clock.advance(schedule.defer_interval)
    session.tick()
    assert len(context.calls) == 2


def test_detectors_are_left_alone_while_focusing(
    session: BreakSession, clock: FakeMonotonicClock, context: ScriptedContext
):
    session.start()
    clock.advance(60.0)
    session.tick()
    assert context.calls == []


def test_a_deferral_in_flight_emits_nothing_until_the_deadline(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen"))
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()

    clock.advance(schedule.defer_interval / 2)
    assert session.tick() == []
    assert session.state is TimerState.DEFERRED

    clock.advance(schedule.defer_interval / 2)
    kinds = [event.kind for event in session.tick()]
    assert kinds == [SessionEventKind.BREAK_DUE, SessionEventKind.BREAK_STARTED]


def test_skip_break_ends_it_early_and_resets_focus(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()
    assert session.state is TimerState.ON_BREAK

    clock.advance(schedule.break_duration / 3)
    event = session.skip_break()
    # Not BREAK_COMPLETED. A break the user ended after a third of it is a
    # different fact from one that ran out, and the log is the one place that
    # difference is kept — see the note on the kind itself.
    assert event.kind is SessionEventKind.BREAK_SKIPPED
    assert event.duration == schedule.break_duration / 3
    assert session.state is TimerState.FOCUSING
    assert session.snapshot().focus_elapsed == 0.0


def test_skip_break_rejected_when_not_on_a_break(session: BreakSession):
    session.start()
    with pytest.raises(TransitionError):
        session.skip_break()


def test_pause_and_resume_emit_events(session: BreakSession, clock: FakeMonotonicClock):
    session.start()
    clock.advance(120.0)
    assert session.pause().kind is SessionEventKind.PAUSED

    clock.advance(9999.0)
    assert session.tick() == []
    assert session.resume().kind is SessionEventKind.RESUMED
    assert session.snapshot().focus_elapsed == 120.0


# --- durations -------------------------------------------------------------
#
# Every event about a span of time carries that span, because the questions the
# testers' feedback will raise are all of the form "how long". A kind with no
# duration attached is a row that can be counted and not measured.


def only(events: list[SessionEvent], kind: SessionEventKind) -> SessionEvent:
    matching = [event for event in events if event.kind is kind]
    assert len(matching) == 1, f"expected exactly one {kind}, got {[e.kind for e in events]}"
    return matching[0]


def test_an_offer_carries_the_stretch_at_the_screen_that_earned_it(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    session.start()
    clock.advance(schedule.focus_interval)

    assert only(session.tick(), SessionEventKind.BREAK_DUE).duration == schedule.focus_interval


def test_an_offer_after_a_deferral_carries_the_longer_stretch_it_really_was(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    """The scheduled interval and the time actually spent at the screen differ
    the moment anything postpones a break, and the second one is the fact."""
    context.queue.append(Deferral(reason="a call is running", retry_after=None))
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()
    assert session.state is TimerState.DEFERRED

    clock.advance(schedule.defer_interval)
    offered = only(session.tick(), SessionEventKind.BREAK_DUE)

    assert offered.duration == schedule.focus_interval + schedule.defer_interval


def test_a_break_that_ran_out_carries_how_long_it_lasted(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()

    clock.advance(schedule.break_duration)
    completed = only(session.tick(), SessionEventKind.BREAK_COMPLETED)

    assert completed.duration == schedule.break_duration


def test_a_break_ended_early_carries_the_shorter_time_it_actually_lasted(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """The number the whole distinction exists for: a twenty-second break that
    was three seconds long is not a twenty-second break."""
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()

    clock.advance(3.0)
    skipped = session.skip_break()

    assert skipped.kind is SessionEventKind.BREAK_SKIPPED
    assert skipped.duration == 3.0


def test_a_deferral_carries_how_long_it_postpones_the_break_for(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="a call is running", retry_after=None))
    session.start()
    clock.advance(schedule.focus_interval)

    deferred = only(session.tick(), SessionEventKind.BREAK_DEFERRED)
    assert deferred.duration == schedule.defer_interval
    assert deferred.detail == "a call is running"


def test_a_detector_that_names_its_own_retry_is_the_duration_recorded(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    """Read off the timer rather than off the schedule, so an override lands."""
    context.queue.append(Deferral(reason="presenting", retry_after=90.0))
    session.start()
    clock.advance(schedule.focus_interval)

    assert only(session.tick(), SessionEventKind.BREAK_DEFERRED).duration == 90.0


def test_a_snooze_carries_the_snooze_interval(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    session.start()
    clock.advance(schedule.focus_interval - schedule.pre_break_warning)
    session.tick()

    snoozed = session.snooze()
    assert snoozed.kind is SessionEventKind.BREAK_SNOOZED
    assert snoozed.duration == schedule.snooze_interval


def test_a_rest_that_discharged_a_break_carries_how_long_the_rest_was(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    rested_for = schedule.break_duration * 4
    context.queue.append(RestSatisfied(reason="the session was locked", rested_for=rested_for))
    session.start()
    clock.advance(schedule.focus_interval)

    satisfied = only(session.tick(), SessionEventKind.BREAK_SATISFIED)
    assert satisfied.duration == rested_for
    assert satisfied.detail == "the session was locked"


def test_events_that_are_not_about_a_span_of_time_carry_no_duration(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """None, not zero. Nothing was measured, which is not a measurement of nothing."""
    assert session.start().duration is None
    clock.advance(schedule.focus_interval)
    session.tick()

    assert session.state is TimerState.ON_BREAK
    assert session.pause().duration is None
    assert session.resume().duration is None
    assert session.stop().duration is None


def test_a_user_initiated_break_is_its_own_kind_and_starts_unmeasured(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """A break that has just begun has no duration yet; the one that ends it does."""
    session.start()
    clock.advance(60.0)

    started = session.take_break_now()
    assert started.kind is SessionEventKind.BREAK_STARTED_BY_USER
    assert started.duration is None
