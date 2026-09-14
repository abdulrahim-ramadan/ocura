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

#: How many times the eyelid closes across a break. Three is enough to be an
#: instruction and few enough not to become a rhythm.
BLINK_COUNT = 3

#: A blink occupies this fraction of the break, centred on each of its moments.
BLINK_SPAN = 0.08


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
        """Soften a state change. Called on change only, never on every tick.

        The effect is removed the moment the fade ends, and this is not tidiness.
        A QGraphicsEffect renders its widget through a cached source pixmap, and
        a child repainting on its own — a label whose text changes every second —
        does not invalidate that cache. Leaving the effect attached therefore
        composites the cached frame with the live one: the dashboard drew
        "Focusing" underneath the countdown, and two different countdown values
        at once, for as long as the window stayed open.

        Nothing is faded that is not being replaced, and nothing stays faded.
        """
        if not self.enabled or widget.graphicsEffect() is not None:
            # A fade is already running. Stacking effects is what left one
            # attached permanently in the first place.
            return

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        # Parented to the widget, not to the effect: the finished handler
        # deletes the effect, and an animation must not be destroyed while it is
        # emitting.
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._run(animation, MIN_FADE_FROM, 1.0, FADE_MS, QEasingCurve.Type.OutCubic)

    def recede(self, shape: QWidget, seconds: float, to: float) -> None:
        """Shrink the focus shape once, across the whole break.

        One interpolation with a single loop, not a pulse. It ends when the
        break ends and the widget is destroyed with the overlay.
        """
        if not self.enabled or seconds <= 0:
            shape.setProperty("scale", to)
            return
        self._run(
            QPropertyAnimation(shape, b"scale", shape),
            1.0,
            to,
            int(seconds * 1000),
            QEasingCurve.Type.InOutSine,
        )

    def blink(self, cue: QWidget, seconds: float) -> None:
        """Three eyelid closes spaced across the break.

        Key frames on one animation rather than a repeating timer or an
        animation group: three closes are three key frames, and when the single
        run finishes there is nothing left scheduled.
        """
        if not self.enabled or seconds <= 0:
            cue.setProperty("openness", 1.0)
            return

        animation = QPropertyAnimation(cue, b"openness", cue)
        animation.setDuration(int(seconds * 1000))
        animation.setKeyValueAt(0.0, 1.0)
        for index in range(BLINK_COUNT):
            # Spread the closes over the middle of the break so neither the
            # first nor the last lands exactly on an edge.
            at = (index + 1) / (BLINK_COUNT + 1)
            animation.setKeyValueAt(max(0.0, at - BLINK_SPAN), 1.0)
            animation.setKeyValueAt(at, 0.0)
            animation.setKeyValueAt(min(1.0, at + BLINK_SPAN), 1.0)
        animation.setKeyValueAt(1.0, 1.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.setLoopCount(1)
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

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
