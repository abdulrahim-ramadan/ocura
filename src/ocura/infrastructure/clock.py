from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemMonotonicClock:
    """time.monotonic() is unaffected by NTP steps and by the user changing the clock."""

    def monotonic(self) -> float:
        return time.monotonic()


class SystemWallClock:
    """UTC-aware; local presentation is the UI's problem, not the domain's."""

    def now(self) -> datetime:
        return datetime.now(UTC)
