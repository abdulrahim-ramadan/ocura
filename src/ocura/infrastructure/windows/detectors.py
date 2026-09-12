"""Detectors that turn Windows signals into the domain's three answers.

Each takes its signal as a plain callable rather than reaching for api.py itself,
so every branch below is tested without a Windows API in sight. build_windows_context()
supplies the real ones.
"""

from __future__ import annotations

from collections.abc import Callable

from ocura.domain.clock import MonotonicClock
from ocura.domain.context import (
    INTERRUPTIBLE,
    ContextAssessment,
    Deferral,
    RestSatisfied,
)
from ocura.domain.timer import TimerSnapshot
from ocura.infrastructure.credit import RestCreditLedger

#: How long without input before a break offer is pointless. Two minutes is long
#: enough that it is not just a pause for thought.
IDLE_THRESHOLD = 120.0

#: While away, ask again soon: the moment they come back is the moment to offer.
AWAY_RETRY = 30.0


class IdleDetector:
    """Idle defers and never satisfies.

    A reader produces no input for many minutes while their eyes are at their
    worst, and is indistinguishable from an empty chair through GetLastInputInfo.
    Crediting that as rest would silence Ocura for exactly the user who needs it,
    so idleness only postpones the offer. See docs/architecture.md,
    "What counts as rest: lock yes, idle no".
    """

    def __init__(
        self,
        idle_seconds: Callable[[], float],
        threshold: float = IDLE_THRESHOLD,
        retry_after: float | None = AWAY_RETRY,
    ) -> None:
        self._idle_seconds = idle_seconds
        self._threshold = threshold
        self._retry_after = retry_after

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        idle = self._idle_seconds()
        if idle >= self._threshold:
            return Deferral(reason=f"idle for {idle:.0f}s", retry_after=self._retry_after)
        return INTERRUPTIBLE


class SessionLockDetector:
    """Lock is satisfaction, unconditionally: locking means "I am leaving".

    observe() runs every tick so lock time accumulates while the user is merely
    focusing, long before a break is owed. assess() runs only when one is owed,
    and is where the accumulated credit gets spent.
    """

    def __init__(
        self,
        is_locked: Callable[[], bool],
        clock: MonotonicClock,
        ledger: RestCreditLedger,
        retry_after: float | None = AWAY_RETRY,
    ) -> None:
        self._is_locked = is_locked
        self._clock = clock
        self._ledger = ledger
        self._retry_after = retry_after
        self._locked_since: float | None = None

    @property
    def locked(self) -> bool:
        return self._locked_since is not None

    def observe(self) -> None:
        now = self._clock.monotonic()
        if self._is_locked():
            if self._locked_since is None:
                self._locked_since = now
            return
        if self._locked_since is not None:
            self._ledger.record(now - self._locked_since, source="session lock")
            self._locked_since = None

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        self.observe()
        if self.locked:
            # Nobody is at the screen to receive the offer, and the rest is still
            # being earned; it is banked on unlock, not now.
            return Deferral(reason="session locked", retry_after=self._retry_after)

        credit = self._ledger.take()
        if credit is None:
            return INTERRUPTIBLE
        return RestSatisfied(reason=credit.source, rested_for=credit.seconds)


class PresentationDetector:
    """A fullscreen app, presentation mode or Focus Assist. Defer, never satisfy.

    Backed by SHQueryUserNotificationState rather than a window-rectangle
    comparison: a maximized window overhangs its monitor by the invisible resize
    border and would otherwise read as fullscreen forever.
    """

    def __init__(
        self,
        is_presenting: Callable[[], bool],
        retry_after: float | None = None,
    ) -> None:
        self._is_presenting = is_presenting
        self._retry_after = retry_after

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        if self._is_presenting():
            return Deferral(reason="fullscreen or presenting", retry_after=self._retry_after)
        return INTERRUPTIBLE


class ScreensaverDetector:
    """A running screensaver means the screen is not being read.

    Deferral, not satisfaction: the screensaver starting is a timeout, not the
    deliberate act of leaving that a lock is, and the user may be sitting right
    there reading something on paper.
    """

    def __init__(
        self,
        is_running: Callable[[], bool],
        retry_after: float | None = AWAY_RETRY,
    ) -> None:
        self._is_running = is_running
        self._retry_after = retry_after

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        if self._is_running():
            return Deferral(reason="screensaver running", retry_after=self._retry_after)
        return INTERRUPTIBLE
