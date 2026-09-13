"""The reconciliation rule, tested without a display or a monitor to unplug."""

from __future__ import annotations

from ocura.ui.overlay import plan


def test_opens_one_window_per_screen_from_nothing():
    to_open, to_close = plan([], ["primary", "portrait"])
    assert to_open == ["primary", "portrait"]
    assert to_close == []


def test_a_settled_layout_needs_no_changes():
    to_open, to_close = plan(["primary", "portrait"], ["primary", "portrait"])
    assert (to_open, to_close) == ([], [])


def test_a_monitor_appearing_mid_break_opens_one_more():
    to_open, to_close = plan(["primary"], ["primary", "portrait"])
    assert to_open == ["portrait"]
    assert to_close == []


def test_a_monitor_disappearing_mid_break_closes_only_that_one():
    to_open, to_close = plan(["primary", "portrait"], ["primary"])
    assert to_open == []
    assert to_close == ["portrait"]


def test_a_swap_in_one_event_is_handled_as_both():
    """Docking can replace every screen between two ticks."""
    to_open, to_close = plan(["laptop"], ["desk-left", "desk-right"])
    assert to_open == ["desk-left", "desk-right"]
    assert to_close == ["laptop"]


def test_losing_every_screen_closes_everything():
    to_open, to_close = plan(["primary", "portrait"], [])
    assert to_open == []
    assert to_close == ["primary", "portrait"]


def test_the_plan_is_idempotent():
    """Any screen event re-runs the same function, so it must settle."""
    have: list[str] = []
    want = ["primary", "portrait"]
    for _ in range(3):
        to_open, to_close = plan(have, want)
        have = [key for key in have if key not in to_close] + to_open
    assert have == want
    assert plan(have, want) == ([], [])
