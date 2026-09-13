"""Motion policy, and the only place animations are created.

Ocura's dashboard is a two-second glance surface and must be still. Peripheral
motion pulls the eye involuntarily, so an eye-care app that animates
continuously is interrupting the user without asking — the exact thing the whole
product is built to avoid.

Every animation here therefore:

  - is triggered by a state change and by nothing else
  - runs once and stops; nothing loops, nothing pulses, nothing breathes
  - is skipped entirely when the OS reports reduced motion

The countdown fill is the one continuous-looking animation, and it is not a
loop: each tick starts a single interpolation to the new value, which happens to
arrive before the previous one ends.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QProgressBar, QWidget

logger = logging.getLogger(__name__)

FADE_MS = 200
#: Just under the tick, so the fill arrives as the next one starts and the bar
#: glides instead of stepping.
FILL_MS = 950

#: Below this the fade reads as a flicker rather than a transition.
MIN_FADE_FROM = 0.35


def reduced_motion() -> bool:
    try:
        from ocura.infrastructure.windows import api
    except (ImportError, OSError):
        return False
    return not api.animations_enabled()


class Motion:
    """Enabled once at startup; widgets ask it rather than deciding for themselves."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    @classmethod
    def from_system(cls) -> Motion:
        enabled = not reduced_motion()
        if not enabled:
            logger.info("reduced motion is on; animations are disabled")
        return cls(enabled)

    def fill(self, bar: QProgressBar, value: int) -> None:
        """Glide the countdown to its new value instead of stepping to it."""
        if not self.enabled:
            bar.setValue(value)
            return
        if value < bar.value():
            # A reset (break finished, session restarted) should not rewind
            # visibly; only forward progress is worth animating.
            bar.setValue(value)
            return
        self._run(
            QPropertyAnimation(bar, b"value", bar),
            bar.value(),
            value,
            FILL_MS,
            QEasingCurve.Type.Linear,
        )

    def fade_in(self, widget: QWidget) -> None:
        """Soften a state change. Called on change only, never on every tick."""
        if not self.enabled:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        self._run(
            QPropertyAnimation(effect, b"opacity", effect),
            MIN_FADE_FROM,
            1.0,
            FADE_MS,
            QEasingCurve.Type.OutCubic,
        )

    @staticmethod
    def _run(
        animation: QPropertyAnimation,
        start: float,
        end: float,
        duration: int,
        easing: QEasingCurve.Type,
    ) -> None:
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(duration)
        animation.setEasingCurve(easing)
        # Explicit: the default is already 1, and anything else would be a loop.
        animation.setLoopCount(1)
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


#: Configured once by the application; widgets read it. A module-level object
#: rather than a constructor argument threaded through every widget.
MOTION = Motion()


def configure(motion: Motion) -> None:
    MOTION.enabled = motion.enabled
