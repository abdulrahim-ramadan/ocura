from __future__ import annotations

from datetime import timedelta

import pytest

from ocura.application.session import BreakSession, SessionEvent, SessionEventKind
from ocura.domain.context import INTERRUPTIBLE, ContextAssessment, Deferral, RestSatisfied
from ocura.domain.errors import TransitionError
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerSnapshot, TimerState

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
    # The re-offer is not written: this block's break already came due once.
    context.queue.append(RestSatisfied(reason="session locked", rested_for=900.0))
    clock.advance(schedule.defer_interval)
    events = session.tick()

    assert [event.kind for event in events] == [SessionEventKind.BREAK_SATISFIED]
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

    # Staying deferred is a state, not an event: nothing is written, but the
    # new retry is honoured and the live reason is the current one.
    assert events == []
    assert session.state is TimerState.DEFERRED
    assert session.snapshot().deferral_remaining == 60.0
    assert session.deferral_reason == "still fullscreen"


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
    assert kinds == [SessionEventKind.BREAK_STARTED]


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


def test_an_offer_carries_no_duration_of_its_own(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """The block is measured once, when it closes, not at the offer."""
    session.start()
    clock.advance(schedule.focus_interval)

    offered = only(session.tick(), SessionEventKind.BREAK_DUE)
    assert offered.duration is None
    assert offered.focus is None


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


# --- once per occurrence, and blocks measured when they close -----------------
#
# The patterns below are taken from a real database (build\real-profile, never
# committed): a break re-offered and deferred every thirty seconds while the
# user was away, an absence of 57 hours, a sleep, and a handful of fullscreen
# deferrals that the idle ones buried. Together they summed into a statistics
# page that said 627 hours at the screen in one day, and 725 reasons for
# waiting where there had been a few.

THRESHOLD = 120.0
RETRY = 30.0


class Desk:
    """A user at a machine: when they last touched it, and what is on screen.

    Answers the way the real detectors do — idle past the threshold defers with
    a thirty-second retry, fullscreen defers — so the session meets the same
    re-offer loop it met in production.
    """

    def __init__(self, clock: FakeMonotonicClock) -> None:
        self.clock = clock
        self.last_input = clock.monotonic()
        self.fullscreen = False

    def touch(self) -> None:
        self.last_input = self.clock.monotonic()

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        idle = self.clock.monotonic() - self.last_input
        if idle >= THRESHOLD:
            return Deferral(reason=f"idle for {idle:.0f}s", retry_after=RETRY)
        if self.fullscreen:
            return Deferral(reason="fullscreen or presenting", retry_after=RETRY)
        return INTERRUPTIBLE


@pytest.fixture
def desk(clock: FakeMonotonicClock) -> Desk:
    return Desk(clock)


@pytest.fixture
def at_desk(
    schedule: BreakSchedule, clock: FakeMonotonicClock, wall_clock: FakeWallClock, desk: Desk
) -> BreakSession:
    return BreakSession(schedule, clock, wall_clock, desk)


def run(
    session: BreakSession,
    desk: Desk,
    clock: FakeMonotonicClock,
    seconds: float,
    *,
    working: bool,
    step: float = 1.0,
) -> list[SessionEvent]:
    """Tick as the presenter does: observe input first, then tick."""
    events: list[SessionEvent] = []
    end = clock.monotonic() + seconds
    while clock.monotonic() < end:
        clock.advance(step)
        if working:
            desk.touch()
        session.observe_input(desk.last_input, THRESHOLD)
        events += session.tick()
    return events


def kinds_of(events: list[SessionEvent]) -> list[SessionEventKind]:
    return [event.kind for event in events]


def closed_blocks(events: list[SessionEvent]) -> list[float]:
    return [event.focus for event in events if event.focus is not None]


def test_the_thirty_second_re_offer_loop_writes_one_deferral(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    at_desk.start()
    events = run(at_desk, desk, clock, schedule.focus_interval, working=True)
    assert kinds_of(events) == [SessionEventKind.BREAK_DUE, SessionEventKind.BREAK_STARTED]

    events = [at_desk.snooze()]
    # They walk away for two hours. The break is re-offered every thirty
    # seconds and deferred every time; that is the engine asking, not news.
    events += run(at_desk, desk, clock, 2 * 3600.0, working=False)

    assert kinds_of(events) == [
        SessionEventKind.BREAK_SNOOZED,
        SessionEventKind.BREAK_DEFERRED,
    ]
    assert events[-1].detail.startswith("idle for")
    assert events[-1].duration == RETRY


def test_a_57_hour_absence_is_not_57_hours_at_the_screen(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    at_desk.start()
    run(at_desk, desk, clock, schedule.focus_interval, working=True)
    at_desk.snooze()
    events = run(at_desk, desk, clock, 57 * 3600.0, working=False, step=10.0)

    assert kinds_of(events) == [SessionEventKind.BREAK_DEFERRED]
    assert at_desk.snapshot().away is True

    # Back. The owed break is offered at the next retry, and taken.
    events = run(at_desk, desk, clock, RETRY + schedule.break_duration + 2, working=True)
    assert SessionEventKind.BREAK_COMPLETED in kinds_of(events)
    (block,) = closed_blocks(events)
    # The interval, the threshold's worth of the absence (a reader's pause
    # counts), and the moments between coming back and the break starting.
    assert schedule.focus_interval + THRESHOLD <= block
    assert block <= schedule.focus_interval + THRESHOLD + RETRY + 1


def test_a_sleep_ended_by_input_is_taken_out_of_the_block(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """Measured 2026-10-30: the input that wakes the machine resets the idle
    count before Ocura ticks, so the first tick after a sleep sees almost no
    idle at all. Only the jump in the input moment shows the sleep."""
    at_desk.start()
    run(at_desk, desk, clock, 300.0, working=True)

    clock.advance(3 * 3600.0)  # asleep: no ticks at all
    desk.touch()  # the key that woke it
    clock.advance(1.9)
    woke = clock.monotonic()

    # The first tick awake must not find a break due: the sleep is not focus.
    at_desk.observe_input(desk.last_input, THRESHOLD)
    assert SessionEventKind.BREAK_DUE not in kinds_of(at_desk.tick())

    while at_desk.state is not TimerState.BREAK_DUE:
        clock.advance(1.0)
        desk.touch()
        at_desk.observe_input(desk.last_input, THRESHOLD)
        if SessionEventKind.BREAK_DUE in kinds_of(at_desk.tick()):
            break

    # 300 s before the sleep and the threshold's 120 s of it were counted; the
    # rest of the block is what was left to work after waking.
    left_after_waking = schedule.focus_interval - 300.0 - THRESHOLD
    assert clock.monotonic() - woke == pytest.approx(left_after_waking, abs=2.0)


def test_a_short_pause_for_thought_is_still_time_at_the_screen(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock
):
    at_desk.start()
    run(at_desk, desk, clock, 100.0, working=True)
    run(at_desk, desk, clock, THRESHOLD - 5.0, working=False)
    run(at_desk, desk, clock, 50.0, working=True)

    assert at_desk.snapshot().away is False
    assert at_desk.snapshot().focus_elapsed == pytest.approx(100.0 + THRESHOLD - 5.0 + 50.0)


def test_clock_wobble_does_not_end_an_absence(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock
):
    """The input moment is monotonic time minus GetLastInputInfo's count, two
    counters measured 0.02-0.05 s apart; that difference must not read as a
    return."""
    at_desk.start()
    run(at_desk, desk, clock, THRESHOLD + 10.0, working=False)
    assert at_desk.snapshot().away is True

    for wobble in (0.03, -0.02, 0.05, 0.01):
        clock.advance(1.0)
        at_desk.observe_input(desk.last_input + wobble, THRESHOLD)
        at_desk.tick()
    assert at_desk.snapshot().away is True


def test_fullscreen_deferrals_are_not_buried_by_idle_ones(
    at_desk: BreakSession, desk: Desk, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """Seven fullscreen deferrals among 8,220 idle rows was the real ratio. Each
    fullscreen deferral is one occurrence, and so is each absence."""
    events: list[SessionEvent] = []
    at_desk.start()
    for _ in range(3):
        desk.fullscreen = True
        events += run(at_desk, desk, clock, schedule.focus_interval + 5 * RETRY, working=True)
        desk.fullscreen = False
        events += run(at_desk, desk, clock, RETRY + schedule.break_duration + 2, working=True)
    for _ in range(2):
        events += run(at_desk, desk, clock, schedule.focus_interval, working=True)
        events.append(at_desk.snooze())
        events += run(at_desk, desk, clock, 3600.0, working=False, step=10.0)
        events += run(at_desk, desk, clock, RETRY + schedule.break_duration + 2, working=True)

    deferred = [e.detail for e in events if e.kind is SessionEventKind.BREAK_DEFERRED]
    assert deferred.count("fullscreen or presenting") == 3
    assert len([d for d in deferred if d.startswith("idle for")]) == 2
    assert kinds_of(events).count(SessionEventKind.BREAK_DUE) == 5


def test_every_block_is_counted_once_on_the_row_that_closes_it(
    session: BreakSession,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    assert session.start().focus is None  # nothing was open

    clock.advance(schedule.focus_interval)
    session.tick()
    clock.advance(schedule.break_duration)
    assert only(session.tick(), SessionEventKind.BREAK_COMPLETED).focus == schedule.focus_interval

    clock.advance(schedule.focus_interval)
    session.tick()
    clock.advance(3.0)
    assert session.skip_break().focus == schedule.focus_interval

    context.queue.append(RestSatisfied(reason="session lock", rested_for=600.0))
    clock.advance(schedule.focus_interval)
    assert only(session.tick(), SessionEventKind.BREAK_SATISFIED).focus == schedule.focus_interval

    clock.advance(400.0)
    assert session.start().focus == 400.0  # a restart closes the running block
    clock.advance(250.0)
    assert session.stop().focus == 250.0


def test_a_break_postponed_from_the_break_screen_keeps_its_block_open(
    session: BreakSession, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    """Snoozing from the overlay sends the owed break back to waiting; the
    stretch at the screen carries on, and is counted once when it does end."""
    session.start()
    clock.advance(schedule.focus_interval)
    session.tick()
    clock.advance(2.0)
    assert session.snooze().focus is None

    clock.advance(schedule.snooze_interval)
    assert kinds_of(session.tick()) == [SessionEventKind.BREAK_STARTED]
    clock.advance(schedule.break_duration)
    completed = only(session.tick(), SessionEventKind.BREAK_COMPLETED)
    assert completed.focus == schedule.focus_interval + schedule.snooze_interval
