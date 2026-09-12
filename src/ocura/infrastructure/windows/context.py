from __future__ import annotations

from collections.abc import Callable, Sequence

from ocura.domain.clock import MonotonicClock
from ocura.domain.context import ContextAssessment, ContextDetector, DetectorChain
from ocura.domain.timer import TimerSnapshot
from ocura.infrastructure.credit import RestCreditLedger
from ocura.infrastructure.windows.detectors import (
    IdleDetector,
    PresentationDetector,
    ScreensaverDetector,
    SessionLockDetector,
)


class WindowsContext:
    """A context source plus the observation that must happen when nothing is owed.

    The session only consults a context source when a break is owed, which is
    correct for deciding whether to interrupt but useless for watching a lock that
    started twenty minutes earlier. poll() is therefore driven by the application's
    tick, every tick, and assess() answers the question when it is finally asked.
    """

    def __init__(self, chain: DetectorChain, observers: Sequence[Callable[[], None]] = ()) -> None:
        self._chain = chain
        self._observers = tuple(observers)

    @property
    def detectors(self) -> tuple[ContextDetector, ...]:
        return self._chain.detectors

    def poll(self) -> None:
        for observe in self._observers:
            observe()

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        return self._chain.assess(snapshot)


def build_windows_context(
    clock: MonotonicClock, ledger: RestCreditLedger | None = None
) -> WindowsContext:
    # Imported here so this module stays importable off Windows; loading api.py
    # binds user32 and kernel32 immediately.
    from ocura.infrastructure.windows import api

    ledger = ledger or RestCreditLedger(clock)
    lock = SessionLockDetector(api.is_locked, clock, ledger)
    chain = DetectorChain(
        lock,
        IdleDetector(api.idle_seconds),
        PresentationDetector(api.is_presenting),
        ScreensaverDetector(api.is_screensaver_running),
    )
    return WindowsContext(chain, observers=(lock.observe,))
