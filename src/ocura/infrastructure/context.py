from __future__ import annotations

from ocura.domain.context import INTERRUPTIBLE, ContextAssessment
from ocura.domain.timer import TimerSnapshot


class AlwaysInterruptible:
    """P0 has no detectors. Until P1 lands, every moment is treated as a fine one."""

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        return INTERRUPTIBLE
