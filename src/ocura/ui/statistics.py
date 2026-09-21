"""The statistics page: four numbers, a week, and the record of when Ocura waited.

Nothing here computes anything. Every number and every sentence arrives already
formed on a `StatisticsPageView`, for the same reason the dashboard works that
way — the language rules are a product decision, and a widget test cannot
assert them without a display.

**The chart is Qt, not a charting library.** A dependency for one bar chart
would be a dependency to package, license, audit and carry into every build, in
exchange for a rounded rectangle. What it costs instead is `Bar` below, which
is a `QWidget` that fills part of itself.

Colour is not written in Python anywhere on this page. `Bar` and `TodayBar`
take theirs from the palette QSS puts on them, which is the same route the
break overlay's shape takes — so both themes and any future one are a token
change, exactly as P6 needs.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ocura.application.i18n import QT_TRANSLATE_NOOP, translate
from ocura.application.statistics import StatisticsPageView, StatisticsPresenter
from ocura.ui.theme import LAYOUT, SPACING
from ocura.ui.views import _card, _label

#: Tall enough for the shape of a week to be legible, short enough that the
#: deferral list below it is on the screen at the same time in a default-sized
#: window. That list is the reason this page exists; a chart that pushed it
#: under the fold would have made it a footnote, which is exactly what it is
#: not. Measured against MIN_SIZE rather than chosen by eye.
CHART_HEIGHT = 130

#: A day with time on it always draws something. Without a floor, a twenty
#: minute day next to an eight hour one rounds to nothing and reads as a day
#: when Ocura was not running, which is a different fact.
MIN_BAR_PIXELS = 3

#: The deferral rows are a proportion of the commonest reason, drawn as a track
#: behind the label rather than as a second chart.
REASON_BAR_HEIGHT = 6


def _empty(layout) -> None:
    """Take every widget out of a layout and off the screen with it.

    `takeAt` removes the layout entry but leaves the widget parented, so it
    keeps painting at its old geometry until the deferred delete is processed —
    a repopulated chart drawn over the top of the one before it. Unparenting
    first is what actually removes it; `deleteLater` is then only about when
    the memory goes, which is Qt's business rather than this widget's.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class Bar(QWidget):
    """A proportion of itself, filled in one colour.

    Vertical by default, which is a column of the week chart growing from the
    bottom; horizontal for the deferral rows, where the proportion runs along
    the row the reason is written on.

    Both directions live in one widget because they are the same drawing and
    the same colour rule, and two classes would be two places for the palette
    trick to be got right. That trick: the object name picks up a colour from
    the token set through QSS and `paintEvent` reads it back off the palette,
    so this file names no colour and P6 can restyle the chart without opening
    it.
    """

    def __init__(
        self,
        today: bool = False,
        horizontal: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TodayBar" if today else "Bar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._horizontal = horizontal
        self._fraction = 0.0

    def set_fraction(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event) -> None:
        del event
        if self._fraction <= 0.0:
            return

        colour: QColor = self.palette().color(QPalette.ColorRole.WindowText)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        if self._horizontal:
            width = max(MIN_BAR_PIXELS, round(self.width() * self._fraction))
            # From the edge the row is read from. A proportion that grows away
            # from its own label is not a proportion the eye can compare, and
            # Qt does not mirror what a paint event draws — only what a layout
            # places.
            left = self.width() - width if self.isRightToLeft() else 0
            painter.drawRoundedRect(left, 0, width, self.height(), 3, 3)
        else:
            height = max(MIN_BAR_PIXELS, round(self.height() * self._fraction))
            painter.drawRoundedRect(0, self.height() - height, self.width(), height, 3, 3)
        painter.end()


class WeekChart(QWidget):
    """Seven columns: a value, a bar, a weekday, a date. Rebuilt per render.

    Rebuilt rather than updated because which column is today changes at
    midnight and the widget cannot know when that was. Seven columns is a
    trivial amount of work and it removes a whole class of stale-highlight bug.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(SPACING.s)
        self._grid.setVerticalSpacing(SPACING.xs)
        self.setMinimumHeight(CHART_HEIGHT)

    def render(self, view: StatisticsPageView) -> None:
        _empty(self._grid)

        for column, bar in enumerate(view.bars):
            value = _label(bar.value_text, "BarValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setWordWrap(False)

            painted = Bar(today=bar.is_today)
            painted.set_fraction(bar.fraction)

            weekday = _label(bar.weekday, "BarLabel" if not bar.is_today else "BarLabelToday")
            weekday.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekday.setWordWrap(False)

            day = _label(bar.day_of_month, "BarDate")
            day.setAlignment(Qt.AlignmentFlag.AlignCenter)
            day.setWordWrap(False)

            self._grid.addWidget(value, 0, column)
            self._grid.addWidget(painted, 1, column)
            self._grid.addWidget(weekday, 2, column)
            self._grid.addWidget(day, 3, column)

        # Only the bars absorb height; the three label rows take what their
        # text needs, so a short window shrinks the chart rather than clipping
        # the dates off the bottom of it.
        self._grid.setRowStretch(1, 1)


class ReasonRow(QWidget):
    """One deferral reason: what it was, how often, and how it compares.

    The proportion is drawn as a quiet track rather than as a number, because
    the question this answers is "which of these is the one that keeps
    happening" and a row of percentages answers it more slowly.
    """

    def __init__(self, reason: str, count_text: str, fraction: float) -> None:
        super().__init__()

        # Horizontal: the proportion runs along the row, so the commonest
        # reason is the longest line and the eye finds it without reading a
        # single number.
        track = Bar(horizontal=True)
        track.setObjectName("ReasonBar")
        track.set_fraction(fraction)
        track.setFixedHeight(REASON_BAR_HEIGHT)
        track.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(SPACING.s)
        heading.addWidget(_label(reason, "ReasonLabel"), 1)
        heading.addWidget(_label(count_text, "ReasonCount"))

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING.xs)
        column.addLayout(heading)
        column.addWidget(track)


class StatisticsPage(QWidget):
    """Renders a StatisticsPageView. Computes nothing, decides nothing."""

    def __init__(
        self, presenter: StatisticsPresenter | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._presenter = presenter or StatisticsPresenter()

        self._headline = _label("", "Headline")
        self._subheading = _label("", "Detail")
        self._empty = _label("", "Placeholder")
        self._chart_note = _label("", "Placeholder")

        self._today = _label("—", "Metric")
        self._week = _label("—", "Metric")
        self._breaks = _label("0", "Metric")
        self._average = _label("—", "Metric")

        self._chart = WeekChart()
        self._chart_card = _card()
        self._metrics = _card()
        self._reasons_title = _label("", "SectionTitle")
        self._reasons_note = _label("", "Detail")
        self._reasons_holder = QVBoxLayout()
        self._reasons_holder.setContentsMargins(0, 0, 0, 0)
        self._reasons_holder.setSpacing(SPACING.sm)

        self._build()
        self.retranslate()
        # Rendered once on construction so the page is correct before anyone
        # navigates to it. Without this it exists for a moment showing default
        # label text, which a screenshot or a test would catch as real content.
        self.refresh()

    def _build(self) -> None:
        # A page title rather than a card. Four stacked cards do not fit a
        # default-sized window, and of the four this is the only one that is
        # purely a heading — giving up its border is what keeps the deferral
        # list on screen without shrinking the chart into a sparkline.
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(SPACING.xs, 0, SPACING.xs, 0)
        header_layout.setSpacing(SPACING.s)
        header_layout.addWidget(self._headline)
        header_layout.addWidget(self._subheading)
        header_layout.addWidget(self._empty)

        metrics_layout = QHBoxLayout(self._metrics)
        metrics_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        metrics_layout.setSpacing(SPACING.xl)
        self._captions: list[tuple[object, str]] = []
        for widget, caption in (
            (self._today, QT_TRANSLATE_NOOP("StatisticsPage", "At the screen today")),
            (self._week, QT_TRANSLATE_NOOP("StatisticsPage", "This week")),
            (self._breaks, QT_TRANSLATE_NOOP("StatisticsPage", "Breaks taken")),
            (self._average, QT_TRANSLATE_NOOP("StatisticsPage", "Average focus block")),
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

        chart_layout = QVBoxLayout(self._chart_card)
        chart_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.m)
        chart_layout.setSpacing(SPACING.sm)
        self._chart_title = _label("", "SectionTitle")
        chart_layout.addWidget(self._chart_title)
        chart_layout.addWidget(self._chart, 1)

        # The deferral card is the reason this page exists: it is the one that
        # answers "it interrupted me too often" with evidence. It gets the
        # bottom of the column, which is where the eye stops, and it is a full
        # card rather than a line under the chart.
        reasons = _card()
        reasons_layout = QVBoxLayout(reasons)
        reasons_layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.lg)
        reasons_layout.setSpacing(SPACING.sm)
        reasons_layout.addWidget(self._reasons_title)
        reasons_layout.addWidget(self._reasons_note)
        reasons_layout.addSpacing(SPACING.xs)
        reasons_layout.addLayout(self._reasons_holder)

        for card in (header, self._metrics, reasons):
            card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        content = QWidget()
        content.setObjectName("Content")
        content.setMaximumWidth(LAYOUT.content_max_width)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING.m)
        column.addWidget(header)
        column.addWidget(self._metrics)
        column.addWidget(self._chart_card)
        column.addWidget(self._chart_note)
        column.addWidget(reasons)
        column.addStretch(1)

        # Scrolled and width-capped for the reasons set out in DashboardView:
        # a squeezed column draws text outside its own box, and there is no
        # minimum window size that prevents it.
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

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.addWidget(scroller, 1)
        root.addStretch(0)

    def retranslate(self) -> None:
        """The page's own labels. Everything else arrives already translated.

        The headline, the notes and the deferral reasons are the presenter's,
        computed fresh on every `refresh`, so a language change reaches them
        through the query rather than through here.
        """
        for label, caption in self._captions:
            label.setText(translate("StatisticsPage", caption))
        self._chart_title.setText(self.tr("At the screen, by day"))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
            self.refresh()
        super().changeEvent(event)

    def refresh(self) -> None:
        """Re-read the window and render it. Called when the page is opened."""
        self.render(self._presenter.view())

    def render(self, view: StatisticsPageView) -> None:
        self._headline.setText(view.headline)
        self._subheading.setText(view.subheading)

        self._empty.setText(view.empty_message)
        self._empty.setVisible(view.empty)
        self._subheading.setVisible(not view.empty)

        # An empty chart with labelled axes and no bars in it is a worse lie
        # than a sentence saying there is nothing yet: it looks like a reading
        # of zero rather than an absence of readings.
        self._metrics.setVisible(not view.empty)
        # Two separate questions. There is nothing at all to show, and there is
        # nothing to *chart* — a week with breaks in it but no finished focus
        # block is the second without being the first.
        self._chart_card.setVisible(not view.empty and view.chart_visible)
        self._chart_note.setText(view.chart_note)
        self._chart_note.setVisible(not view.empty and not view.chart_visible)

        self._today.setText(view.today_text)
        self._week.setText(view.week_text)
        self._breaks.setText(view.breaks_text)
        self._average.setText(view.average_focus_text)
        self._chart.render(view)

        self._reasons_title.setText(view.deferrals_title)
        self._reasons_note.setText(view.deferrals_note)

        _empty(self._reasons_holder)
        for line in view.deferrals:
            self._reasons_holder.addWidget(ReasonRow(line.reason, line.count_text, line.fraction))
