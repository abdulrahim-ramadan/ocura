"""Local history, in one SQLite file. P4.

Nothing above this package imports `sqlite3` — the domain, the application
layer and the UI each ban it in their own `.ruff.toml` — so everything that
leaves here is a plain dataclass or a `StorageError`.

Opening one is two calls, kept separate because the connection outlives any
single store and the next thing P4 adds will want its own view of it:

    connection = open_database()
    store = EventStore.open(connection)
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from ocura.infrastructure.storage.database import (
    DATABASE_NAME,
    default_database_path,
    open_database,
)
from ocura.infrastructure.storage.errors import FutureSchemaError, StorageError
from ocura.infrastructure.storage.events import EventStore, StoredEvent, next_run
from ocura.infrastructure.storage.schema import (
    SCHEMA_VERSION,
    VERSION_TABLE,
    migrate,
    migration_log,
    schema_version,
)
from ocura.infrastructure.storage.settings import SettingsStore
from ocura.infrastructure.storage.statistics import StatisticsStore

#: The connection type, re-exported so that callers above this package can name
#: one without importing sqlite3 — which the domain, the application layer and
#: the UI are each banned from doing.
Connection = sqlite3.Connection

__all__ = [
    "DATABASE_NAME",
    "SCHEMA_VERSION",
    "VERSION_TABLE",
    "Connection",
    "EventStore",
    "FutureSchemaError",
    "SettingsStore",
    "StatisticsStore",
    "StorageError",
    "StoredEvent",
    "close_database",
    "default_database_path",
    "migrate",
    "migration_log",
    "next_run",
    "open_database",
    "open_event_store",
    "schema_version",
]


def open_event_store(path: Path | None = None) -> tuple[Connection, EventStore]:
    """The whole of it in one call, for a caller that only wants to write events."""
    connection = open_database(path)
    try:
        return connection, EventStore.open(connection)
    except StorageError:
        connection.close()
        raise


def close_database(connection: Connection | None) -> None:
    """Close without making the caller think about it, including at shutdown.

    A close that raises during quit would leave the tray icon on screen with no
    process behind it, so this reports nothing: there is no longer anybody to
    report to, and the write-ahead log is recovered on the next open regardless.
    """
    if connection is None:
        return
    with contextlib.suppress(sqlite3.Error):
        connection.close()
