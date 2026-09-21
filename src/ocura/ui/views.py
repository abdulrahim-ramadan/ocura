from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ocura.application.i18n import QT_TRANSLATE_NOOP, translate
from ocura.application.presenter import SessionView
from ocura.ui.motion import MOTION
from ocura.ui.theme import LAYOUT, SPACING


def _card(object_name: str = "Card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    return frame


def _label(text: str = "", object_name: str = "") -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(True)
    return label


class DashboardView(QWidget):
    """Renders a SessionView. Holds no engine state and computes no text."""

    startRequested = Signal()
    pauseToggled = Signal()
    breakRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._headline = _label("", "Headline")
        self._display = _label("", "Display")
        self._detail = _label("", "Detail")
        self._progress = QProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._progress.setValue(0)  # default is minimum-1, which animates from -1

        self._waiting = _label("", "WaitingNote")
        self._waiting.hide()

        self._start = QPushButton()
        self._start.setObjectName("Primary")
        self._pause = QPushButton()
        self._break = QPushButton()

        self._start.clicked.connect(self.startRequested)
        self._pause.clicked.connect(self.pauseToggled)
        self._break.clicked.connect(self.breakRequested)

        self._breaks_taken = _label("0", "Metric")
        self._rests_credited = _label("0", "Metric")
        self._focus_elapsed = _label("0:00", "Metric")

        self._events = QListWidget()
        self._events.setObjectName("EventList")
        self._events.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._events.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._events.setMinimumHeight(SPACING.xl)
        self._last_headline = ""
        self._running = False
        self._paused = False

        self._build()

    def _build(self) -> None:
        status = self._status = _card()
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        status_layout.setSpacing(SPACING.s)
        status_layout.addWidget(self._headline)
        status_layout.addWidget(self._display)
        status_layout.addWidget(self._detail)
        status_layout.addSpacing(SPACING.m)
        status_layout.addWidget(self._progress)
        status_layout.addSpacing(SPACING.s)
        status_layout.addWidget(self._waiting)

        buttons = self._buttons = QHBoxLayout()
        buttons.setSpacing(SPACING.s)
        buttons.addWidget(self._start)
        buttons.addWidget(self._pause)
        buttons.addWidget(self._break)
        buttons.addStretch(1)

        metrics = _card()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        metrics_layout.setSpacing(SPACING.xl)
        self._captions: list[tuple[QLabel, str]] = []
        for widget, caption in (
            (self._breaks_taken, QT_TRANSLATE_NOOP("DashboardView", "Breaks taken")),
            (self._rests_credited, QT_TRANSLATE_NOOP("DashboardView", "Rests credited")),
            (self._focus_elapsed, QT_TRANSLATE_NOOP("DashboardView", "At the screen")),
        ):
            column = QVBoxLayout()
            column.setSpacing(SPACING.xs)
            column.addWidget(widget)
            label = _label("", "MetricLabel")
            # One line, whatever the language. The card takes exactly the
            # height its text needs, so a caption that wraps is a caption
            # drawn outside its own box — which is how "Durchschnittlicher
            # Fokusblock" lost its second line in a narrow window. Unwrapped,
            # it asks for the width it needs instead, and the page scrolls.
            label.setWordWrap(False)
            self._captions.append((label, caption))
            column.addWidget(label)
            metrics_layout.addLayout(column)
        metrics_layout.addStretch(1)

        # The status card and the metrics row take exactly the height their text
        # needs and no less. Without this the column over-subscribes the window,
        # every child is squeezed below its own minimum, and 44px digits are
        # drawn into a 20px box — which reads on screen as the headline and the
        # countdown printed on top of each other. Only the event list, which
        # scrolls, is allowed to absorb a shortfall.
        status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        metrics.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        events = _card()
        events.setMinimumHeight(SPACING.xl * 4)
        events_layout = QVBoxLayout(events)
        events_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        events_layout.setSpacing(SPACING.sm)
        self._events_title = _label("", "SectionTitle")
        events_layout.addWidget(self._events_title)
        events_layout.addWidget(self._events)

        content = QWidget()
        content.setObjectName("Content")
        # A maximised window is very wide and long lines are hard to read. Expanding
        # rather than Preferred, or the column sits at its size hint and never
        # reaches the cap.
        content.setMaximumWidth(LAYOUT.content_max_width)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING.m)
        column.addWidget(status)
        column.addLayout(buttons)
        column.addWidget(metrics)
        column.addWidget(events, 1)

        # Left-aligned rather than centred: the column stays anchored to the
        # sidebar instead of floating away from it as the window widens.
        # Scrolled, so a short or narrow window can never squeeze the column.
        # Squeezing is not benign here: Qt hands each child less height than its
        # text needs and the text is drawn outside its box, which on screen reads
        # as the headline and the countdown printed on top of each other. There
        # is no minimum window size that prevents it — a narrower window wraps
        # the detail line onto more lines and needs *more* height — so the fix
        # has to be structural rather than a number.
        scroller = QScrollArea()
        scroller.setObjectName("Page")
        scroller.setWidget(content)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        # As needed rather than always off. Off was right when every string was
        # English and fitted: it kept a long sentence wrapping instead of
        # sliding sideways. A translated interface is wider — the German
        # dashboard's three buttons do not fit the minimum window, and the
        # German week chart does not either — and a control that is simply not
        # on the screen is worse than a scrollbar. Wrapping text still wraps:
        # a bar appears only when something that cannot wrap, such as a row of
        # buttons, needs more room than the window has.
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # The column takes the stretch so it grows to its cap, and a zero-weight
        # spacer absorbs whatever is left. Without the spacer Qt centres a
        # size-capped widget in its cell and the column floats away from the
        # sidebar; with the spacer weighted, the column never reaches the cap.
        root = QHBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.addWidget(scroller, 1)
        root.addStretch(0)
        self.retranslate()

    def minimum_content_width(self) -> int:
        """The narrowest this page can be and still show all three controls.

        Buttons are the one thing on the page that cannot wrap, and their
        width is a fact about the language: "Erinnerungen pausieren" is half
        again as wide as "Pause reminders". The window asks for this after
        every language change rather than trusting a minimum size that was
        measured once, in English.
        """
        return self._buttons.sizeHint().width() + 2 * SPACING.lg

    def retranslate(self) -> None:
        """Re-set every string this widget owns, in the language now active.

        Qt posts a LanguageChange event to every widget when a translator is
        installed, and `changeEvent` turns that into this call. Text that came
        from a SessionView is not touched here — the presenter recomputes it on
        the next tick, and it is not this widget's to decide.
        """
        for label, caption in self._captions:
            label.setText(translate("DashboardView", caption))
        self._events_title.setText(self.tr("This session"))
        self._break.setText(self.tr("Take a break now"))
        self._retranslate_buttons()

    def _retranslate_buttons(self) -> None:
        """The two buttons whose label depends on state as well as language."""
        self._start.setText(
            self.tr("Restart session") if self._running else self.tr("Start session")
        )
        self._pause.setText(
            self.tr("Resume reminders") if self._paused else self.tr("Pause reminders")
        )

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    def render(self, view: SessionView) -> None:
        # Fade on a real state change only. Doing it every tick would be a
        # permanent flicker, which is the motion this app exists to avoid.
        if view.headline != self._last_headline:
            MOTION.fade_in(self._status)
            self._last_headline = view.headline

        self._headline.setText(view.headline)
        self._display.setText(view.countdown_text)
        self._detail.setText(view.detail)
        MOTION.fill(self._progress, int(view.progress * 1000))

        if view.waiting_reason:
            self._waiting.setText(self.tr("Waiting — %1").replace("%1", view.waiting_reason))
            self._waiting.show()
        else:
            self._waiting.hide()

        self._running, self._paused = view.running, view.paused
        self._retranslate_buttons()
        self._pause.setEnabled(view.running)
        self._break.setEnabled(view.can_take_break_now)

        self._breaks_taken.setText(str(view.breaks_taken))
        self._rests_credited.setText(str(view.rests_credited))
        self._focus_elapsed.setText(view.focus_elapsed_text)

        # Small and append-only; rebuilding is simpler than diffing and the list
        # is capped at MAX_EVENTS.
        if self._events.count() != len(view.events):
            self._events.clear()
            for line in view.events:
                self._events.addItem(f"{line.time_text}   {line.text}")
            self._events.scrollToBottom()
