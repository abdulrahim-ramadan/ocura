"""What the surrounding environment has to say about interrupting the user.

P0 defines the vocabulary only. P1 supplies the detectors (session lock, full
screen, idle) that produce these assessments; nothing here knows Windows exists.

The two non-trivial answers are deliberately different types, because they mean
different things and must not be collapsed into one boolean:

    Deferral      the break is due but now is a bad moment; the break stays owed
    RestSatisfied the environment already gave the user a real break; it is paid
"""

from __future__ import annotations

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
