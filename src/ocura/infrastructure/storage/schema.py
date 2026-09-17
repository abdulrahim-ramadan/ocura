"""The schema, and the only route a file takes from one version to the next.

Migrations are a tuple in a module, not a directory of numbered files. At this
size the entire history fits on one screen, and a step that cannot be read next
to the one before it is a step nobody will check.

`PRAGMA user_version` is the version marker rather than a table of our own. It
is one integer in the database header, it is written inside the same
transaction as the DDL it describes, and it therefore cannot get out of step
with the schema it claims to describe.

**No user identifier, ever.** Not a UUID, not a machine ID, not a hashed one.
This is a permanent architectural constraint rather than a default waiting to
be revisited: data that cannot identify anyone cannot leak anyone.
`tests/unit/test_storage.py` reads the real `PRAGMA table_info` of a migrated
database and fails on any column that looks like one, so the constraint is
enforced against the schema that actually exists rather than against intent.
"""

from __future__ import annotations

import sqlite3

from ocura.infrastructure.storage.errors import FutureSchemaError

#: What this build writes and expects to read.
SCHEMA_VERSION = 1

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
)


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def migrate(connection: sqlite3.Connection) -> int:
    """Bring a database up to SCHEMA_VERSION. Idempotent; returns the version.

    Each step and the version bump that records it share one transaction, so a
    step that fails leaves the file exactly as it was. A half-applied migration
    carrying a version number that claims otherwise is a database that fails
    the same way on every launch afterwards, with no way back.
    """
    current = schema_version(connection)
    if current > SCHEMA_VERSION:
        raise FutureSchemaError(current, SCHEMA_VERSION)

    for version in range(current, SCHEMA_VERSION):
        connection.execute("BEGIN")
        try:
            for statement in MIGRATIONS[version]:
                connection.execute(statement)
            # PRAGMA takes no bound parameter, so this one interpolation is
            # unavoidable. It is safe because `version` is a loop index over a
            # module constant and can never come from outside this process.
            connection.execute(f"PRAGMA user_version = {version + 1}")
        except sqlite3.Error:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    return schema_version(connection)
