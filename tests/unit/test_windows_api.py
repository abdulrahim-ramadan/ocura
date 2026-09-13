"""The one place api.py is testable: which lock source wins, and when.

Everything else in that module is a raw Win32 call and is verified by hand
against a real desktop, not here. See docs/architecture.md, "Verified against
the real API".
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="api.py binds user32, kernel32, shell32 and wtsapi32"
)


@pytest.fixture
def api():
    from ocura.infrastructure.windows import api as module

    return module


@pytest.mark.parametrize("wts_says", [True, False])
def test_wts_is_the_source_of_truth(api, monkeypatch, wts_says: bool):
    monkeypatch.setattr(api, "locked_via_wts", lambda: wts_says)
    # Set the fallback to the opposite answer: if it is ever consulted, this fails.
    monkeypatch.setattr(api, "locked_via_input_desktop", lambda: not wts_says)

    assert api.is_locked() is wts_says


def test_the_input_desktop_is_only_a_fallback(api, monkeypatch):
    """OpenInputDesktop reports the secure desktop, which lags a lock by minutes.

    It is consulted only when the WTS query itself fails, never to second-guess
    an answer WTS already gave.
    """
    monkeypatch.setattr(api, "locked_via_wts", lambda: None)
    monkeypatch.setattr(api, "locked_via_input_desktop", lambda: True)

    assert api.is_locked() is True


def test_the_wts_struct_places_session_flags_correctly(api):
    """A truncated WTSINFOEX_LEVEL1 shifts SessionFlags and silently misreads it."""
    import ctypes

    level1 = api._WTSINFOEX_LEVEL1
    assert level1.SessionId.offset == 0
    assert level1.SessionState.offset == 4
    assert level1.SessionFlags.offset == 8
    assert ctypes.alignment(level1) == 8
    # The union is 8-byte aligned, so Level is followed by four bytes of padding.
    assert api._WTSINFOEX.Data.offset == 8


def test_the_live_query_answers_at_all(api):
    """Not asserting locked or unlocked: only that the call works on this machine."""
    assert api.locked_via_wts() in (True, False)
    assert isinstance(api.is_locked(), bool)
