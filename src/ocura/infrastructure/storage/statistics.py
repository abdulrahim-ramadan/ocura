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

**What "at the screen" is counted from.** The `focus` on the row that closed
each block — a break finished or skipped, a rest credited, the session stopped
or restarted — measured on the monotonic clock with every absence past the idle
threshold taken out, sleep included. Not the wall-clock gap between events, and
no longer the duration on `BREAK_DUE`: that was written again on every retry of
a deferred break, each time carrying the whole stretch so far, and it summed
one 57-hour absence into a week of 3,997 hours. A block still running is not
counted until it ends, and one lost to a crash is not counted at all; the page
says it counts finished blocks, and a number that is honestly incomplete beats
one that is silently wrong.

**A block belongs to the day it closed.** One that runs from 23:50 to 00:10 is
counted whole on the new day. The row says how long the block was, not when
each minute of it happened — absences and pauses inside it are already gone —
so splitting it at midnight would be inventing the split.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from ocura.application.reasons import normalise
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

#: The folding of a detector's raw reason into a family lives in
#: `ocura.application.reasons`, not here. It was here first, when the
#: statistics page was the only surface that showed a reason; the dashboard,
#: the tray and the event list show the same reasons live, and two copies of
#: the table would have been two vocabularies free to disagree about what a
#: lock is called.


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

        for at, kind, detail, focus in rows:
            day = _local(datetime.fromisoformat(at), zone).date()
            # Any kind can close a block, so this is not part of the match on
            # kind below. A block of no time at all — a restart the instant
            # after a start — is not a block.
            if focus is not None and focus > 0:
                screen[day] = screen.get(day, 0.0) + float(focus)
                blocks[day] += 1
            if kind in _BREAK_HAPPENED:
                breaks[day] += 1
            elif kind == SessionEventKind.BREAK_DEFERRED and detail:
                reasons[normalise(detail)] += 1

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
                "SELECT at, kind, detail, focus FROM events WHERE at >= ? AND at < ? ORDER BY id",
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
