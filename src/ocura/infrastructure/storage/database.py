"""Where the file lives, how it is opened, and the pragmas it is opened with.

One connection, on the Qt main thread, for the life of the process. Ocura
writes a handful of rows per break and reads on demand; a pool would be
machinery in service of nothing.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from ocura.infrastructure.storage.errors import StorageError
from ocura.infrastructure.storage.schema import migrate

logger = logging.getLogger(__name__)

APPLICATION_DIRECTORY = "Ocura"
DATABASE_NAME = "ocura.db"

#: Long enough to outlast another writer finishing a transaction, short enough
#: that a stuck one does not hold up the tick that draws the countdown.
BUSY_TIMEOUT_MS = 5000


def default_database_path() -> Path:
    """`%LOCALAPPDATA%\\Ocura\\ocura.db`.

    Local rather than Roaming on purpose. History is a record of what happened
    on *this* machine, it grows without a natural bound, and a roaming profile
    would copy all of it over the network at every sign-in to no benefit.
    """
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / APPLICATION_DIRECTORY / DATABASE_NAME


def open_database(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed), set the pragmas, and migrate. Never returns half-ready.

    Raises StorageError for anything that stopped that happening, so the caller
    has exactly one exception type to decide about and no reason to import
    sqlite3 itself.
    """
    target = path or default_database_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: this module manages its own transactions with
        # explicit BEGIN/COMMIT. sqlite3's implicit handling starts one before
        # DML but not before DDL, which is precisely the wrong way round for a
        # migration that has to be all-or-nothing.
        connection = sqlite3.connect(target, isolation_level=None)
    except (sqlite3.Error, OSError) as exc:
        raise StorageError(f"could not open history at {target}: {exc}") from exc

    connection.row_factory = sqlite3.Row
    try:
        _apply_pragmas(connection)
        migrate(connection)
    except sqlite3.Error as exc:
        connection.close()
        raise StorageError(f"could not prepare history at {target}: {exc}") from exc
    except StorageError:
        connection.close()
        raise

    return connection


def _apply_pragmas(connection: sqlite3.Connection) -> None:
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")

    # WAL keeps a reader from blocking the writer and survives a hard kill
    # better than the rollback journal. It is not available everywhere — a
    # network share refuses it — and SQLite reports the mode it actually
    # settled on rather than failing, so read the answer back instead of
    # assuming the request was honoured.
    mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if str(mode).lower() != "wal":
        logger.warning("history is in %s mode; WAL was refused for this file", mode)
    else:
        # Safe to relax only under WAL: a power cut can cost the last
        # transaction, never the integrity of the file.
        connection.execute("PRAGMA synchronous = NORMAL")
