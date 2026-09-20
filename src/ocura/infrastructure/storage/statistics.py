"""Aggregating the event log into the window the statistics page reads.

No `statistics` table and no daily rollup, for the reason the log itself is one
table: a stored total is a second copy of the truth, free to disagree with the
events it claims to summarise. A week is a few hundred rows and counting them
on demand is instant.

**Why the day bucketing happens in Python and not in SQL.** SQLite's
`datetime(..., 'localtime')` depends on the host's zone database and cannot be
pointed at a different zone for a test. The rows are stored in UTC — they have
to be, a log ordered in mixed zones is not ordered — and a day is a local
thing. `datetime.astimezone` does that conversion exactly, including across a
DST change, so the range filter is done in SQL over UTC text and the bucketing
is done here.

**What "at the screen" is counted from.** The measured duration on each
`BREAK_DUE` row, which is the focus block that earned the break, taken from the
monotonic clock at the moment it completed. Not the wall-clock gap between
events: a laptop that slept for three hours between two rows would turn that
sleep into three hours of screen time. The cost of that choice is that a block
still running, or one ended by stopping the session before a break came due, is
not counted — the page says so in as many words, and a number that is honestly
incomplete beats one that is silently wrong.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from ocura.application.session import SessionEventKind
from ocura.application.statistics import (
    WINDOW_DAYS,
    DayTotals,
    ReasonCount,
    Statistics,
)
from ocura.infrastructure.storage.errors import StorageError

#: The kinds that mean a break happened. Both, because the dashboard counts
#: both: a break the user ended early is still a break that happened, and this
#: page is not the place to start having an opinion about its length.
_BREAK_HAPPENED = (SessionEventKind.BREAK_COMPLETED, SessionEventKind.BREAK_SKIPPED)

#: Raw detector reasons, folded to the family they belong to. The idle detector
#: writes the measured seconds into its reason — "idle for 312s" — so grouping
#: on the raw string would produce one bucket per deferral and a list nobody
#: can read. Matched by prefix and kept in one place so a detector's wording
#: and this page's wording cannot drift apart silently.
_REASON_FAMILIES: tuple[tuple[str, str], ...] = (
    ("idle for", "Away from the keyboard"),
    ("session locked", "Screen locked"),
    ("fullscreen or presenting", "Fullscreen or presenting"),
    ("screensaver running", "Screensaver running"),
)


def normalise_reason(reason: str) -> str:
    """Fold a detector's reason into its family, or pass it through unchanged.

    Unknown reasons are kept verbatim rather than swept into an "Other" bucket.
    A detector added later must show up on this page as itself on the day it
    ships, not disappear into a total nobody can explain — the same rule that
    makes `StoredEvent.event_kind` return None for a kind it has never heard of
    instead of refusing to read the row.
    """
    folded = reason.strip().lower()
    for prefix, family in _REASON_FAMILIES:
        if folded.startswith(prefix):
            return family
    return reason.strip()


class StatisticsStore:
    """Reads a window of the log and counts it. Owns no connection lifetime."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def read(
        self,
        days: int = WINDOW_DAYS,
        *,
        now: datetime | None = None,
        zone: tzinfo | None = None,
    ) -> Statistics:
        """The last `days` local days, today last.

        `now` and `zone` exist so this can be asked about a fixed moment in a
        fixed zone. Left alone, both come from the machine, which is the only
        thing the application ever passes.
        """
        if days < 1:
            raise ValueError(f"a window of {days} days is not a window")

        moment = now or datetime.now().astimezone()
        today = _local(moment, zone).date()
        first = today - timedelta(days=days - 1)

        rows = self._rows_between(_day_start(first, zone), _day_start(today + timedelta(1), zone))

        screen: dict[date, float] = {}
        blocks: Counter[date] = Counter()
        breaks: Counter[date] = Counter()
        reasons: Counter[str] = Counter()

        for at, kind, detail, duration in rows:
            day = _local(datetime.fromisoformat(at), zone).date()
            if kind == SessionEventKind.BREAK_DUE:
                # A block is counted on the day it finished. One that ran
                # across midnight belongs to the day it ended on rather than
                # being split: the row records how long it was, not when each
                # minute of it happened, and inventing the split would be
                # inventing data.
                if duration is not None:
                    screen[day] = screen.get(day, 0.0) + float(duration)
                    blocks[day] += 1
            elif kind in _BREAK_HAPPENED:
                breaks[day] += 1
            elif kind == SessionEventKind.BREAK_DEFERRED and detail:
                reasons[normalise_reason(detail)] += 1

        return Statistics(
            days=tuple(
                DayTotals(
                    day=day,
                    screen_seconds=screen.get(day, 0.0),
                    breaks=breaks[day],
                    focus_blocks=blocks[day],
                )
                for day in (first + timedelta(days=offset) for offset in range(days))
            ),
            deferrals=tuple(
                # Commonest first, and ties broken by name so the order of two
                # equal reasons does not flip between one reading and the next.
                ReasonCount(reason=reason, count=count)
                for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
            ),
        )

    def _rows_between(self, start: datetime, end: datetime) -> list[tuple[str, str, str, float]]:
        """Half-open: the last day's midnight belongs to the day after it."""
        try:
            return self._connection.execute(
                "SELECT at, kind, detail, duration FROM events "
                "WHERE at >= ? AND at < ? ORDER BY id",
                (start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"could not read history: {exc}") from exc


def _day_start(day: date, zone: tzinfo | None) -> datetime:
    """Local midnight, as an aware moment.

    With no zone this goes through `astimezone()` on a naive datetime, which is
    the one call that reads the host's real zone rules — so a day that is 23 or
    25 hours long because the clocks changed is still one day.
    """
    midnight = datetime.combine(day, time.min)
    return midnight.astimezone() if zone is None else midnight.replace(tzinfo=zone)


def _local(moment: datetime, zone: tzinfo | None) -> datetime:
    return moment.astimezone() if zone is None else moment.astimezone(zone)
