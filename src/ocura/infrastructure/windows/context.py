from __future__ import annotations

from collections.abc import Callable, Sequence

from ocura.domain.clock import MonotonicClock
from ocura.domain.context import ContextAssessment, ContextDetector, DetectorChain
from ocura.domain.timer import TimerSnapshot
from ocura.infrastructure.credit import RestCreditLedger
from ocura.infrastructure.windows.detectors import (
    IDLE_THRESHOLD,
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

    def __init__(
        self,
        chain: DetectorChain,
        observers: Sequence[Callable[[], None]] = (),
        idle: IdleDetector | None = None,
        clock: MonotonicClock | None = None,
    ) -> None:
        self._chain = chain
        self._observers = tuple(observers)
        self._idle = idle
        self._clock = clock

    @property
    def detectors(self) -> tuple[ContextDetector, ...]:
        return self._chain.detectors

    def set_idle_threshold(self, seconds: float) -> None:
        """Retune the idle detector while the session runs.

        The whole chain is not rebuilt for this. The session-lock detector
        carries a ledger of rest observed since the process started, and
        replacing it to change an unrelated number would throw that away —
        the user would lose credit for a lock they are in the middle of.
        """
        if self._idle is not None:
            self._idle.set_threshold(seconds)

    @property
    def away_after(self) -> float:
        """The idle threshold: past it, Ocura neither interrupts nor counts.

        It is a setting, so "away" moves with it. Someone who sets ten minutes
        has up to ten minutes of each absence counted as time at the screen —
        they said what counts as away, and one definition serving both
        decisions is the point. Infinite without an idle detector: nothing is
        ever taken out of a block on evidence that is not there.
        """
        return self._idle.threshold if self._idle is not None else float("inf")

    def last_input(self) -> float:
        """The latest input as a monotonic moment.

        Monotonic time minus GetLastInputInfo's idle count. The two are
        different counters, but both include time asleep and agree to within
        0.05 s across a sleep (measured 2026-10-30), which is what lets an
        absence that spans one be placed on the monotonic clock at all.
        """
        if self._clock is None:
            return 0.0
        if self._idle is None:
            # No idle signal, so no evidence of absence: input is always "now".
            return self._clock.monotonic()
        return self._clock.monotonic() - self._idle.idle_seconds()

    def poll(self) -> None:
        for observe in self._observers:
            observe()

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        return self._chain.assess(snapshot)


def build_windows_context(
    clock: MonotonicClock,
    ledger: RestCreditLedger | None = None,
    idle_threshold: float = IDLE_THRESHOLD,
) -> WindowsContext:
    # Imported here so this module stays importable off Windows; loading api.py
    # binds user32 and kernel32 immediately.
    from ocura.infrastructure.windows import api

    ledger = ledger or RestCreditLedger(clock)
    lock = SessionLockDetector(api.is_locked, clock, ledger)
    idle = IdleDetector(api.idle_seconds, threshold=idle_threshold)
    chain = DetectorChain(
        lock,
        idle,
        PresentationDetector(api.is_presenting),
        ScreensaverDetector(api.is_screensaver_running),
    )
    return WindowsContext(chain, observers=(lock.observe,), idle=idle, clock=clock)
