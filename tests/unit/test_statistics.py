"""The statistics window: what it counts, and the day boundaries it counts across.

Seeded through the real `EventStore` into a real SQLite file rather than by
hand-writing rows. The write path normalises timestamps to UTC and the read
path converts them back to a local day; a test that inserted its own rows would
be testing the read half against a fixture instead of against what the product
actually stores.

Every zone here is a fixed offset rather than a named one. `zoneinfo` needs the
`tzdata` package on Windows, and what these tests need to prove — that a day is
a local day and not a UTC one, and that a week can cross a month end — needs an
offset, not a DST rule.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ocura.application.reasons import normalise
from ocura.application.session import SessionEvent, SessionEventKind
from ocura.application.statistics import (
    WINDOW_DAYS,
    NullStatistics,
    Statistics,
    StatisticsPresenter,
    StatisticsSource,
    duration_text,
    empty_window,
)
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerState
from ocura.infrastructure.storage import (
    StatisticsStore,
    StorageError,
    close_database,
    open_event_store,
)

from .conftest import ACCUSATORY_WORDS

#: Nine hours ahead, so a local day and a UTC day are never the same day for
#: most of the evening. Anything that quietly buckets on UTC fails here.
TOKYO = timezone(timedelta(hours=9))
#: And a zone behind UTC, so the error cannot be a sign flip that happens to
#: pass in one direction.
DENVER = timezone(timedelta(hours=-7))

FOCUS = 20 * 60.0


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "history" / "ocura.db"


class Seeder:
    """Writes events at chosen local moments through the real store."""

    def __init__(self, path: Path, zone: timezone) -> None:
        self.connection, self.store = open_event_store(path)
        self.statistics = StatisticsStore(self.connection)
        self._zone = zone

    def at(self, moment: datetime) -> datetime:
        return moment.replace(tzinfo=self._zone)

    def focus_block(self, moment: datetime, seconds: float = FOCUS) -> None:
        """A block that reached a break, which is what screen time is counted from."""
        self._record(SessionEventKind.BREAK_DUE, moment, duration=seconds)

    def took_a_break(self, moment: datetime, *, early: bool = False) -> None:
        kind = SessionEventKind.BREAK_SKIPPED if early else SessionEventKind.BREAK_COMPLETED
        self._record(kind, moment, duration=20.0)

    def waited(self, moment: datetime, reason: str) -> None:
        self._record(SessionEventKind.BREAK_DEFERRED, moment, detail=reason, duration=300.0)

    def other(self, moment: datetime) -> None:
        """An event that is none of the above and must not be counted as one."""
        self._record(SessionEventKind.STARTED, moment)

    def _record(
        self,
        kind: SessionEventKind,
        moment: datetime,
        detail: str = "",
        duration: float | None = None,
    ) -> None:
        self.store.record(
            SessionEvent(
                kind=kind,
                at=self.at(moment),
                state=TimerState.FOCUSING,
                detail=detail,
                duration=duration,
            )
        )

    def read(self, now: datetime, days: int = WINDOW_DAYS) -> Statistics:
        return self.statistics.read(days, now=self.at(now), zone=self._zone)

    def close(self) -> None:
        close_database(self.connection)


@pytest.fixture
def seeded(database_path: Path):
    def build(zone: timezone = TOKYO) -> Seeder:
        return Seeder(database_path, zone)

    made: list[Seeder] = []

    def factory(zone: timezone = TOKYO) -> Seeder:
        seeder = build(zone)
        made.append(seeder)
        return seeder

    yield factory
    for seeder in made:
        seeder.close()


# --- what is counted -------------------------------------------------------


def test_screen_time_is_the_sum_of_measured_focus_blocks(seeded):
    """Not the wall-clock gap between rows: a laptop that slept for three hours
    between two events would turn that sleep into three hours at the screen."""
    history = seeded()
    history.focus_block(datetime(2026, 9, 20, 9, 30), seconds=1200.0)
    history.focus_block(datetime(2026, 9, 20, 10, 10), seconds=1500.0)

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert window.today.screen_seconds == 2700.0
    assert window.today.focus_blocks == 2
    assert window.screen_seconds == 2700.0


def test_a_block_with_no_measured_duration_is_not_counted_as_zero(seeded):
    """A v1 row has no duration. It is a block nobody measured, not a block of
    no length, so it is left out of both the total and the count it averages."""
    history = seeded()
    history.focus_block(datetime(2026, 9, 20, 9, 30), seconds=1200.0)
    history._record(SessionEventKind.BREAK_DUE, datetime(2026, 9, 20, 10, 30), duration=None)

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert window.today.focus_blocks == 1
    assert window.today.screen_seconds == 1200.0


def test_breaks_count_the_ones_ended_early_too(seeded):
    """The dashboard counts both, and this page does not start having an
    opinion about how long a break the user chose to end should have been."""
    history = seeded()
    history.took_a_break(datetime(2026, 9, 20, 9, 50))
    history.took_a_break(datetime(2026, 9, 20, 10, 30), early=True)

    assert history.read(datetime(2026, 9, 20, 18, 0)).today.breaks == 2


def test_events_that_are_neither_a_block_nor_a_break_are_not_counted(seeded):
    history = seeded()
    history.other(datetime(2026, 9, 20, 9, 0))
    history.other(datetime(2026, 9, 20, 9, 5))

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert window.today.breaks == 0
    assert window.today.focus_blocks == 0
    assert window.is_empty


def test_the_average_focus_block_is_the_mean_of_the_blocks(seeded):
    history = seeded()
    history.focus_block(datetime(2026, 9, 18, 9, 0), seconds=1200.0)
    history.focus_block(datetime(2026, 9, 19, 9, 0), seconds=1800.0)
    history.focus_block(datetime(2026, 9, 20, 9, 0), seconds=1500.0)

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert window.average_focus_seconds == 1500.0


def test_the_average_is_none_rather_than_zero_when_nothing_was_measured(seeded):
    """Zero would read as "your focus blocks are zero minutes long"."""
    history = seeded()
    history.took_a_break(datetime(2026, 9, 20, 9, 50))

    assert history.read(datetime(2026, 9, 20, 18, 0)).average_focus_seconds is None


# --- days, in local time ---------------------------------------------------


def test_the_window_is_seven_local_days_ending_today(seeded):
    history = seeded()
    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert len(window.days) == WINDOW_DAYS
    assert window.days[0].day == date(2026, 9, 14)
    assert window.today.day == date(2026, 9, 20)


def test_a_day_is_a_local_day_and_not_a_utc_one(seeded):
    """Late evening in Tokyo is the previous afternoon in UTC. A row written at
    23:30 local belongs to the local day it was written on."""
    history = seeded(TOKYO)
    late = datetime(2026, 9, 20, 23, 30)
    history.focus_block(late, seconds=600.0)

    # The stored row really is on the previous UTC day: this is the confusion
    # the local bucketing exists to prevent, asserted rather than assumed.
    stored = history.store.recent(limit=1)[0]
    assert stored.at.astimezone(UTC).date() == date(2026, 9, 20)
    assert history.at(late).astimezone(UTC).hour == 14

    window = history.read(datetime(2026, 9, 20, 23, 45))
    assert window.today.day == date(2026, 9, 20)
    assert window.today.screen_seconds == 600.0


def test_just_after_local_midnight_belongs_to_the_new_day(seeded):
    history = seeded(TOKYO)
    history.focus_block(datetime(2026, 9, 20, 23, 50), seconds=600.0)
    history.focus_block(datetime(2026, 9, 21, 0, 10), seconds=900.0)

    window = history.read(datetime(2026, 9, 21, 9, 0))

    yesterday, today = window.days[-2], window.days[-1]
    assert yesterday.day == date(2026, 9, 20)
    assert yesterday.screen_seconds == 600.0
    assert today.day == date(2026, 9, 21)
    assert today.screen_seconds == 900.0


def test_the_same_boundary_holds_in_a_zone_behind_utc(seeded):
    """So the bucketing cannot be a sign flip that happens to pass one way."""
    history = seeded(DENVER)
    history.focus_block(datetime(2026, 9, 20, 23, 50), seconds=600.0)
    history.focus_block(datetime(2026, 9, 21, 0, 10), seconds=900.0)

    window = history.read(datetime(2026, 9, 21, 9, 0))

    assert window.days[-2].screen_seconds == 600.0
    assert window.days[-1].screen_seconds == 900.0


def test_tomorrow_is_not_in_the_window(seeded):
    """The window ends at tonight's local midnight, which belongs to tomorrow."""
    history = seeded()
    history.focus_block(datetime(2026, 9, 21, 0, 0), seconds=900.0)

    window = history.read(datetime(2026, 9, 20, 23, 59))

    assert window.screen_seconds == 0.0
    assert window.is_empty


def test_anything_older_than_the_window_is_left_out(seeded):
    history = seeded()
    history.focus_block(datetime(2026, 9, 13, 23, 59), seconds=3600.0)
    history.focus_block(datetime(2026, 9, 14, 0, 1), seconds=600.0)

    window = history.read(datetime(2026, 9, 20, 12, 0))

    assert window.days[0].day == date(2026, 9, 14)
    assert window.screen_seconds == 600.0


def test_a_week_that_spans_a_month_end(seeded):
    """The window is seven days back, not "this calendar month so far"."""
    history = seeded()
    history.focus_block(datetime(2026, 9, 29, 10, 0), seconds=1200.0)
    history.focus_block(datetime(2026, 9, 30, 10, 0), seconds=1800.0)
    history.focus_block(datetime(2026, 10, 1, 10, 0), seconds=600.0)
    history.focus_block(datetime(2026, 10, 3, 10, 0), seconds=900.0)

    window = history.read(datetime(2026, 10, 3, 18, 0))

    assert [day.day for day in window.days] == [
        date(2026, 9, 27),
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]
    assert [day.screen_seconds for day in window.days] == [
        0.0,
        0.0,
        1200.0,
        1800.0,
        600.0,
        0.0,
        900.0,
    ]
    assert window.today.screen_seconds == 900.0


def test_a_week_that_spans_a_year_end(seeded):
    history = seeded()
    history.focus_block(datetime(2026, 12, 31, 10, 0), seconds=1200.0)
    history.focus_block(datetime(2027, 1, 1, 10, 0), seconds=600.0)

    window = history.read(datetime(2027, 1, 2, 18, 0))

    assert window.days[0].day == date(2026, 12, 27)
    assert window.today.day == date(2027, 1, 2)
    assert window.screen_seconds == 1800.0


def test_a_day_with_nothing_on_it_is_present_and_empty(seeded):
    """Zero-filled rather than absent: a chart that skipped quiet days would
    compress the week into whichever days happened to be busy."""
    history = seeded()
    history.focus_block(datetime(2026, 9, 20, 10, 0), seconds=600.0)

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert len(window.days) == WINDOW_DAYS
    assert all(day.screen_seconds == 0.0 for day in window.days[:-1])


# --- the deferral reasons --------------------------------------------------


def test_reasons_are_grouped_into_families_with_counts(seeded):
    """The idle detector writes the measured seconds into its reason, so
    grouping on the raw string would make one bucket per deferral."""
    history = seeded()
    history.waited(datetime(2026, 9, 20, 9, 0), "idle for 312s")
    history.waited(datetime(2026, 9, 20, 10, 0), "idle for 87s")
    history.waited(datetime(2026, 9, 20, 11, 0), "session locked")

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert [(entry.reason, entry.count) for entry in window.deferrals] == [
        ("Away from the keyboard", 2),
        ("Screen locked", 1),
    ]


def test_the_commonest_reason_comes_first(seeded):
    history = seeded()
    for hour in (9, 10, 11):
        history.waited(datetime(2026, 9, 20, hour, 0), "fullscreen or presenting")
    history.waited(datetime(2026, 9, 20, 12, 0), "session locked")

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert window.deferrals[0].reason == "Fullscreen or presenting"
    assert window.deferrals[0].count == 3


def test_ties_are_broken_by_name_so_the_order_does_not_flicker(seeded):
    history = seeded()
    history.waited(datetime(2026, 9, 20, 9, 0), "session locked")
    history.waited(datetime(2026, 9, 20, 10, 0), "fullscreen or presenting")

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert [entry.reason for entry in window.deferrals] == [
        "Fullscreen or presenting",
        "Screen locked",
    ]


def test_a_reason_this_build_has_never_heard_of_is_kept_verbatim(seeded):
    """A detector added later shows up as itself on the day it ships rather
    than disappearing into an "Other" nobody can explain."""
    history = seeded()
    history.waited(datetime(2026, 9, 20, 9, 0), "camera in use")

    window = history.read(datetime(2026, 9, 20, 18, 0))

    assert [entry.reason for entry in window.deferrals] == ["camera in use"]


def test_a_deferral_outside_the_window_is_not_counted(seeded):
    history = seeded()
    history.waited(datetime(2026, 9, 1, 9, 0), "session locked")

    assert history.read(datetime(2026, 9, 20, 18, 0)).deferrals == ()


@pytest.mark.parametrize(
    ("raw", "family"),
    [
        ("idle for 312s", "Away from the keyboard"),
        ("idle for 9s", "Away from the keyboard"),
        ("session locked", "Screen locked"),
        ("fullscreen or presenting", "Fullscreen or presenting"),
        ("screensaver running", "Screensaver running"),
        ("  Session Locked  ", "Screen locked"),
        ("something nobody has written yet", "something nobody has written yet"),
    ],
)
def test_reason_families(raw: str, family: str):
    assert normalise(raw) == family


# --- the shape of no history ----------------------------------------------


def test_an_empty_database_reads_as_a_window_of_empty_days(seeded):
    window = seeded().read(datetime(2026, 9, 20, 18, 0))

    assert len(window.days) == WINDOW_DAYS
    assert window.is_empty
    assert window.breaks == 0
    assert window.deferrals == ()


def test_a_closed_database_reports_a_storage_error(database_path: Path):
    """Never a sqlite3 exception: the UI is banned from importing sqlite3."""
    history = Seeder(database_path, TOKYO)
    history.close()

    with pytest.raises(StorageError):
        history.read(datetime(2026, 9, 20, 18, 0))


def test_a_window_of_no_days_is_refused(seeded):
    with pytest.raises(ValueError):
        seeded().read(datetime(2026, 9, 20, 18, 0), days=0)


def test_the_null_source_is_a_source_and_answers_with_empty_days():
    source = NullStatistics(today=date(2026, 9, 20))

    assert isinstance(source, StatisticsSource)
    window = source.read()
    assert window.today.day == date(2026, 9, 20)
    assert window.is_empty


def test_the_real_store_satisfies_the_protocol_the_application_asks_for(seeded):
    """The seam, checked rather than assumed: application names a protocol and
    infrastructure implements it, the way SessionJournal works."""
    assert isinstance(seeded().statistics, StatisticsSource)


def test_an_empty_window_is_the_right_length_and_ends_today():
    window = empty_window(date(2026, 3, 1))

    assert len(window.days) == WINDOW_DAYS
    assert window.days[0].day == date(2026, 2, 23)
    assert window.today.day == date(2026, 3, 1)


# --- the page's numbers and its words --------------------------------------


class FixedSource:
    """A window of history that was decided by the test, not by a database."""

    def __init__(self, statistics: Statistics) -> None:
        self._statistics = statistics

    def read(self, days: int = WINDOW_DAYS) -> Statistics:
        del days
        return self._statistics


def a_window(**per_day: float) -> Statistics:
    """Seven days ending 2026-09-20, given screen seconds by weekday name."""
    from ocura.application.statistics import DayTotals, ReasonCount

    days = [date(2026, 9, 14) + timedelta(days=offset) for offset in range(WINDOW_DAYS)]
    reasons = per_day.pop("reasons", ())
    breaks = per_day.pop("breaks", 0)
    return Statistics(
        days=tuple(
            DayTotals(
                day=day,
                screen_seconds=per_day.get(day.strftime("%a").lower(), 0.0),
                breaks=breaks if day == days[-1] else 0,
                focus_blocks=1 if per_day.get(day.strftime("%a").lower(), 0.0) else 0,
            )
            for day in days
        ),
        deferrals=tuple(ReasonCount(reason, count) for reason, count in reasons),
    )


def a_page(statistics: Statistics, schedule: BreakSchedule | None = None):
    return StatisticsPresenter(FixedSource(statistics), schedule).view()


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (None, "—"),
        (0.0, "—"),
        (90.0, "2m"),
        (1200.0, "20m"),
        (3600.0, "1h"),
        (8100.0, "2h 15m"),
        (28800.0, "8h"),
    ],
)
def test_durations_read_as_hours_and_minutes(seconds, text):
    """Never seconds. Every number on this page is a total over a day or a
    week, and nobody decides anything on the strength of forty seconds."""
    assert duration_text(seconds) == text


def test_nothing_measured_reads_as_a_dash_rather_than_a_zero():
    """A zero is a reading. An absence of readings is not one."""
    page = a_page(a_window())

    assert page.today_text == "—"
    assert page.average_focus_text == "—"


def test_the_page_shows_what_the_window_counted():
    page = a_page(a_window(fri=3600.0, sat=1800.0, sun=900.0, breaks=4))

    assert page.today_text == "15m"
    assert page.week_text == "1h 45m"
    assert page.breaks_text == "4"


def test_there_is_one_bar_per_day_and_today_is_the_last_one():
    page = a_page(a_window(sun=900.0))

    assert len(page.bars) == WINDOW_DAYS
    assert [bar.is_today for bar in page.bars] == [False] * 6 + [True]
    assert page.bars[-1].day_of_month == "20"


def test_bars_are_a_fraction_of_the_tallest_day_not_of_a_target():
    """Read against itself, because there is no target to read it against."""
    page = a_page(a_window(tue=3600.0, sun=1800.0))

    tallest = max(page.bars, key=lambda bar: bar.fraction)
    assert tallest.fraction == 1.0
    assert page.bars[-1].fraction == 0.5
    assert page.bars[0].fraction == 0.0


def test_a_week_with_breaks_but_no_finished_block_has_nothing_to_chart():
    """Not the empty state — breaks did happen — and still no chart. This is
    what a database written by someone who only ever pressed "Take a break now"
    looks like, and it is the case a bare `empty` flag gets wrong."""
    page = a_page(a_window(breaks=3))

    assert page.empty is False
    assert page.chart_visible is False
    assert page.breaks_text == "3"
    assert page.chart_note


def test_the_chart_appears_as_soon_as_one_block_has_finished():
    page = a_page(a_window(sun=600.0))

    assert page.chart_visible is True


def test_the_chart_note_says_how_long_a_block_is_when_it_can():
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=20.0, defer_interval=300.0)
    page = a_page(a_window(breaks=3), schedule)

    assert "20 minutes" in page.chart_note


def test_a_week_with_nothing_in_it_has_no_bar_heights_at_all():
    page = a_page(a_window())

    assert all(bar.fraction == 0.0 for bar in page.bars)


# --- the empty state -------------------------------------------------------


def test_an_empty_week_says_so_and_says_when_there_will_be_something():
    """ "No data" on its own reads as a fault. A first-day user has done nothing
    wrong, so the sentence says what the page is waiting for and how long."""
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=20.0, defer_interval=300.0)
    page = a_page(a_window(), schedule)

    assert page.empty is True
    assert "20 minutes" in page.empty_message
    assert "nothing to show yet" in page.empty_message.lower()


def test_a_week_with_anything_in_it_is_not_the_empty_state():
    assert a_page(a_window(sun=600.0)).empty is False
    assert a_page(a_window(breaks=1)).empty is False
    assert a_page(a_window(reasons=(("Screen locked", 1),))).empty is False


def test_the_empty_state_still_says_something_without_a_schedule():
    """The page is constructible with no schedule; it just cannot promise a
    number of minutes, so it does not invent one."""
    page = a_page(a_window())

    assert page.empty_message
    assert "minutes" not in page.empty_message


# --- the deferral section --------------------------------------------------


def test_the_deferral_lines_carry_their_counts_and_proportions():
    page = a_page(a_window(reasons=(("Fullscreen or presenting", 6), ("Screen locked", 3))))

    assert [line.reason for line in page.deferrals] == [
        "Fullscreen or presenting",
        "Screen locked",
    ]
    assert [line.count_text for line in page.deferrals] == ["6", "3"]
    assert [line.fraction for line in page.deferrals] == [1.0, 0.5]


def test_the_note_counts_the_times_ocura_held_back():
    page = a_page(a_window(reasons=(("Screen locked", 4), ("Away from the keyboard", 2))))

    assert "6 times" in page.deferrals_note


def test_one_deferral_is_not_described_as_one_times():
    page = a_page(a_window(reasons=(("Screen locked", 1),)))

    assert "once" in page.deferrals_note


def test_having_never_waited_is_explained_rather_than_left_blank():
    page = a_page(a_window(sun=600.0))

    assert page.deferrals == ()
    assert "has not needed to yet" in page.deferrals_note


# --- the language rule -----------------------------------------------------


def every_word_on(page) -> str:
    """Every string the page will put on screen, including the empty state."""
    parts = [
        page.headline,
        page.subheading,
        page.empty_message,
        page.today_text,
        page.week_text,
        page.breaks_text,
        page.average_focus_text,
        page.deferrals_title,
        page.deferrals_note,
        page.chart_note,
    ]
    parts += [bar.weekday + " " + bar.value_text for bar in page.bars]
    parts += [line.reason + " " + line.count_text for line in page.deferrals]
    return " ".join(parts).lower()


@pytest.mark.parametrize(
    "statistics",
    [
        a_window(),
        a_window(sun=900.0, breaks=3),
        a_window(mon=3600.0, sun=600.0, breaks=8, reasons=(("Screen locked", 5),)),
    ],
)
def test_no_statistics_text_is_accusatory(statistics):
    """The same rule as the dashboard's `test_no_event_text_is_accusatory`, off
    the same shared list — a rule enforced on one screen and not the other is
    one the next screen quietly breaks."""
    schedule = BreakSchedule(focus_interval=1200.0, break_duration=20.0, defer_interval=300.0)
    words = every_word_on(StatisticsPresenter(FixedSource(statistics), schedule).view())

    assert not [bad for bad in ACCUSATORY_WORDS if bad in words]


def test_the_page_never_scores_a_week():
    """No streaks, no goals, no percentage of breaks "achieved" against a
    target that does not exist. Ocura reports; it does not mark."""
    page = a_page(
        a_window(mon=3600.0, sun=600.0, breaks=8, reasons=(("Screen locked", 5),)),
        BreakSchedule(focus_interval=1200.0, break_duration=20.0, defer_interval=300.0),
    )
    words = every_word_on(page)

    assert "%" not in words
    for bad in ("day streak", "in a row", "best", "worst", "average day", "keep it up"):
        assert bad not in words
