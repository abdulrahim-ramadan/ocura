"""The session event log: append-only, and the thing the rest of P4 is derived from.

There is no `sessions` table and no `daily_metrics` table. A session is the run
of events between one STARTED and the next STOPPED, and a day's metrics are a
count over a date range — both are questions the log already answers. A stored
total is a second copy of the truth, free to disagree with the first, and this
codebase has already made that argument once about owed breaks (see "No flag
for an owed break" in docs/architecture.md). The same reasoning applies here.

Times are stored as ISO-8601 in UTC, without exception. A log ordered in mixed
timezones is not ordered, and a naive timestamp is one whose meaning depends on
which machine reads it. Local time is a presentation decision and is made by
the UI, at the moment of display.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from ocura.application.session import SessionEvent, SessionEventKind
from ocura.infrastructure.storage.errors import StorageError


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """One row, read back. Distinct from SessionEvent: it has an identity and a run."""

    id: int
    run: int
    at: datetime
    kind: str
    state: str
    detail: str

    @property
    def event_kind(self) -> SessionEventKind | None:
        """The kind as this build understands it, or None if it does not.

        A newer Ocura may have written a kind this one has never heard of, and
        reading old history must not turn into a crash over an unknown string.
        """
        try:
            return SessionEventKind(self.kind)
        except ValueError:
            return None


def next_run(connection: sqlite3.Connection) -> int:
    """One past the highest run in the file, or 1 for an empty one."""
    try:
        highest = connection.execute("SELECT MAX(run) FROM events").fetchone()[0]
    except sqlite3.Error as exc:
        raise StorageError(f"could not read the run counter: {exc}") from exc
    return int(highest or 0) + 1


class EventStore:
    """Appends SessionEvents to the log and reads them back. Owns no connection lifetime.

    Failures are reported, not swallowed. Whether a failed write matters is not
    a decision this class is in a position to make — the caller that knows the
    timer must keep running is the one that decides, and does so in exactly one
    place (`BreakPresenter._keep`).
    """

    def __init__(self, connection: sqlite3.Connection, run: int) -> None:
        self._connection = connection
        self._run = run

    @classmethod
    def open(cls, connection: sqlite3.Connection) -> EventStore:
        """Claim the next run number and start appending to it."""
        return cls(connection, next_run(connection))

    @property
    def run(self) -> int:
        return self._run

    def record(self, event: SessionEvent) -> None:
        """Append one event. Raises StorageError; never returns a failure quietly."""
        try:
            self._connection.execute(
                "INSERT INTO events (run, at, kind, state, detail) VALUES (?, ?, ?, ?, ?)",
                (
                    self._run,
                    _utc_text(event.at),
                    str(event.kind),
                    str(event.state),
                    event.detail,
                ),
            )
        except sqlite3.Error as exc:
            raise StorageError(f"could not record {event.kind}: {exc}") from exc

    def recent(self, limit: int = 100) -> list[StoredEvent]:
        """The newest events first, which is the order every view of them wants."""
        return self._read(
            "SELECT id, run, at, kind, state, detail FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def for_run(self, run: int | None = None) -> list[StoredEvent]:
        """One launch of the application, oldest first."""
        return self._read(
            "SELECT id, run, at, kind, state, detail FROM events WHERE run = ? ORDER BY id",
            (self._run if run is None else run,),
        )

    def count(self) -> int:
        try:
            return int(self._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        except sqlite3.Error as exc:
            raise StorageError(f"could not count history: {exc}") from exc

    def _read(self, sql: str, parameters: tuple[object, ...]) -> list[StoredEvent]:
        try:
            rows = self._connection.execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"could not read history: {exc}") from exc
        return [
            StoredEvent(
                id=row["id"],
                run=row["run"],
                at=datetime.fromisoformat(row["at"]),
                kind=row["kind"],
                state=row["state"],
                detail=row["detail"],
            )
            for row in rows
        ]


def _utc_text(moment: datetime) -> str:
    """Normalise to UTC before storing. A naive datetime is read as local time.

    That is the only reading available — a naive datetime carries no other
    information — and it is better than storing the ambiguity and discovering
    it later in a chart that is an hour wrong twice a year.
    """
    return moment.astimezone(UTC).isoformat()
