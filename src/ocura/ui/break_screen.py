"""What the break overlay actually shows.

Dim, warm, and low contrast. The screen exists to rest the eye, so it is the
one surface that stays dark in the light theme too — a bright white panel at
the end of a focus block would undo the break it is announcing.

The number is deliberately secondary. The focus shape carries the twenty
seconds; the digits are there for anyone who wants them, small and quiet.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ocura.application.presenter import SessionView
from ocura.ui.motion import MOTION
from ocura.ui.theme import SPACING

#: The shape spans this much of the shorter screen edge at its widest. Sized
#: against min(width, height) so a portrait monitor gets a circle rather than a
#: landscape composition stretched sideways.
SHAPE_SPAN = 0.42

#: How far it recedes by the end of the break.
SHAPE_MIN_SCALE = 0.35


class FocusShape(QWidget):
    """A soft circle that recedes across the break, guiding focus outward.

    Painted rather than styled because its size changes continuously. Its colour
    still comes from the token set: QSS sets the palette on #FocusShape and the
    paint event reads it back, so no colour is written in Python.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FocusShape")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scale = 1.0

    def sizeHint(self) -> QSize:
        return QSize(320, 320)

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, value: float) -> None:
        self._scale = max(0.0, min(1.0, value))
        self.update()

    #: Animated by ocura.ui.motion; nothing else writes it.
    scale = Property(float, get_scale, set_scale)

    def paintEvent(self, event) -> None:
        del event
        colour: QColor = self.palette().color(QPalette.ColorRole.WindowText)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)

        span = min(self.width(), self.height()) * SHAPE_SPAN * self._scale
        centre = self.rect().center()
        painter.drawEllipse(centre, span / 2, span / 2)


class BlinkCue(QWidget):
    """A wide line that closes like an eyelid and opens again. Wordless.

    Three closes spaced across the break, driven by one animation with key
    frames rather than by a repeating timer — see the motion policy.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FocusShape")  # shares the shape's token colour
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(SPACING.lg)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._openness = 1.0

    def get_openness(self) -> float:
        return self._openness

    def set_openness(self, value: float) -> None:
        self._openness = max(0.0, min(1.0, value))
        self.update()

    #: 1.0 is open, 0.0 is a closed lid.
    openness = Property(float, get_openness, set_openness)

    def paintEvent(self, event) -> None:
        del event
        colour: QColor = self.palette().color(QPalette.ColorRole.WindowText)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)

        # Closing narrows the line towards its centre rather than fading it, so
        # it reads as a lid rather than as a flash.
        width = self.width() * (0.25 + 0.35 * self._openness)
        height = max(2.0, self.height() * 0.18)
        centre = self.rect().center()
        painter.drawRoundedRect(
            centre.x() - width / 2, centre.y() - height / 2, width, height, height / 2, height / 2
        )


class BreakScreen(QWidget):
    """The content of one overlay window. Renders a SessionView, decides nothing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BreakScreen")
        self.setAutoFillBackground(True)

        self.shape = FocusShape()
        self.blink = BlinkCue()

        self._message = QLabel("Look at something far away")
        self._message.setObjectName("BreakMessage")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._countdown = QLabel("")
        self._countdown.setObjectName("BreakCountdown")
        self._countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(SPACING.sm)
        self.actions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.lg)
        # Stretches above and below: on a portrait screen the shape is sized by
        # the short edge, and the space left over stays empty. Empty space on a
        # break screen is the point.
        layout.addStretch(1)
        layout.addWidget(self.shape, 3)
        layout.addWidget(self.blink)
        layout.addWidget(self._message)
        layout.addWidget(self._countdown)
        layout.addLayout(self.actions)
        layout.addStretch(1)

    def begin(self, seconds: float) -> None:
        """Start the two animations once, for exactly the length of the break."""
        self.shape.set_scale(1.0)
        self.blink.set_openness(1.0)
        MOTION.recede(self.shape, seconds, SHAPE_MIN_SCALE)
        MOTION.blink(self.blink, seconds)

    def render(self, view: SessionView) -> None:
        self._countdown.setText(view.countdown_text)
