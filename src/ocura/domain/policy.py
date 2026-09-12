"""Turns a context assessment into exactly one timer transition.

Deferral and satisfaction reach the timer through separate branches calling
separate methods, and report separate outcome types. Nothing downstream has to
inspect a flag to tell which of the two happened.
"""

from __future__ import annotations

from dataclasses import dataclass

from ocura.domain.context import (
    ContextAssessment,
    Deferral,
    Interruptible,
    RestSatisfied,
)
from ocura.domain.errors import InsufficientRestError
from ocura.domain.timer import BreakTimer, TimerState


@dataclass(frozen=True, slots=True)
class BreakStarted:
    pass


@dataclass(frozen=True, slots=True)
class BreakDeferred:
    reason: str
    retry_after: float | None


@dataclass(frozen=True, slots=True)
class BreakSatisfied:
    reason: str
    rested_for: float


@dataclass(frozen=True, slots=True)
class NoAction:
    reason: str


PolicyOutcome = BreakStarted | BreakDeferred | BreakSatisfied | NoAction


class BreakPolicy:
    def resolve(self, timer: BreakTimer, assessment: ContextAssessment) -> PolicyOutcome:
        match timer.state:
            case TimerState.BREAK_DUE:
                return self._resolve_due(timer, assessment)
            case TimerState.DEFERRED:
                return self._resolve_deferred(timer, assessment)
            case _:
                return NoAction("no break is owed")

    def _resolve_due(self, timer: BreakTimer, assessment: ContextAssessment) -> PolicyOutcome:
        match assessment:
            case Interruptible():
                timer.begin_break()
                return BreakStarted()
            case Deferral(reason=reason, retry_after=retry_after):
                timer.defer(retry_after=retry_after)
                return BreakDeferred(reason=reason, retry_after=retry_after)
            case RestSatisfied(reason=reason, rested_for=rested_for):
                return self._satisfy(timer, reason, rested_for)

    def _resolve_deferred(self, timer: BreakTimer, assessment: ContextAssessment) -> PolicyOutcome:
        # A rest can land mid-deferral. Everything else waits for the retry deadline,
        # which the timer owns.
        match assessment:
            case RestSatisfied(reason=reason, rested_for=rested_for):
                return self._satisfy(timer, reason, rested_for)
            case _:
                return NoAction("waiting for the retry deadline")

    def _satisfy(self, timer: BreakTimer, reason: str, rested_for: float) -> PolicyOutcome:
        # Detectors report what they saw; too short a rest is normal input, not a fault.
        try:
            timer.satisfy_break(rested_for)
        except InsufficientRestError as exc:
            return NoAction(str(exc))
        return BreakSatisfied(reason=reason, rested_for=rested_for)
