"""Time enters the domain only through these two protocols.

They are deliberately separate. Measuring how long someone has been focusing is
a duration problem and must survive the user (or NTP) moving the system clock.
Knowing that it is 22:30 on a Tuesday is a calendar problem and cannot be
answered by a monotonic counter. Conflating them is how a clock change from
09:30 to 10:15 turns into a phantom 45 minutes of focus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class MonotonicClock(Protocol):
    """Seconds from an arbitrary origin, never decreasing, unaffected by clock changes."""

    def monotonic(self) -> float: ...


@runtime_checkable
class WallClock(Protocol):
    """Calendar time. Only for things that genuinely need a date or a time of day."""

    def now(self) -> datetime: ...
