from __future__ import annotations

from ocura.domain.context import ContextSource, Interruptible
from ocura.domain.timer import BreakTimer
from ocura.infrastructure.context import AlwaysInterruptible


def test_placeholder_source_satisfies_the_protocol():
    assert isinstance(AlwaysInterruptible(), ContextSource)


def test_placeholder_source_never_blocks_a_break(due_timer: BreakTimer):
    assert AlwaysInterruptible().assess(due_timer.snapshot()) == Interruptible()
