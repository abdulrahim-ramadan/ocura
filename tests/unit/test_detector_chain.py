from __future__ import annotations

from ocura.domain.context import (
    ContextAssessment,
    Deferral,
    DetectorChain,
    Interruptible,
    RestSatisfied,
    combine,
)
from ocura.domain.timer import BreakTimer, TimerSnapshot


class Fixed:
    def __init__(self, assessment: ContextAssessment) -> None:
        self.assessment = assessment
        self.calls = 0

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        self.calls += 1
        return self.assessment


def test_no_detectors_means_nothing_in_the_way():
    assert combine([]) == Interruptible()


def test_all_clear_is_interruptible():
    assert combine([Interruptible(), Interruptible()]) == Interruptible()


def test_rest_beats_deferral():
    rest = RestSatisfied(reason="session lock", rested_for=900.0)
    assert combine([Deferral(reason="fullscreen"), rest]) == rest


def test_rest_beats_deferral_regardless_of_order():
    rest = RestSatisfied(reason="session lock", rested_for=900.0)
    assert combine([rest, Deferral(reason="fullscreen")]) == rest


def test_the_longest_rest_wins():
    short = RestSatisfied(reason="brief", rested_for=60.0)
    long = RestSatisfied(reason="lunch", rested_for=3600.0)
    assert combine([short, long]) == long


def test_deferral_beats_interruptible_and_merges_reasons():
    outcome = combine(
        [Interruptible(), Deferral(reason="fullscreen"), Deferral(reason="idle for 300s")]
    )
    assert outcome == Deferral(reason="fullscreen, idle for 300s", retry_after=None)


def test_shortest_explicit_retry_wins():
    outcome = combine(
        [
            Deferral(reason="fullscreen", retry_after=600.0),
            Deferral(reason="idle", retry_after=30.0),
            Deferral(reason="screensaver"),
        ]
    )
    assert outcome.retry_after == 30.0


def test_retry_stays_none_when_no_detector_names_one():
    outcome = combine([Deferral(reason="fullscreen"), Deferral(reason="idle")])
    assert outcome.retry_after is None


def test_chain_consults_every_detector(due_timer: BreakTimer):
    detectors = [Fixed(Interruptible()), Fixed(Deferral(reason="fullscreen"))]
    chain = DetectorChain(*detectors)

    assert chain.assess(due_timer.snapshot()) == Deferral(reason="fullscreen", retry_after=None)
    assert [d.calls for d in detectors] == [1, 1]


def test_chain_order_does_not_change_the_result(due_timer: BreakTimer):
    rest = RestSatisfied(reason="session lock", rested_for=900.0)
    forwards = DetectorChain(Fixed(Deferral(reason="fullscreen")), Fixed(rest))
    backwards = DetectorChain(Fixed(rest), Fixed(Deferral(reason="fullscreen")))
    snapshot = due_timer.snapshot()

    assert forwards.assess(snapshot) == backwards.assess(snapshot) == rest


def test_an_empty_chain_never_blocks(due_timer: BreakTimer):
    assert DetectorChain().assess(due_timer.snapshot()) == Interruptible()
