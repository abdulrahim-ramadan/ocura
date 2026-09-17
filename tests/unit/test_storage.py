"""Storage tests against real SQLite files on disk, never an in-memory stand-in.

`:memory:` is a different database engine configuration in the ways that matter
here: it cannot be in WAL mode, it has no parent directory to fail to create,
and it cannot be reopened, which is the whole subject of half of these tests. A
tmp_path file is the artifact the product actually writes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ocura.application.session import SessionEvent, SessionEventKind
from ocura.domain.timer import TimerState
from ocura.infrastructure.storage import (
    SCHEMA_VERSION,
    FutureSchemaError,
    StorageError,
    close_database,
    default_database_path,
    open_database,
    open_event_store,
    schema_version,
)
from ocura.infrastructure.storage import schema as schema_module

AT = datetime(2026, 9, 17, 14, 20, tzinfo=UTC)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "history" / "ocura.db"


def an_event(
    kind: SessionEventKind = SessionEventKind.BREAK_COMPLETED,
    at: datetime = AT,
    state: TimerState = TimerState.FOCUSING,
    detail: str = "",
) -> SessionEvent:
    return SessionEvent(kind=kind, at=at, state=state, detail=detail)


# --- opening and migrating -------------------------------------------------


def test_opening_an_empty_location_creates_a_migrated_database(database_path: Path):
    connection = open_database(database_path)
    try:
        assert database_path.is_file()
        assert schema_version(connection) == SCHEMA_VERSION
    finally:
        close_database(connection)


def test_the_parent_directory_is_created(database_path: Path):
    assert not database_path.parent.exists()
    connection = open_database(database_path)
    close_database(connection)
    assert database_path.parent.is_dir()


def test_reopening_keeps_the_rows_and_migrates_nothing(database_path: Path):
    connection, store = open_event_store(database_path)
    store.record(an_event())
    close_database(connection)

    connection, store = open_event_store(database_path)
    try:
        assert schema_version(connection) == SCHEMA_VERSION
        assert store.count() == 1
    finally:
        close_database(connection)


def test_a_database_from_a_newer_ocura_is_refused_rather_than_downgraded(database_path: Path):
    """A newer build may have added a column this one would write nulls into."""
    connection = open_database(database_path)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    close_database(connection)

    with pytest.raises(FutureSchemaError) as raised:
        open_database(database_path)
    assert raised.value.found == SCHEMA_VERSION + 5
    assert raised.value.supported == SCHEMA_VERSION

    # And it left the file exactly as it found it.
    probe = sqlite3.connect(database_path)
    try:
        assert probe.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 5
    finally:
        probe.close()


def test_a_failing_migration_step_leaves_the_version_where_it_was(database_path: Path, monkeypatch):
    """A half-applied migration claiming to be complete fails forever, silently."""
    monkeypatch.setattr(
        schema_module,
        "MIGRATIONS",
        (("CREATE TABLE fine (id INTEGER)", "THIS IS NOT SQL"),),
    )

    with pytest.raises(StorageError):
        open_database(database_path)

    probe = sqlite3.connect(database_path)
    try:
        assert probe.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = [row[0] for row in probe.execute("SELECT name FROM sqlite_master")]
        assert "fine" not in tables, "the successful half of the migration survived"
    finally:
        probe.close()


def test_a_path_that_cannot_be_opened_raises_storage_error_not_sqlite3(tmp_path: Path):
    """Callers above infrastructure are banned from importing sqlite3 at all."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StorageError):
        open_database(blocker / "ocura.db")


def test_the_database_is_in_wal_mode(database_path: Path):
    """Read back rather than assumed: SQLite reports the mode it settled on."""
    connection = open_database(database_path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        close_database(connection)


def test_the_default_path_is_under_local_appdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\someone\AppData\Local")
    path = default_database_path()

    assert path.name == "ocura.db"
    assert path.parent.name == "Ocura"
    # Local, not Roaming: history is machine-local and grows without a bound.
    assert "Roaming" not in str(path)


# --- the permanent constraint ----------------------------------------------

#: Anything that could name a person or a machine. The roadmap's wording is
#: "no user identifier in the schema, ever — not a UUID, not a machine ID, not
#: a hashed one", and this is that sentence in a form CI can fail on.
FORBIDDEN_COLUMN_WORDS = (
    "user",
    "uuid",
    "guid",
    "machine",
    "device",
    "host",
    "account",
    "email",
    "username",
    "install",
    "client",
    "person",
    "hash",
    "fingerprint",
)


def test_no_table_carries_anything_that_could_identify_anyone(database_path: Path):
    """Read off the real migrated schema, not off the DDL we meant to write."""
    connection = open_database(database_path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        assert tables, "the schema created no tables at all"

        offenders = []
        for table in tables:
            for column in connection.execute(f"PRAGMA table_info({table})"):
                name = column["name"].lower()
                offenders += [
                    f"{table}.{column['name']}" for word in FORBIDDEN_COLUMN_WORDS if word in name
                ]
        assert offenders == []
    finally:
        close_database(connection)


def test_the_run_column_is_a_counter_and_not_an_identity(database_path: Path):
    """`run` groups events by launch. It must start at 1 and mean nothing else."""
    connection, first = open_event_store(database_path)
    assert first.run == 1
    first.record(an_event())
    close_database(connection)

    connection, second = open_event_store(database_path)
    try:
        assert second.run == 2
    finally:
        close_database(connection)


# --- writing and reading back ----------------------------------------------


def test_an_event_round_trips(database_path: Path):
    connection, store = open_event_store(database_path)
    try:
        store.record(
            an_event(
                kind=SessionEventKind.BREAK_DEFERRED,
                state=TimerState.DEFERRED,
                detail="session locked",
            )
        )
        (stored,) = store.recent()

        assert stored.kind == SessionEventKind.BREAK_DEFERRED
        assert stored.event_kind is SessionEventKind.BREAK_DEFERRED
        assert stored.state == TimerState.DEFERRED
        assert stored.detail == "session locked"
        assert stored.at == AT
        assert stored.run == store.run
    finally:
        close_database(connection)


def test_a_timestamp_comes_back_aware_and_in_utc(database_path: Path):
    """A log ordered in mixed timezones is not ordered."""
    elsewhere = AT.astimezone(timezone(timedelta(hours=9)))
    connection, store = open_event_store(database_path)
    try:
        store.record(an_event(at=elsewhere))
        (stored,) = store.recent()

        assert stored.at.tzinfo is not None
        assert stored.at.utcoffset() == timedelta(0)
        assert stored.at == elsewhere
    finally:
        close_database(connection)


def test_recent_returns_the_newest_first_and_honours_its_limit(database_path: Path):
    connection, store = open_event_store(database_path)
    try:
        for index in range(5):
            store.record(an_event(detail=str(index)))

        recent = store.recent(limit=3)
        assert [stored.detail for stored in recent] == ["4", "3", "2"]
    finally:
        close_database(connection)


def test_one_run_can_be_read_back_on_its_own(database_path: Path):
    connection, first = open_event_store(database_path)
    first.record(an_event(detail="first run"))
    close_database(connection)

    connection, second = open_event_store(database_path)
    try:
        second.record(an_event(detail="second run"))

        assert [stored.detail for stored in second.for_run()] == ["second run"]
        assert [stored.detail for stored in second.for_run(1)] == ["first run"]
        assert second.count() == 2
    finally:
        close_database(connection)


def test_a_kind_this_build_has_never_heard_of_reads_back_without_crashing(database_path: Path):
    """Old history written by a newer Ocura must still be readable."""
    connection, store = open_event_store(database_path)
    try:
        connection.execute(
            "INSERT INTO events (run, at, kind, state, detail) VALUES (?, ?, ?, ?, ?)",
            (store.run, AT.isoformat(), "posture_corrected", "focusing", ""),
        )
        (stored,) = store.recent()

        assert stored.kind == "posture_corrected"
        assert stored.event_kind is None
    finally:
        close_database(connection)


def test_writing_to_a_closed_database_reports_rather_than_returns_quietly(database_path: Path):
    connection, store = open_event_store(database_path)
    close_database(connection)

    with pytest.raises(StorageError):
        store.record(an_event())
