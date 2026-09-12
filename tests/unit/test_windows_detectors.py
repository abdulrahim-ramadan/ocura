from __future__ import annotations

from ocura.domain.context import Deferral, Interruptible, RestSatisfied
from ocura.domain.timer import BreakTimer
from ocura.infrastructure.credit import RestCreditLedger
from ocura.infrastructure.windows.detectors import (
    AWAY_RETRY,
    IDLE_THRESHOLD,
    IdleDetector,
    PresentationDetector,
    ScreensaverDetector,
    SessionLockDetector,
)

from .conftest import FakeMonotonicClock


class Switch:
    """A signal a test can flip, standing in for a Win32 call."""

    def __init__(self, value: bool | float = False) -> None:
        self.value = value

    def __call__(self) -> bool | float:
        return self.value


def test_active_user_is_not_idle(due_timer: BreakTimer):
    detector = IdleDetector(Switch(5.0))
    assert detector.assess(due_timer.snapshot()) == Interruptible()


def test_idle_defers_and_says_for_how_long(due_timer: BreakTimer):
    outcome = IdleDetector(Switch(300.0)).assess(due_timer.snapshot())
    assert outcome == Deferral(reason="idle for 300s", retry_after=AWAY_RETRY)


def test_idle_fires_exactly_at_the_threshold(due_timer: BreakTimer):
    snapshot = due_timer.snapshot()
    assert IdleDetector(Switch(IDLE_THRESHOLD - 0.001)).assess(snapshot) == Interruptible()
    assert isinstance(IdleDetector(Switch(IDLE_THRESHOLD)).assess(snapshot), Deferral)


def test_idle_never_satisfies_however_long_it_runs(due_timer: BreakTimer):
    # The reading case: hours without input is still not evidence of rest.
    outcome = IdleDetector(Switch(6 * 3600.0)).assess(due_timer.snapshot())
    assert isinstance(outcome, Deferral)


def test_idle_leaves_the_ledger_empty(due_timer: BreakTimer, clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    IdleDetector(Switch(6 * 3600.0)).assess(due_timer.snapshot())
    assert ledger.take() is None


def test_locking_defers_while_it_lasts(due_timer: BreakTimer, clock: FakeMonotonicClock):
    locked = Switch(True)
    detector = SessionLockDetector(locked, clock, RestCreditLedger(clock))

    outcome = detector.assess(due_timer.snapshot())
    assert outcome == Deferral(reason="session locked", retry_after=AWAY_RETRY)
    assert detector.locked is True


def test_lock_duration_becomes_credit_on_unlock(due_timer: BreakTimer, clock: FakeMonotonicClock):
    locked = Switch(False)
    ledger = RestCreditLedger(clock)
    detector = SessionLockDetector(locked, clock, ledger)

    locked.value = True
    detector.observe()
    clock.advance(900.0)
    locked.value = False
    detector.observe()

    credit = ledger.peek()
    assert credit is not None
    assert (credit.seconds, credit.source) == (900.0, "session lock")


def test_credit_is_spent_at_the_next_owed_break(due_timer: BreakTimer, clock: FakeMonotonicClock):
    locked = Switch(True)
    ledger = RestCreditLedger(clock)
    detector = SessionLockDetector(locked, clock, ledger)

    detector.observe()
    clock.advance(1800.0)
    locked.value = False

    outcome = detector.assess(due_timer.snapshot())
    assert outcome == RestSatisfied(reason="session lock", rested_for=1800.0)
    # Consumed once: a second break is not discharged by the same absence.
    assert detector.assess(due_timer.snapshot()) == Interruptible()


def test_lock_observed_during_focus_credits_a_break_owed_later(clock: FakeMonotonicClock):
    """The whole point of the ledger: the lock happened before anything was owed."""
    locked = Switch(True)
    ledger = RestCreditLedger(clock)
    detector = SessionLockDetector(locked, clock, ledger)

    detector.observe()
    clock.advance(1200.0)
    locked.value = False
    detector.observe()

    credit = ledger.peek()
    assert credit is not None
    assert credit.seconds == 1200.0


def test_stale_lock_credit_is_not_spent(due_timer: BreakTimer, clock: FakeMonotonicClock):
    locked = Switch(True)
    ledger = RestCreditLedger(clock, staleness_window=60.0)
    detector = SessionLockDetector(locked, clock, ledger)

    detector.observe()
    clock.advance(900.0)
    locked.value = False
    detector.observe()

    clock.advance(60.0)
    assert detector.assess(due_timer.snapshot()) == Interruptible()


def test_unlocked_and_unrested_is_interruptible(due_timer: BreakTimer, clock: FakeMonotonicClock):
    detector = SessionLockDetector(Switch(False), clock, RestCreditLedger(clock))
    assert detector.assess(due_timer.snapshot()) == Interruptible()


def test_repeated_observation_while_locked_keeps_one_start(clock: FakeMonotonicClock):
    locked = Switch(True)
    ledger = RestCreditLedger(clock)
    detector = SessionLockDetector(locked, clock, ledger)

    for _ in range(5):
        detector.observe()
        clock.advance(100.0)
    locked.value = False
    detector.observe()

    credit = ledger.peek()
    assert credit is not None
    assert credit.seconds == 500.0


def test_presenting_defers(due_timer: BreakTimer):
    outcome = PresentationDetector(Switch(True)).assess(due_timer.snapshot())
    assert outcome == Deferral(reason="fullscreen or presenting", retry_after=None)


def test_an_ordinary_window_is_interruptible(due_timer: BreakTimer):
    assert PresentationDetector(Switch(False)).assess(due_timer.snapshot()) == Interruptible()


def test_screensaver_defers_but_never_satisfies(due_timer: BreakTimer):
    outcome = ScreensaverDetector(Switch(True)).assess(due_timer.snapshot())
    assert outcome == Deferral(reason="screensaver running", retry_after=AWAY_RETRY)


def test_no_screensaver_is_interruptible(due_timer: BreakTimer):
    assert ScreensaverDetector(Switch(False)).assess(due_timer.snapshot()) == Interruptible()
