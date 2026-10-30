"""The schema, and the only route a file takes from one version to the next.

Migrations are a tuple in a module, not a directory of numbered files. At this
size the entire history fits on one screen, and a step that cannot be read next
to the one before it is a step nobody will check.

`PRAGMA user_version` is the authoritative marker rather than a table of our
own. It is one integer in the database header, it is written inside the same
transaction as the DDL it describes, and it therefore cannot get out of step
with the schema it claims to describe.

The `schema_version` table beside it is a **ledger, not a second marker**: one
row per step that has been applied, with the time it was applied. It answers a
question the pragma cannot — *when did this file become a v2* — which is the
first thing worth knowing when a tester's database behaves unlike anyone
else's. `migrate()` reads the pragma and never the ledger, so the two cannot
disagree about what the schema is; the ledger only ever adds to what the pragma
already says.

**No user identifier, ever.** Not a UUID, not a machine ID, not a hashed one.
This is a permanent architectural constraint rather than a default waiting to
be revisited: data that cannot identify anyone cannot leak anyone.
`tests/unit/test_storage.py` reads the real `PRAGMA table_info` of every table
in a migrated database and fails on any column that looks like one, so the
constraint is enforced against the schema that actually exists rather than
against intent.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from ocura.infrastructure.storage.errors import FutureSchemaError

#: What this build writes and expects to read.
SCHEMA_VERSION = 4

#: The migration ledger. Not listed in MIGRATIONS on purpose: it has to exist
#: before the first step can record itself, including on a file that is being
#: created from nothing, so it cannot be one of the things a step creates.
VERSION_TABLE = "schema_version"

#: Step n takes a database at version n to version n + 1, so MIGRATIONS[0]
#: takes an empty file to version 1. Append; never edit one that has shipped.
MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        # `run` groups events into one launch of the application. It is a local
        # counter and nothing else: it says which run an event belongs to, and
        # carries no information about who or which machine produced it. It
        # exists because STARTED and STOPPED cannot delimit a run that ended in
        # a crash, and two runs merged into one would be history that never
        # happened.
        """
        CREATE TABLE events (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            run    INTEGER NOT NULL,
            at     TEXT    NOT NULL,
            kind   TEXT    NOT NULL,
            state  TEXT    NOT NULL,
            detail TEXT    NOT NULL DEFAULT ''
        )
        """,
        # Statistics ask "what happened today"; the dashboard asks "what
        # happened in this run". One index each.
        "CREATE INDEX events_at ON events (at)",
        "CREATE INDEX events_run ON events (run, id)",
    ),
    (
        # Seconds, and nullable rather than defaulted to zero: NULL means no
        # duration applies to this kind of event, which is a different fact
        # from a break that lasted no time at all. A break skipped instantly
        # and a session being paused must not read the same.
        #
        # REAL because the source is a monotonic clock in seconds. Rounding to
        # whole seconds at the point of storage would throw away the only
        # evidence that distinguishes a twenty-second break from one ended at
        # nineteen point nine.
        "ALTER TABLE events ADD COLUMN duration REAL",
    ),
    (
        # Settings, as name/value rather than a column each. A column each
        # would be a migration every time P6 adds a preference, and this table
        # will grow exactly that way; the type safety a column set would buy is
        # bought instead by `Settings`, which is what every reader goes
        # through and which refuses a value it cannot honour.
        #
        # Nothing identifying goes in here either. The constraint is about the
        # database, not about one table in it, and the test that enforces it
        # reads every table this migration leaves behind.
        """
        CREATE TABLE settings (
            name  TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    ),
    (
        # The focus block a row closed, in seconds at the screen. Before this,
        # each BREAK_DUE carried the time since its block began, and was
        # written again on every retry of a deferred break, so the statistics
        # page summed one absence into hundreds of hours. A block is now
        # measured once, on the row that ends it, in a column of its own
        # because that row is usually about another span: the break.
        #
        # Nothing is backfilled. Old BREAK_DUE durations cannot be told apart
        # into blocks, retries and absences after the fact, and no released
        # build ever wrote them.
        "ALTER TABLE events ADD COLUMN focus REAL",
    ),
)


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def migrate(connection: sqlite3.Connection) -> int:
    """Bring a database up to SCHEMA_VERSION. Idempotent; returns the version.

    Each step, the ledger row recording it and the version bump share one
    transaction, so a step that fails leaves the file exactly as it was. A
    half-applied migration carrying a version number that claims otherwise is a
    database that fails the same way on every launch afterwards, with no way
    back.
    """
    current = schema_version(connection)
    if current > SCHEMA_VERSION:
        raise FutureSchemaError(current, SCHEMA_VERSION)

    _ensure_ledger(connection, current)

    for version in range(current, SCHEMA_VERSION):
        connection.execute("BEGIN")
        try:
            for statement in MIGRATIONS[version]:
                connection.execute(statement)
            connection.execute(
                f"INSERT OR REPLACE INTO {VERSION_TABLE} (version, applied_at) VALUES (?, ?)",
                (version + 1, datetime.now(UTC).isoformat()),
            )
            # PRAGMA takes no bound parameter, so this one interpolation is
            # unavoidable. It is safe because `version` is a loop index over a
            # module constant and can never come from outside this process.
            connection.execute(f"PRAGMA user_version = {version + 1}")
        except sqlite3.Error:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    return schema_version(connection)


def migration_log(connection: sqlite3.Connection) -> list[tuple[int, str | None]]:
    """Every version this file has been through, oldest first.

    `applied_at` is None for a version that was applied before this build
    started keeping the ledger — which is every v1 database written by the
    first release. The version was reached; when is not recoverable, and
    inventing a timestamp for it would make the column worthless for the ones
    that are real.
    """
    rows = connection.execute(
        f"SELECT version, applied_at FROM {VERSION_TABLE} ORDER BY version"
    ).fetchall()
    return [(int(row[0]), row[1]) for row in rows]


def _ensure_ledger(connection: sqlite3.Connection, current: int) -> None:
    """Create the ledger if it is absent, and account for versions already applied.

    Outside the migration loop because the loop's first step has to be able to
    write into it.

    The existence check comes first so that opening an already-current database
    writes nothing whatsoever. That matters for a file the process cannot write
    to — one on a read-only volume, or locked down by policy — where reading
    the history back is still worth doing and a gratuitous CREATE TABLE IF NOT
    EXISTS would have refused the open outright.
    """
    if _has_ledger(connection):
        return

    connection.execute("BEGIN")
    try:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT
            )
            """
        )
        # A file written by the first release reached v1 with no ledger to
        # record it. Backfill the fact without the time: see migration_log.
        for version in range(1, current + 1):
            connection.execute(
                f"INSERT OR IGNORE INTO {VERSION_TABLE} (version, applied_at) VALUES (?, NULL)",
                (version,),
            )
    except sqlite3.Error:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def _has_ledger(connection: sqlite3.Connection) -> bool:
    found = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (VERSION_TABLE,)
    ).fetchone()
    return found is not None
