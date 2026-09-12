"""What the surrounding environment has to say about interrupting the user.

P0 defines the vocabulary only. P1 supplies the detectors (session lock, full
screen, idle) that produce these assessments; nothing here knows Windows exists.

The two non-trivial answers are deliberately different types, because they mean
different things and must not be collapsed into one boolean:

    Deferral      the break is due but now is a bad moment; the break stays owed
    RestSatisfied the environment already gave the user a real break; it is paid
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ocura.domain.timer import TimerSnapshot


@dataclass(frozen=True, slots=True)
class Interruptible:
    """Nothing stands in the way of a break right now."""


@dataclass(frozen=True, slots=True)
class Deferral:
    reason: str
    #: Seconds until the break should be offered again; None uses the schedule.
    retry_after: float | None = None


@dataclass(frozen=True, slots=True)
class RestSatisfied:
    reason: str
    #: How long the observed rest lasted, in seconds. Evidence, never a score.
    rested_for: float


ContextAssessment = Interruptible | Deferral | RestSatisfied

INTERRUPTIBLE = Interruptible()


@runtime_checkable
class ContextSource(Protocol):
    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment: ...


#: A detector is a context source that speaks for exactly one signal. Same
#: contract, narrower remit; DetectorChain turns several of them into one source.
ContextDetector = ContextSource


def combine(assessments: Iterable[ContextAssessment]) -> ContextAssessment:
    """Reduce several detectors' opinions to the one the policy will act on.

    Rest beats deferral beats interruptible. Rest wins because it discharges the
    break outright: if the user genuinely rested, a bad moment to interrupt is
    moot, there is nothing left to interrupt them for.
    """
    rests: list[RestSatisfied] = []
    deferrals: list[Deferral] = []
    for assessment in assessments:
        match assessment:
            case RestSatisfied():
                rests.append(assessment)
            case Deferral():
                deferrals.append(assessment)
            case _:
                pass

    if rests:
        # The longest observed rest is the most defensible evidence, and the one
        # most likely to clear the domain's break_duration veto.
        return max(rests, key=lambda rest: rest.rested_for)
    if deferrals:
        # Shortest explicit retry wins: asking again too early costs a wasted
        # question, asking too late costs the moment the user became free.
        explicit = [d.retry_after for d in deferrals if d.retry_after is not None]
        return Deferral(
            reason=", ".join(d.reason for d in deferrals),
            retry_after=min(explicit) if explicit else None,
        )
    return INTERRUPTIBLE


class DetectorChain:
    """Consults every detector on every assessment; order does not change the result."""

    def __init__(self, *detectors: ContextDetector) -> None:
        self._detectors = detectors

    @property
    def detectors(self) -> tuple[ContextDetector, ...]:
        return self._detectors

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        return combine(detector.assess(snapshot) for detector in self._detectors)
