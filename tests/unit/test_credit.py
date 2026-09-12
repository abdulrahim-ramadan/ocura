from __future__ import annotations

from ocura.infrastructure.credit import STALENESS_WINDOW, RestCreditLedger

from .conftest import FakeMonotonicClock


def test_nothing_is_owed_by_default(clock: FakeMonotonicClock):
    assert RestCreditLedger(clock).take() is None


def test_recorded_rest_can_be_taken(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")

    credit = ledger.take()
    assert credit is not None
    assert (credit.seconds, credit.source) == (900.0, "session lock")


def test_credit_is_consumed_once(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")

    assert ledger.take() is not None
    assert ledger.take() is None


def test_peek_does_not_consume(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")

    assert ledger.peek() is not None
    assert ledger.peek() is not None
    assert ledger.take() is not None
    assert ledger.peek() is None


def test_credit_expires_at_the_staleness_window(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")

    clock.advance(STALENESS_WINDOW - 1.0)
    assert ledger.peek() is not None

    clock.advance(1.0)
    assert ledger.peek() is None
    assert ledger.take() is None


def test_staleness_window_is_configurable(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock, staleness_window=60.0)
    ledger.record(900.0, source="session lock")

    clock.advance(60.0)
    assert ledger.take() is None


def test_a_newer_rest_replaces_an_older_one(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")
    clock.advance(60.0)
    ledger.record(120.0, source="session lock")

    credit = ledger.take()
    assert credit is not None
    # Not summed: two absences are not one long break.
    assert credit.seconds == 120.0


def test_replacing_a_credit_restarts_its_expiry(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")
    clock.advance(STALENESS_WINDOW - 1.0)
    ledger.record(600.0, source="session lock")

    clock.advance(STALENESS_WINDOW - 1.0)
    assert ledger.peek() is not None


def test_worthless_rest_is_not_recorded(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(0.0, source="session lock")
    ledger.record(-5.0, source="session lock")
    assert ledger.take() is None


def test_clear_discards_pending_credit(clock: FakeMonotonicClock):
    ledger = RestCreditLedger(clock)
    ledger.record(900.0, source="session lock")
    ledger.clear()
    assert ledger.take() is None
