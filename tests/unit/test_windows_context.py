from __future__ import annotations

import sys

import pytest

from ocura.application.session import BreakSession, SessionEventKind
from ocura.domain.context import ContextSource, Deferral, DetectorChain, Interruptible
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import BreakTimer, TimerState
from ocura.infrastructure.credit import RestCreditLedger
from ocura.infrastructure.windows.context import WindowsContext, build_windows_context
from ocura.infrastructure.windows.detectors import (
    IdleDetector,
    PresentationDetector,
    SessionLockDetector,
)

from .conftest import FakeMonotonicClock, FakeWallClock
from .test_windows_detectors import Switch


def build(clock: FakeMonotonicClock, locked: Switch, idle: Switch, presenting: Switch):
    ledger = RestCreditLedger(clock)
    lock = SessionLockDetector(locked, clock, ledger)
    chain = DetectorChain(lock, IdleDetector(idle), PresentationDetector(presenting))
    return WindowsContext(chain, observers=(lock.observe,)), ledger


def test_it_is_a_context_source(clock: FakeMonotonicClock):
    context, _ = build(clock, Switch(False), Switch(0.0), Switch(False))
    assert isinstance(context, ContextSource)


def test_the_detectors_are_inspectable(clock: FakeMonotonicClock):
    context, _ = build(clock, Switch(False), Switch(0.0), Switch(False))
    names = [type(detector).__name__ for detector in context.detectors]
    assert names == ["SessionLockDetector", "IdleDetector", "PresentationDetector"]


@pytest.mark.skipif(sys.platform != "win32", reason="binds user32, kernel32 and shell32")
def test_the_real_chain_wires_all_four_detectors(clock: FakeMonotonicClock):
    context = build_windows_context(clock)
    names = [type(detector).__name__ for detector in context.detectors]
    assert names == [
        "SessionLockDetector",
        "IdleDetector",
        "PresentationDetector",
        "ScreensaverDetector",
    ]


def test_polling_accumulates_lock_time_without_any_break_owed(clock: FakeMonotonicClock):
    locked = Switch(True)
    context, ledger = build(clock, locked, Switch(0.0), Switch(False))

    context.poll()
    clock.advance(1200.0)
    locked.value = False
    context.poll()

    credit = ledger.peek()
    assert credit is not None
    assert credit.seconds == 1200.0


def test_clear_context_lets_the_break_through(due_timer: BreakTimer, clock: FakeMonotonicClock):
    context, _ = build(clock, Switch(False), Switch(0.0), Switch(False))
    assert context.assess(due_timer.snapshot()) == Interruptible()


def test_a_single_blocking_signal_defers(due_timer: BreakTimer, clock: FakeMonotonicClock):
    context, _ = build(clock, Switch(False), Switch(0.0), Switch(True))
    outcome = context.assess(due_timer.snapshot())
    assert isinstance(outcome, Deferral)
    assert "fullscreen" in outcome.reason


def test_lock_credit_outranks_a_fullscreen_deferral(
    due_timer: BreakTimer, clock: FakeMonotonicClock
):
    """Returning from lunch into a fullscreen app: the break is paid, not postponed."""
    locked = Switch(True)
    context, _ = build(clock, locked, Switch(0.0), Switch(True))

    context.poll()
    clock.advance(1800.0)
    locked.value = False

    outcome = context.assess(due_timer.snapshot())
    assert outcome.__class__.__name__ == "RestSatisfied"
    assert outcome.rested_for == 1800.0


def test_a_locked_session_defers_end_to_end(clock: FakeMonotonicClock, wall_clock: FakeWallClock):
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=300.0)
    locked = Switch(True)
    context, _ = build(clock, locked, Switch(0.0), Switch(False))
    session = BreakSession(schedule, clock, wall_clock, context)

    session.start()
    context.poll()
    clock.advance(schedule.focus_interval)
    context.poll()
    events = session.tick()

    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_DEFERRED,
    ]
    assert session.state is TimerState.DEFERRED


def test_unlocking_after_a_long_absence_discharges_the_break(
    clock: FakeMonotonicClock, wall_clock: FakeWallClock
):
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=300.0)
    locked = Switch(False)
    context, _ = build(clock, locked, Switch(0.0), Switch(False))
    session = BreakSession(schedule, clock, wall_clock, context)
    session.start()

    # Locked five minutes in, back forty minutes later, well past the focus interval.
    clock.advance(300.0)
    locked.value = True
    context.poll()
    clock.advance(2400.0)
    locked.value = False
    context.poll()

    events = session.tick()
    assert [event.kind for event in events] == [
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_SATISFIED,
    ]
    assert session.state is TimerState.FOCUSING
    assert session.snapshot().focus_elapsed == 0.0


def test_a_reader_is_deferred_not_credited(clock: FakeMonotonicClock, wall_clock: FakeWallClock):
    """Two hours of reading: no input, no lock. The break waits, it is never cancelled."""
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=300.0)
    idle = Switch(7200.0)
    context, ledger = build(clock, Switch(False), idle, Switch(False))
    session = BreakSession(schedule, clock, wall_clock, context)

    session.start()
    clock.advance(schedule.focus_interval)
    context.poll()
    session.tick()

    assert session.state is TimerState.DEFERRED
    assert session.snapshot().break_owed is True
    assert ledger.peek() is None

    # They look up and touch the mouse; the owed break arrives immediately.
    idle.value = 0.0
    clock.advance(schedule.defer_interval)
    context.poll()
    events = session.tick()

    # The re-offer is not written again; the break it offers is.
    assert [event.kind for event in events] == [SessionEventKind.BREAK_STARTED]
    assert session.state is TimerState.ON_BREAK


# --- presence ----------------------------------------------------------------


def present_context(clock: FakeMonotonicClock, idle: Switch) -> WindowsContext:
    detector = IdleDetector(idle, threshold=120.0)
    return WindowsContext(DetectorChain(detector), idle=detector, clock=clock)


def test_away_is_the_idle_detectors_own_threshold_and_follows_it(clock: FakeMonotonicClock):
    """One definition of away: the moment Ocura stops interrupting is the
    moment it stops counting, including after the user changes the setting."""
    context = present_context(clock, Switch(0.0))
    assert context.away_after == 120.0

    context.set_idle_threshold(600.0)
    assert context.away_after == 600.0


def test_the_last_input_is_now_less_the_idle_count(clock: FakeMonotonicClock):
    idle = Switch(42.5)
    context = present_context(clock, idle)
    assert context.last_input() == clock.monotonic() - 42.5


def test_with_no_idle_signal_nothing_is_ever_counted_as_absence(clock: FakeMonotonicClock):
    context = WindowsContext(DetectorChain(), clock=clock)
    assert context.away_after == float("inf")
    assert context.last_input() == clock.monotonic()


def test_the_real_context_answers_presence(clock: FakeMonotonicClock):
    from ocura.application.presenter import PresenceContext

    assert isinstance(present_context(clock, Switch(0.0)), PresenceContext)
