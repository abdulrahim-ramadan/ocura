from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ocura.application.presenter import SessionView


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
        status_layout.setContentsMargins(24, 24, 24, 24)
        status_layout.setSpacing(8)
        status_layout.addWidget(self._headline)
        status_layout.addWidget(self._display)
        status_layout.addWidget(self._detail)
        status_layout.addSpacing(8)
        status_layout.addWidget(self._progress)
        status_layout.addSpacing(8)
        status_layout.addWidget(self._waiting)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self._start)
        buttons.addWidget(self._pause)
        buttons.addWidget(self._break)
        buttons.addStretch(1)

        metrics = _card()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(24, 20, 24, 20)
        metrics_layout.setSpacing(36)
        for widget, caption in (
            (self._breaks_taken, "Breaks taken"),
            (self._rests_credited, "Rests credited"),
            (self._focus_elapsed, "At the screen"),
        ):
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(widget)
            column.addWidget(_label(caption, "MetricLabel"))
            metrics_layout.addLayout(column)
        metrics_layout.addStretch(1)

        events = _card()
        events_layout = QVBoxLayout(events)
        events_layout.setContentsMargins(24, 20, 24, 20)
        events_layout.setSpacing(8)
        events_layout.addWidget(_label("This session", "SectionTitle"))
        events_layout.addWidget(self._events)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(16)
        root.addWidget(status)
        root.addLayout(buttons)
        root.addWidget(metrics)
        root.addWidget(events, 1)

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
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(8)
        card_layout.addWidget(_label(title, "Headline"))
        card_layout.addWidget(_label(promise, "Placeholder"))

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.addWidget(card)
        root.addStretch(1)
