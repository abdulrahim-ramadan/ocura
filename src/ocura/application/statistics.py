"""What the statistics page knows, and the words it says.

The shapes live here rather than in storage for the same reason `SessionEvent`
does: the layer that asks the question owns the answer's form, and the layer
that reads a database implements a protocol named up here. `StatisticsSource`
is that protocol. `ocura.infrastructure.storage.StatisticsStore` is the one
implementation that touches SQLite; `NullStatistics` is what runs when there is
nowhere to read from, and the page behaves identically with it.

The text lives here too, for the same reason `BreakPresenter` holds the
dashboard's language: the rules about it — informational, never accusatory, no
goals, no streaks, nothing that grades a day — are a product decision worth
testing, and a widget test cannot assert them without a display.

**What this page refuses to show.** No streaks. No goals. Nothing "missed" and
nothing "achieved". No percentage of breaks taken against a target, because
there is no target. No colour that sorts days into good and bad. A person
looking at this page should learn what happened and never be told how they did:
the moment a number has a score attached, the honest thing to do with it is to
game it, and a break taken to keep a number up is not a break.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from ocura.application.i18n import QT_TRANSLATE_NOOP, duration_text, duration_words, translate
from ocura.domain.schedule import BreakSchedule

#: Weekday names, abbreviated, indexed by `date.weekday()`. Written out and
#: marked rather than taken from `strftime("%a")`, which answers in the
#: process's C locale and would have put "Mon" under a German chart forever.
#: Qt's `QLocale` would answer correctly and cannot be reached from here — this
#: layer is banned from importing it — so the seven names go through the same
#: catalogue as every other word in the interface, where a translator can also
#: decide how short "Donnerstag" should be cut.
WEEKDAYS = (
    QT_TRANSLATE_NOOP("Calendar", "Mon"),
    QT_TRANSLATE_NOOP("Calendar", "Tue"),
    QT_TRANSLATE_NOOP("Calendar", "Wed"),
    QT_TRANSLATE_NOOP("Calendar", "Thu"),
    QT_TRANSLATE_NOOP("Calendar", "Fri"),
    QT_TRANSLATE_NOOP("Calendar", "Sat"),
    QT_TRANSLATE_NOOP("Calendar", "Sun"),
)

#: A week, which is the window the page reads and the one the chart draws. Long
#: enough to show a shape, short enough that every bar is a day the user still
#: remembers.
WINDOW_DAYS = 7


@dataclass(frozen=True, slots=True)
class DayTotals:
    """One local day. Zero-filled rather than absent: a day with nothing on it
    is a day that happened, and a chart that skipped it would compress the week
    into whichever days were busy."""

    day: date
    screen_seconds: float = 0.0
    breaks: int = 0
    focus_blocks: int = 0


@dataclass(frozen=True, slots=True)
class ReasonCount:
    """One reason Ocura waited, and how often it did."""

    reason: str
    count: int


@dataclass(frozen=True, slots=True)
class Statistics:
    """The window, already aggregated. Carries no text and no opinion."""

    #: Oldest first, always exactly the window length, today last.
    days: tuple[DayTotals, ...]
    #: Commonest first.
    deferrals: tuple[ReasonCount, ...] = ()

    @property
    def today(self) -> DayTotals:
        return self.days[-1]

    @property
    def screen_seconds(self) -> float:
        return sum(day.screen_seconds for day in self.days)

    @property
    def breaks(self) -> int:
        return sum(day.breaks for day in self.days)

    @property
    def focus_blocks(self) -> int:
        return sum(day.focus_blocks for day in self.days)

    @property
    def average_focus_seconds(self) -> float | None:
        """None rather than zero when nothing has been measured.

        Zero is a number somebody could read as "your focus blocks are zero
        minutes long". Nothing measured is not a measurement of nothing.
        """
        if not self.focus_blocks:
            return None
        return self.screen_seconds / self.focus_blocks

    @property
    def is_empty(self) -> bool:
        return not self.focus_blocks and not self.breaks and not self.deferrals


@runtime_checkable
class StatisticsSource(Protocol):
    """Somewhere to read a window of history from. Read-only from up here."""

    def read(self, days: int = WINDOW_DAYS) -> Statistics: ...


class NullStatistics:
    """There is no history to read. The page says so and nothing else breaks.

    The same bargain as `NullJournal`: a database that could not be opened
    costs the user their history and never anything the product does.
    """

    def __init__(self, today: date | None = None) -> None:
        self._today = today

    def read(self, days: int = WINDOW_DAYS) -> Statistics:
        return empty_window(self._today or date.today(), days)


def empty_window(today: date, days: int = WINDOW_DAYS) -> Statistics:
    """A window of zero-filled days ending today. The shape of no history."""
    from datetime import timedelta

    first = today - timedelta(days=days - 1)
    return Statistics(
        days=tuple(DayTotals(day=first + timedelta(days=offset)) for offset in range(days))
    )


# --- the words -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DayBar:
    """One column of the week chart, already in the words it should say."""

    weekday: str
    day_of_month: str
    value_text: str
    #: Of the tallest day in the window, so the chart is read against itself
    #: rather than against a target. There is no target.
    fraction: float
    is_today: bool


@dataclass(frozen=True, slots=True)
class DeferralLine:
    reason: str
    count_text: str
    #: Of the commonest reason, so the row reads as a proportion of the others.
    fraction: float


@dataclass(frozen=True, slots=True)
class StatisticsPageView:
    """Everything the page renders. No widget computes a number or a sentence."""

    headline: str
    subheading: str

    #: Nothing has happened yet. The page says so plainly and says when there
    #: will be something, rather than drawing an empty chart with no bars in it.
    empty: bool
    empty_message: str

    today_text: str
    week_text: str
    breaks_text: str
    average_focus_text: str

    #: There is at least one day with time on it. Separate from `empty`,
    #: because a week can have breaks in it and still have no finished focus
    #: block to chart — which is exactly what a database written by someone
    #: who only ever used "Take a break now" looks like. Seven bars of zero
    #: height under a title is an empty chart, and an empty chart reads as a
    #: measurement of zero rather than as an absence of measurements.
    chart_visible: bool
    #: Said in the chart's place when there is nothing to draw in it.
    chart_note: str

    bars: tuple[DayBar, ...]

    deferrals_title: str
    deferrals_note: str
    deferrals: tuple[DeferralLine, ...]


class StatisticsPresenter:
    """Turns a window of history into the page. Holds no widget and no database."""

    def __init__(
        self,
        source: StatisticsSource | None = None,
        schedule: BreakSchedule | None = None,
    ) -> None:
        self._source = source or NullStatistics()
        self._schedule = schedule

    def view(self, days: int = WINDOW_DAYS) -> StatisticsPageView:
        statistics = self._source.read(days)
        tallest = max((day.screen_seconds for day in statistics.days), default=0.0)
        busiest = max((entry.count for entry in statistics.deferrals), default=0)
        today = statistics.today.day

        return StatisticsPageView(
            headline=translate("Statistics", "The last seven days"),
            subheading=translate(
                "Statistics",
                "What Ocura recorded while it was running. "
                "Times are counted in focus blocks that finished.",
            ),
            empty=statistics.is_empty,
            empty_message=self._empty_message(),
            chart_visible=tallest > 0.0,
            chart_note=self._chart_note(),
            today_text=duration_text(statistics.today.screen_seconds),
            week_text=duration_text(statistics.screen_seconds),
            breaks_text=str(statistics.breaks),
            average_focus_text=duration_text(statistics.average_focus_seconds),
            bars=tuple(
                DayBar(
                    weekday=translate("Calendar", WEEKDAYS[day.day.weekday()]),
                    day_of_month=str(day.day.day),
                    value_text=duration_text(day.screen_seconds),
                    fraction=(day.screen_seconds / tallest) if tallest > 0 else 0.0,
                    is_today=day.day == today,
                )
                for day in statistics.days
            ),
            deferrals_title=translate("Statistics", "When Ocura waited"),
            deferrals_note=self._deferrals_note(statistics),
            deferrals=tuple(
                DeferralLine(
                    # A reason this build has never heard of passes through
                    # untranslated, which is the same bargain the storage layer
                    # makes when it keeps an unknown family verbatim.
                    reason=translate("Reasons", entry.reason),
                    count_text=f"{entry.count}",
                    fraction=(entry.count / busiest) if busiest else 0.0,
                )
                for entry in statistics.deferrals
            ),
        )

    def _empty_message(self) -> str:
        """Plain, and specific about when there will be something to see.

        "No data" on its own reads as a fault. A first-day user has done
        nothing wrong and there is nothing to fix, so the sentence says what
        the page is waiting for and roughly how long that takes.
        """
        if self._schedule is None:
            return translate(
                "Statistics",
                "Nothing to show yet. Ocura records a focus block once it finishes, "
                "so the first one appears here after your first full block.",
            )
        return translate(
            "Statistics",
            "Nothing to show yet. Ocura records a focus block once it finishes, so the "
            "first one appears here about %1 after you start a session. The week fills "
            "in a day at a time after that.",
        ).replace("%1", duration_words(self._schedule.focus_interval))

    def _chart_note(self) -> str:
        """Why the chart is not there, in the place it would have been."""
        if self._schedule is None:
            return translate(
                "Statistics",
                "No focus block has finished yet, so there is nothing to chart. "
                "Breaks are counted above as they happen.",
            )
        return translate(
            "Statistics",
            "No focus block has finished yet, so there is nothing to chart. A block is "
            "about %1; breaks are counted above as they happen.",
        ).replace("%1", duration_words(self._schedule.focus_interval))

    def _deferrals_note(self, statistics: Statistics) -> str:
        """The most useful sentence on the page, so it is the one that explains.

        This is the section that answers "it interrupted me too often": every
        time Ocura decided the moment was wrong and held the break back,
        counted by why. It is written as a record of what the detectors did,
        not as something the user did.
        """
        if not statistics.deferrals:
            return translate(
                "Statistics",
                "Ocura holds a break back when the moment is wrong — while the screen is "
                "locked, while something is fullscreen, while you are away from the keyboard. "
                "It has not needed to yet.",
            )
        total = sum(entry.count for entry in statistics.deferrals)
        # Two whole sentences rather than one with a count spliced into it.
        # "once" and "4 times" are not interchangeable fragments in German or
        # Arabic, and a translator handed a fragment cannot fix that.
        if total == 1:
            return translate(
                "Statistics",
                "Ocura held a break back once this week rather than interrupting, and "
                "waited for a better moment. This is why.",
            )
        return translate(
            "Statistics",
            "Ocura held a break back %1 times this week rather than interrupting, and "
            "waited for a better moment. This is why.",
        ).replace("%1", str(total))
