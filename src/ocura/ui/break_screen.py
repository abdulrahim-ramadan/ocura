"""What the break overlay actually shows.

Dim, warm, and low contrast. The screen exists to rest the eye, so it is the
one surface that stays dark in the light theme too — a bright white panel at
the end of a focus block would undo the break it is announcing.

Three rules shape everything below, and each of them is a rule because the
obvious alternative contradicts the screen's purpose:

*Nothing here is a light source.* The focus shape sits at roughly a quarter of
the background's remove and fades out radially, so it has no edge. A hard
circle is a luminance step, and a luminance step is something for the eye to
fixate on, which is the opposite of looking into the distance.

*The instruction gets its presence from size, not from brightness.* One
sentence at the top of the type scale, a countdown small enough to ignore, and
controls that are quiet but large enough to look deliberate.

*Related things sit together.* The shape, the cue and the text are one optical
group in the upper half; the empty space belongs at the outer edges, not
between elements that belong to each other.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPalette, QRadialGradient
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ocura.application.presenter import SessionView
from ocura.ui.motion import MOTION
from ocura.ui.theme import SPACING

#: The band the shape is given, as a fraction of the overlay's height, and at
#: full scale its painted extent as well — the box hugs the shape rather than
#: containing it. A box larger than what it draws put two hundred pixels of
#: nothing between the shape and its own instruction, which is what made the
#: text look stranded at the bottom of the screen.
#:
#: Taken from the overlay's height rather than from whatever the layout has
#: left over, so the shape is the same size on a display whatever the text
#: below it does.
SHAPE_BAND = 0.26

#: How far it recedes by the end of the break.
SHAPE_MIN_SCALE = 0.35

#: Radial stops, from the centre outwards, as (position, alpha). Solid well
#: past the middle and gone by the rim: the shape is a disc with an edge that
#: cannot be located, not a blur. A findable edge is a luminance step, and a
#: luminance step is what the eye fixates on instead of the distance.
SHAPE_FALLOFF = ((0.0, 1.0), (0.60, 1.0), (0.78, 0.70), (0.90, 0.28), (1.0, 0.0))

#: The cue at rest, as a fraction of the overlay's width. About a third: a
#: full-width line is a divider, and a divider is furniture the eye stops
#: seeing after the first blink.
CUE_SPAN = 0.33

#: Thick enough to read as a lid rather than as a rule.
CUE_THICKNESS = SPACING.s

#: What is left of it between blinks. Not zero — a cue that vanished entirely
#: would have to arrive from nowhere — but far below the threshold where a
#: still line starts to look like part of the layout.
CUE_REST_ALPHA = 0.07

#: How quickly it becomes fully visible once it starts to close. Past the first
#: third of the movement it is at full strength, so the closing reads as a lid
#: coming down rather than as something fading up.
CUE_RAMP = 3.0

#: Stretch weights for the empty space above and below the group. Unequal on
#: purpose: the group sits in the upper third, which is where a distant object
#: would be, and the larger share of the emptiness falls below it.
EDGE_TOP_STRETCH = 2
EDGE_BOTTOM_STRETCH = 4


class FocusShape(QWidget):
    """A soft circle that recedes across the break, guiding focus outward.

    Painted rather than styled because its size changes continuously and QSS
    has no radial gradient with an alpha falloff. Its colour still comes from
    the token set: QSS sets the palette on #FocusShape and the paint event
    reads it back, so no colour is written in Python.
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

        extent = min(self.width(), self.height()) * self._scale
        if extent <= 0:
            return
        radius = extent / 2
        centre = QPointF(self.rect().center())

        gradient = QRadialGradient(centre, radius)
        for position, alpha in SHAPE_FALLOFF:
            stop = QColor(colour)
            stop.setAlphaF(colour.alphaF() * alpha)
            gradient.setColorAt(position, stop)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(centre, radius, radius)


class BlinkCue(QWidget):
    """A short thick line that closes like an eyelid and opens again. Wordless.

    Three closes spaced across the break, driven by one animation with key
    frames rather than by a repeating timer — see the motion policy.

    A lid does not dim, it meets in the middle, so the close is geometry: the
    line shortens from both ends towards its centre. What fades is only its
    presence between blinks, because a line that sat there at full strength
    would be read once as a divider and then never looked at again.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BlinkCue")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(SPACING.m)
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

        width = self.width() * CUE_SPAN * self._openness
        if width <= 0:
            return

        closing = min(1.0, (1.0 - self._openness) * CUE_RAMP)
        stroke = QColor(colour)
        stroke.setAlphaF(colour.alphaF() * (CUE_REST_ALPHA + (1.0 - CUE_REST_ALPHA) * closing))

        height = min(float(CUE_THICKNESS), width)
        centre = QPointF(self.rect().center())

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(stroke)
        painter.drawRoundedRect(
            centre.x() - width / 2,
            centre.y() - height / 2,
            width,
            height,
            height / 2,
            height / 2,
        )


class BreakScreen(QWidget):
    """The content of one overlay window. Renders a SessionView, decides nothing."""

    skipRequested = Signal()
    snoozeRequested = Signal()

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

        # The evidence behind the break, for whoever wants to know why they are
        # looking at this screen. Lowest contrast on it, at the far edge of it:
        # it must never pull the eye back down to the display it interrupted.
        self._tip = QLabel("")
        self._tip.setObjectName("BreakTip")
        self._tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tip.setWordWrap(True)

        # Skip says what it does and nothing about what it means. Ending a break
        # early is a legitimate choice and the screen has no opinion about it.
        self._skip = QPushButton("Skip")
        self._skip.setObjectName("BreakAction")
        self._skip.clicked.connect(self.skipRequested)

        self._snooze = QPushButton("Later")
        self._snooze.setObjectName("BreakAction")
        self._snooze.clicked.connect(self.snoozeRequested)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(SPACING.sm)
        self.actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.actions.addWidget(self._snooze)
        self.actions.addWidget(self._skip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        # Every gap below is stated on its own line. A uniform spacing would
        # put the same distance between the shape and its instruction as
        # between the instruction and the controls, which is what made the text
        # read as stranded from the shape rather than as belonging to it.
        layout.setSpacing(0)

        layout.addStretch(EDGE_TOP_STRETCH)
        layout.addWidget(self.shape)
        layout.addSpacing(SPACING.xl)
        layout.addWidget(self.blink)
        layout.addSpacing(SPACING.xl)
        layout.addWidget(self._message)
        layout.addSpacing(SPACING.sm)
        layout.addWidget(self._countdown)
        layout.addSpacing(SPACING.xl)
        layout.addLayout(self.actions)
        # The only large gap inside the content, and it is what separates the
        # footnote from the screen rather than dead space inside the group.
        layout.addStretch(EDGE_BOTTOM_STRETCH)
        layout.addWidget(self._tip)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Sized against the screen, not against the leftover room in the
        # layout: the shape is the composition, so its diameter must not drift
        # when the tip wraps onto a second line.
        self.shape.setFixedHeight(round(self.height() * SHAPE_BAND))

    def begin(self, seconds: float) -> None:
        """Start the two animations once, for exactly the length of the break."""
        self.shape.set_scale(1.0)
        self.blink.set_openness(1.0)
        MOTION.recede(self.shape, seconds, SHAPE_MIN_SCALE)
        MOTION.blink(self.blink, seconds)

    def render(self, view: SessionView) -> None:
        self._countdown.setText(view.countdown_text)
        self._tip.setText(view.tip)
        # Past the cap the control goes away rather than sitting there disabled:
        # a greyed button invites a second look at something already decided.
        self._snooze.setVisible(view.can_snooze)
