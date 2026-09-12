from __future__ import annotations

import math

import pytest

from ocura.domain.errors import ConfigurationError
from ocura.domain.schedule import DEFAULT_SCHEDULE, BreakSchedule


def test_from_minutes_converts_to_seconds():
    schedule = BreakSchedule.from_minutes(20, 0.5, 5)
    assert (schedule.focus_interval, schedule.break_duration, schedule.defer_interval) == (
        1200.0,
        30.0,
        300.0,
    )


def test_default_schedule_is_valid():
    assert DEFAULT_SCHEDULE.focus_interval == 1200.0


@pytest.mark.parametrize("value", [0, -1, -0.5])
def test_non_positive_durations_rejected(value):
    with pytest.raises(ConfigurationError):
        BreakSchedule(focus_interval=value, break_duration=30.0, defer_interval=300.0)
    with pytest.raises(ConfigurationError):
        BreakSchedule(focus_interval=1200.0, break_duration=value, defer_interval=300.0)
    with pytest.raises(ConfigurationError):
        BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_durations_rejected(value):
    with pytest.raises(ConfigurationError, match="finite"):
        BreakSchedule(focus_interval=value, break_duration=30.0, defer_interval=300.0)


def test_non_numeric_duration_rejected():
    with pytest.raises(ConfigurationError, match="number"):
        BreakSchedule(focus_interval="1200", break_duration=30.0, defer_interval=300.0)


def test_bool_is_not_a_duration():
    with pytest.raises(ConfigurationError, match="number"):
        BreakSchedule(focus_interval=True, break_duration=30.0, defer_interval=300.0)


def test_break_at_least_as_long_as_focus_rejected():
    with pytest.raises(ConfigurationError, match="break_duration"):
        BreakSchedule(focus_interval=300.0, break_duration=300.0, defer_interval=60.0)


def test_deferral_at_least_as_long_as_focus_rejected():
    with pytest.raises(ConfigurationError, match="defer_interval"):
        BreakSchedule(focus_interval=300.0, break_duration=30.0, defer_interval=600.0)


def test_schedule_is_immutable():
    with pytest.raises(AttributeError):
        DEFAULT_SCHEDULE.focus_interval = 60.0
