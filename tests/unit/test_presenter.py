"""Presenter tests: no QApplication, no widgets, no display."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ocura.application.journal import NullJournal, SessionJournal
from ocura.application.presenter import (
    BREAK_TIPS,
    TICK_SECONDS,
    BreakPresenter,
    SessionView,
)
from ocura.application.session import SessionEvent, SessionEventKind
from ocura.domain.context import Deferral, Interruptible, RestSatisfied
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerState

from .conftest import ACCUSATORY_WORDS, FakeMonotonicClock, FakeWallClock, ScriptedContext


@pytest.fixture
def context() -> ScriptedContext:
    return ScriptedContext()


@pytest.fixture
def presenter(
    schedule: BreakSchedule,
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
) -> BreakPresenter:
    return BreakPresenter(schedule, clock, wall_clock, context)


def run_for(presenter: BreakPresenter, clock: FakeMonotonicClock, seconds: float) -> SessionView:
    """Pulse at the advisory cadence, exactly as the QTimer will."""
    view = presenter.view()
    for _ in range(int(seconds / TICK_SECONDS)):
        clock.advance(TICK_SECONDS)
        view = presenter.tick()
    return view


def test_idle_before_start(presenter: BreakPresenter):
    view = presenter.view()
    assert view.state is TimerState.IDLE
    assert view.running is False
    assert view.headline == "Not running"


def test_ticking_before_start_does_nothing(presenter: BreakPresenter, clock: FakeMonotonicClock):
    view = run_for(presenter, clock, 60)
    assert view.state is TimerState.IDLE
    assert view.focus_elapsed == 0.0


def test_start_begins_focusing(presenter: BreakPresenter):
    view = presenter.start()
    assert view.state is TimerState.FOCUSING
    assert view.running is True
    assert view.headline == "Focusing"
    assert view.events[-1].text == "Session started"


def test_countdown_text_and_progress(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    view = run_for(presenter, clock, 300)

    assert view.focus_elapsed_text == "5:00"
    assert view.countdown_text == "15:00"
    assert view.detail == "Next break in 15:00."
    assert view.progress == pytest.approx(300 / schedule.focus_interval)


def test_hours_appear_only_when_needed(
    clock: FakeMonotonicClock, wall_clock: FakeWallClock, context: ScriptedContext
):
    schedule = BreakSchedule(focus_interval=2 * 3600.0, break_duration=60.0, defer_interval=300.0)
    presenter = BreakPresenter(schedule, clock, wall_clock, context)
    presenter.start()

    assert presenter.view().countdown_text == "2:00:00"
    clock.advance(3600.0)
    assert presenter.tick().countdown_text == "1:00:00"


def test_break_starts_and_finishes(
    presenter: BreakPresenter, clock: FakeMonotonicClock, schedule: BreakSchedule
):
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.state is TimerState.ON_BREAK
    assert view.headline == "On a break"
    assert "Look somewhere far away" in view.detail

    view = run_for(presenter, clock, schedule.break_duration)
    assert view.state is TimerState.FOCUSING
    assert view.breaks_taken == 1
    assert [line.text for line in view.events[-2:]] == ["Break started", "Break finished"]


def test_deferral_shows_the_detector_reason(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="session locked"))
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)

    assert view.state is TimerState.DEFERRED
    assert view.break_owed is True
    assert view.waiting_reason == "session locked"
    assert view.headline == "Waiting for a good moment"
    assert view.detail == "Break owed — session locked."
    assert view.events[-1].text == "Waiting — session locked"


def test_a_fullscreen_deferral_reads_differently(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="fullscreen or presenting"))
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.waiting_reason == "fullscreen or presenting"


def test_the_reason_clears_when_the_break_is_satisfied(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="session locked"))
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)

    context.queue.append(RestSatisfied(reason="session lock", rested_for=900.0))
    view = run_for(presenter, clock, schedule.defer_interval)

    assert view.state is TimerState.FOCUSING
    assert view.waiting_reason is None
    assert view.rests_credited == 1
    assert view.events[-1].text == "Rest credited — session lock"


def test_pause_freezes_and_resume_continues(presenter: BreakPresenter, clock: FakeMonotonicClock):
    presenter.start()
    run_for(presenter, clock, 300)

    view = presenter.set_paused(True)
    assert view.paused is True
    assert view.state is TimerState.PAUSED
    assert view.headline == "Reminders paused"

    view = run_for(presenter, clock, 600)
    assert view.focus_elapsed == 300.0

    view = presenter.set_paused(False)
    assert view.paused is False
    assert view.state is TimerState.FOCUSING
    assert view.focus_elapsed == 300.0


def test_toggling_pause_twice_returns_to_focusing(presenter: BreakPresenter):
    presenter.start()
    assert presenter.toggle_paused().state is TimerState.PAUSED
    assert presenter.toggle_paused().state is TimerState.FOCUSING


def test_pausing_twice_is_harmless(presenter: BreakPresenter):
    presenter.start()
    presenter.set_paused(True)
    view = presenter.set_paused(True)
    assert view.state is TimerState.PAUSED


def test_pause_before_start_is_ignored(presenter: BreakPresenter):
    view = presenter.set_paused(True)
    assert view.state is TimerState.IDLE
    assert view.paused is False


def test_the_user_can_take_an_owed_break_while_it_is_deferred(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.append(Deferral(reason="session locked"))
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.state is TimerState.DEFERRED
    assert view.can_take_break_now is True

    view = presenter.take_break_now()
    assert view.state is TimerState.ON_BREAK
    assert view.waiting_reason is None
    assert view.events[-1].text == "Break started"


def test_the_control_is_offered_while_focusing(presenter: BreakPresenter):
    presenter.start()
    view = presenter.take_break_now()
    assert view.state is TimerState.ON_BREAK
    assert view.can_take_break_now is False


def test_the_control_is_not_offered_before_start_or_on_a_break(presenter: BreakPresenter):
    assert presenter.view().can_take_break_now is False
    presenter.start()
    presenter.take_break_now()
    assert presenter.view().can_take_break_now is False


def test_stop_returns_to_idle(presenter: BreakPresenter, clock: FakeMonotonicClock):
    presenter.start()
    run_for(presenter, clock, 300)
    view = presenter.stop()

    assert view.state is TimerState.IDLE
    assert view.running is False
    assert view.events[-1].text == "Session stopped"


def test_the_event_list_is_capped(
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    presenter = BreakPresenter(schedule, clock, wall_clock, context, max_events=5)
    presenter.start()
    for _ in range(10):
        run_for(presenter, clock, schedule.focus_interval)
        run_for(presenter, clock, schedule.break_duration)

    assert len(presenter.view().events) == 5


def test_no_event_text_is_accusatory(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    context.queue.extend(
        [Deferral(reason="session locked"), Deferral(reason="fullscreen or presenting")]
    )
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    run_for(presenter, clock, schedule.defer_interval)
    presenter.set_paused(True)
    presenter.set_paused(False)
    view = run_for(presenter, clock, schedule.focus_interval + schedule.break_duration)

    words = " ".join(line.text for line in view.events).lower()
    words += f" {view.headline} {view.detail} {presenter.tooltip()}".lower()
    assert not [bad for bad in ACCUSATORY_WORDS if bad in words]


def test_break_due_is_not_shown_as_an_event(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    """It is a decision point, and it fires even on ticks that resolve immediately."""
    context.queue.append(RestSatisfied(reason="session lock", rested_for=900.0))
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)

    assert [line.text for line in view.events] == [
        "Session started",
        "Rest credited — session lock",
    ]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00"), (5, "0:05"), (65, "1:05"), (600, "10:00"), (3600, "1:00:00"), (-5, "0:00")],
)
def test_clock_text(seconds: float, expected: str):
    from ocura.application.presenter import _clock_text

    assert _clock_text(seconds) == expected


def test_tooltip_tracks_the_state(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    assert presenter.tooltip() == "Ocura — not running"

    presenter.start()
    assert presenter.tooltip().startswith("Ocura — next break in")

    presenter.set_paused(True)
    assert presenter.tooltip() == "Ocura — reminders paused"
    presenter.set_paused(False)

    context.queue.append(Deferral(reason="session locked"))
    run_for(presenter, clock, schedule.focus_interval)
    assert presenter.tooltip() == "Ocura — waiting, session locked"


def test_a_pollable_context_is_polled_every_tick(
    clock: FakeMonotonicClock, wall_clock: FakeWallClock, schedule: BreakSchedule
):
    context = _Pollable()
    presenter = BreakPresenter(schedule, clock, wall_clock, context)
    presenter.start()
    run_for(presenter, clock, 10)

    assert context.polls == 10


def test_a_plain_context_source_is_still_accepted(
    presenter: BreakPresenter, clock: FakeMonotonicClock
):
    """ScriptedContext has no poll(); the presenter must not require one."""
    presenter.start()
    assert run_for(presenter, clock, 10).state is TimerState.FOCUSING


class _Pollable:
    def __init__(self) -> None:
        self.polls = 0

    def poll(self) -> None:
        self.polls += 1

    def assess(self, snapshot):
        return Interruptible()


def test_the_break_screen_is_given_a_tip(presenter: BreakPresenter):
    """It never reached the screen because nothing ever produced one."""
    assert presenter.view().tip in BREAK_TIPS
    assert presenter.view().tip


def test_the_tip_does_not_change_while_a_break_is_running(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    """A line that rewrote itself every second would be the loudest thing there."""
    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    assert presenter.view().state is TimerState.ON_BREAK

    seen = {presenter.view().tip}
    for _ in range(int(schedule.break_duration) - 1):
        clock.advance(TICK_SECONDS)
        seen.add(presenter.tick().tip)

    assert len(seen) == 1


def test_a_later_break_shows_a_different_tip(
    presenter: BreakPresenter,
    clock: FakeMonotonicClock,
    context: ScriptedContext,
    schedule: BreakSchedule,
):
    presenter.start()
    seen = []
    for _ in range(len(BREAK_TIPS)):
        run_for(presenter, clock, schedule.focus_interval)
        seen.append(presenter.view().tip)
        run_for(presenter, clock, schedule.break_duration)

    assert len(set(seen)) == len(BREAK_TIPS)


def test_every_tip_carries_the_source_it_rests_on():
    """An unattributable claim about someone's eyes does not belong on screen."""
    for tip in BREAK_TIPS:
        assert "—" in tip, tip
        _, source = tip.rsplit("—", 1)
        assert len(source.strip()) > 10, tip


def test_no_tip_instructs_or_scolds():
    """The screen already says what to do; a second, smaller voice is nagging."""
    forbidden = ("must", "should", "you need", "failed", "missed", "remember to")
    for tip in BREAK_TIPS:
        assert not [bad for bad in forbidden if bad in tip.lower()], tip


def an_event(kind: SessionEventKind = SessionEventKind.STARTED) -> SessionEvent:
    return SessionEvent(kind=kind, at=datetime(2026, 9, 17, tzinfo=UTC), state=TimerState.IDLE)


# --- the journal seam -----------------------------------------------------


class RecordingJournal:
    def __init__(self) -> None:
        self.events: list[SessionEvent] = []

    def record(self, event: SessionEvent) -> None:
        self.events.append(event)


class BrokenJournal:
    """A disk that is full, a file an antivirus scanner has locked, a bug."""

    def __init__(self) -> None:
        self.attempts = 0

    def record(self, event: SessionEvent) -> None:
        del event
        self.attempts += 1
        raise OSError("no space left on device")


def test_a_presenter_with_no_journal_still_runs(
    schedule: BreakSchedule,
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
):
    """The default is NullJournal, and the session cannot tell the difference."""
    presenter = BreakPresenter(schedule, clock, wall_clock, context)
    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)

    assert view.state is TimerState.ON_BREAK


def test_every_event_reaches_the_journal(
    schedule: BreakSchedule,
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
):
    """Including the ones the dashboard does not show. BREAK_DUE is noise on a
    glance surface and evidence in a log."""
    journal = RecordingJournal()
    presenter = BreakPresenter(schedule, clock, wall_clock, context, journal=journal)

    presenter.start()
    run_for(presenter, clock, schedule.focus_interval)
    run_for(presenter, clock, schedule.break_duration)

    kinds = [event.kind for event in journal.events]
    assert SessionEventKind.STARTED in kinds
    assert SessionEventKind.BREAK_STARTED in kinds
    assert SessionEventKind.BREAK_COMPLETED in kinds
    assert SessionEventKind.BREAK_DUE in kinds, "the log dropped what the list filters"

    # Nothing is recorded that the session did not emit.
    shown = [line.text for line in presenter.view().events]
    assert len(journal.events) > len(shown)


def test_a_journal_that_raises_does_not_stop_the_break_engine(
    schedule: BreakSchedule,
    clock: FakeMonotonicClock,
    wall_clock: FakeWallClock,
    context: ScriptedContext,
    caplog,
):
    """A full disk costs the user their history. It must never cost them a break."""
    journal = BrokenJournal()
    presenter = BreakPresenter(schedule, clock, wall_clock, context, journal=journal)

    presenter.start()
    view = run_for(presenter, clock, schedule.focus_interval)
    assert view.state is TimerState.ON_BREAK

    view = run_for(presenter, clock, schedule.break_duration)
    assert view.state is TimerState.FOCUSING
    assert view.breaks_taken == 1

    assert journal.attempts > 0, "the journal was never even tried"
    assert any("history is incomplete" in record.message for record in caplog.records)


def test_the_null_journal_accepts_anything_and_says_nothing():
    journal = NullJournal()
    assert journal.record(an_event()) is None
    assert isinstance(journal, SessionJournal)
