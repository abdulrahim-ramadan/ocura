from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ocura.application.presenter import SessionView
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

        self._waiting = _label("", "WaitingNote")
        self._waiting.hide()

        self._start = QPushButton("Start session")
        self._start.setObjectName("Primary")
        self._pause = QPushButton("Pause reminders")
        self._break = QPushButton("Take a break now")

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

        self._build()

    def _build(self) -> None:
        status = _card()
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

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING.s)
        buttons.addWidget(self._start)
        buttons.addWidget(self._pause)
        buttons.addWidget(self._break)
        buttons.addStretch(1)

        metrics = _card()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        metrics_layout.setSpacing(SPACING.xl)
        for widget, caption in (
            (self._breaks_taken, "Breaks taken"),
            (self._rests_credited, "Rests credited"),
            (self._focus_elapsed, "At the screen"),
        ):
            column = QVBoxLayout()
            column.setSpacing(SPACING.xs)
            column.addWidget(widget)
            column.addWidget(_label(caption, "MetricLabel"))
            metrics_layout.addLayout(column)
        metrics_layout.addStretch(1)

        events = _card()
        events_layout = QVBoxLayout(events)
        events_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        events_layout.setSpacing(SPACING.sm)
        events_layout.addWidget(_label("This session", "SectionTitle"))
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
        # The column takes the stretch so it grows to its cap, and a zero-weight
        # spacer absorbs whatever is left. Without the spacer Qt centres a
        # size-capped widget in its cell and the column floats away from the
        # sidebar; with the spacer weighted, the column never reaches the cap.
        root = QHBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.addWidget(content, 1)
        root.addStretch(0)

    def render(self, view: SessionView) -> None:
        self._headline.setText(view.headline)
        self._display.setText(view.countdown_text)
        self._detail.setText(view.detail)
        self._progress.setValue(int(view.progress * 1000))

        if view.waiting_reason:
            self._waiting.setText(f"Waiting — {view.waiting_reason}")
            self._waiting.show()
        else:
            self._waiting.hide()

        self._start.setText("Start session" if not view.running else "Restart session")
        self._pause.setText("Resume reminders" if view.paused else "Pause reminders")
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


class PlaceholderView(QWidget):
    """An honest empty section. No invented numbers, no sample data."""

    def __init__(self, title: str, promise: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        card = _card()
        card.setMaximumWidth(LAYOUT.content_max_width)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        card_layout.setSpacing(SPACING.sm)
        card_layout.addWidget(_label(title, "Headline"))
        card_layout.addWidget(_label(promise, "Placeholder"))

        # The card needs a real width before a wrapped label can report the height
        # it needs, so give it a row of its own rather than an alignment flag.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(card, 1)
        row.addStretch(0)

        # An empty section is centred rather than pinned to the top of a void.
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)
