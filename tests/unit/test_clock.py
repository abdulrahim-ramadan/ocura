from __future__ import annotations

from datetime import UTC, datetime

from ocura.domain.clock import MonotonicClock, WallClock
from ocura.infrastructure.clock import SystemMonotonicClock, SystemWallClock

from .conftest import FakeMonotonicClock, FakeWallClock


def test_production_clocks_satisfy_the_protocols():
    assert isinstance(SystemMonotonicClock(), MonotonicClock)
    assert isinstance(SystemWallClock(), WallClock)


def test_fakes_satisfy_the_protocols():
    assert isinstance(FakeMonotonicClock(), MonotonicClock)
    assert isinstance(FakeWallClock(), WallClock)


def test_the_two_protocols_are_not_interchangeable():
    assert not isinstance(SystemMonotonicClock(), WallClock)
    assert not isinstance(SystemWallClock(), MonotonicClock)


def test_system_monotonic_never_goes_backwards():
    clock = SystemMonotonicClock()
    readings = [clock.monotonic() for _ in range(5)]
    assert readings == sorted(readings)


def test_system_wall_clock_is_timezone_aware():
    now = SystemWallClock().now()
    assert isinstance(now, datetime)
    assert now.tzinfo is UTC


def test_fake_monotonic_refuses_to_go_backwards():
    clock = FakeMonotonicClock()
    try:
        clock.advance(-1.0)
    except AssertionError:
        return
    raise AssertionError("expected the fake to reject a backwards step")
