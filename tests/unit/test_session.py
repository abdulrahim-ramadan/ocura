from __future__ import annotations

from datetime import timedelta

import pytest

from ocura.application.session import BreakSession, SessionEventKind
from ocura.domain.context import Deferral, RestSatisfied
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


def test_pause_and_resume_emit_events(session: BreakSession, clock: FakeMonotonicClock):
    session.start()
    clock.advance(120.0)
    assert session.pause().kind is SessionEventKind.PAUSED

    clock.advance(9999.0)
    assert session.tick() == []
    assert session.resume().kind is SessionEventKind.RESUMED
    assert session.snapshot().focus_elapsed == 120.0
