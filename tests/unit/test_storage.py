"""Storage tests against real SQLite files on disk, never an in-memory stand-in.

`:memory:` is a different database engine configuration in the ways that matter
here: it cannot be in WAL mode, it has no parent directory to fail to create,
and it cannot be reopened, which is the whole subject of half of these tests. A
tmp_path file is the artifact the product actually writes.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ocura.application.presenter import BreakPresenter
from ocura.application.session import SessionEvent, SessionEventKind
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerState
from ocura.infrastructure.storage import (
    SCHEMA_VERSION,
    FutureSchemaError,
    StorageError,
    close_database,
    default_database_path,
    migration_log,
    open_database,
    open_event_store,
    schema_version,
)
from ocura.infrastructure.storage import schema as schema_module

from .conftest import FakeMonotonicClock, FakeWallClock, ScriptedContext

AT = datetime(2026, 9, 17, 14, 20, tzinfo=UTC)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "history" / "ocura.db"


def an_event(
    kind: SessionEventKind = SessionEventKind.BREAK_COMPLETED,
    at: datetime = AT,
    state: TimerState = TimerState.FOCUSING,
    detail: str = "",
    duration: float | None = None,
) -> SessionEvent:
    return SessionEvent(kind=kind, at=at, state=state, detail=detail, duration=duration)


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


# --- the upgrade path, exercised on a real v1 file -------------------------


def a_v1_database(path: Path, monkeypatch) -> None:
    """Write a file exactly as the first release wrote one, then leave it alone.

    Built by running the real migration machinery with SCHEMA_VERSION pinned to
    1 rather than by hand-writing the v1 DDL into the test: a hand copy is free
    to drift from the shipped step it claims to reproduce, and an upgrade test
    against a v1 that was never shipped tests nothing.

    The ledger is then dropped, because the first release had none. A file that
    predates the ledger is the case that actually exists on testers' machines.
    """
    monkeypatch.setattr(schema_module, "SCHEMA_VERSION", 1)
    connection = open_database(path)
    try:
        connection.execute(f"DROP TABLE {schema_module.VERSION_TABLE}")
        for index in range(3):
            connection.execute(
                "INSERT INTO events (run, at, kind, state, detail) VALUES (?, ?, ?, ?, ?)",
                (1, AT.isoformat(), "break_completed", "focusing", f"v1 row {index}"),
            )
        assert schema_version(connection) == 1
    finally:
        close_database(connection)
    monkeypatch.setattr(schema_module, "SCHEMA_VERSION", SCHEMA_VERSION)


def test_a_v1_database_upgrades_and_its_rows_survive(database_path: Path, monkeypatch):
    """The whole reason the upgrade path exists before anything needs it."""
    a_v1_database(database_path, monkeypatch)

    connection, store = open_event_store(database_path)
    try:
        assert schema_version(connection) == SCHEMA_VERSION

        rows = store.for_run(1)
        assert [stored.detail for stored in rows] == ["v1 row 0", "v1 row 1", "v1 row 2"]
        assert all(stored.kind == SessionEventKind.BREAK_COMPLETED for stored in rows)
        assert all(stored.at == AT for stored in rows)
        # The column the upgrade added, on rows written before it existed. Not
        # zero: nobody measured these, and a backfilled zero would be a
        # measurement nobody took.
        assert all(stored.duration is None for stored in rows)
    finally:
        close_database(connection)


def test_an_upgraded_database_then_takes_new_rows_with_durations(database_path: Path, monkeypatch):
    """An upgrade that keeps the old rows but cannot accept new ones is half of one."""
    a_v1_database(database_path, monkeypatch)

    connection, store = open_event_store(database_path)
    try:
        store.record(an_event(kind=SessionEventKind.BREAK_COMPLETED, duration=20.0))

        assert store.recent(limit=1)[0].duration == 20.0
        assert store.count() == 4
    finally:
        close_database(connection)


def test_upgrading_twice_changes_nothing_the_second_time(database_path: Path, monkeypatch):
    a_v1_database(database_path, monkeypatch)

    close_database(open_database(database_path))

    connection, store = open_event_store(database_path)
    try:
        assert schema_version(connection) == SCHEMA_VERSION
        assert store.count() == 3
        versions = [version for version, _ in migration_log(connection)]
        assert versions == list(range(1, SCHEMA_VERSION + 1))
    finally:
        close_database(connection)


def test_the_ledger_records_every_version_a_fresh_file_went_through(database_path: Path):
    connection = open_database(database_path)
    try:
        log = migration_log(connection)
        assert [version for version, _ in log] == list(range(1, SCHEMA_VERSION + 1))
        # Applied by this build, just now, so every one of them has a real time.
        for version, applied_at in log:
            assert applied_at is not None, f"version {version} was recorded without a time"
            assert datetime.fromisoformat(applied_at).tzinfo is not None
    finally:
        close_database(connection)


def test_a_version_applied_before_the_ledger_existed_is_recorded_without_a_time(
    database_path: Path, monkeypatch
):
    """NULL rather than an invented timestamp. When is not recoverable."""
    a_v1_database(database_path, monkeypatch)

    connection = open_database(database_path)
    try:
        log = dict(migration_log(connection))
        assert log[1] is None, "the time of a v1 upgrade nobody recorded was invented"
        assert log[SCHEMA_VERSION] is not None, "the upgrade this build did went unrecorded"
    finally:
        close_database(connection)


def test_the_pragma_is_the_marker_and_the_ledger_never_overrides_it(database_path: Path):
    """Two records of the version would be two things free to disagree.

    migrate() reads the pragma and nothing else, so a ledger that has been
    tampered with, truncated or dropped cannot make a v2 file behave like a v1
    and have the migrations run over it a second time.
    """
    connection = open_database(database_path)
    connection.execute(f"DELETE FROM {schema_module.VERSION_TABLE}")
    close_database(connection)

    connection = open_database(database_path)
    try:
        assert schema_version(connection) == SCHEMA_VERSION
        # Nothing re-ran: a second pass over migration 2 would have failed on a
        # duplicate column, and the table is still the migrated one.
        columns = [row["name"] for row in connection.execute("PRAGMA table_info(events)")]
        assert columns.count("duration") == 1
    finally:
        close_database(connection)


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


# --- durations -------------------------------------------------------------


def test_a_duration_round_trips_and_absent_is_not_zero(database_path: Path):
    """NULL means no duration applies. 0.0 means one applied and was nothing."""
    connection, store = open_event_store(database_path)
    try:
        store.record(an_event(kind=SessionEventKind.STARTED))
        store.record(an_event(kind=SessionEventKind.BREAK_SKIPPED, duration=19.5))

        by_kind = {stored.kind: stored for stored in store.recent()}
        assert by_kind[SessionEventKind.STARTED].duration is None
        assert by_kind[SessionEventKind.BREAK_SKIPPED].duration == 19.5
    finally:
        close_database(connection)


def test_a_zero_duration_survives_as_zero_and_not_as_absent(database_path: Path):
    """A break ended the instant it began must not read as one with no duration."""
    connection, store = open_event_store(database_path)
    try:
        store.record(an_event(kind=SessionEventKind.BREAK_SKIPPED, duration=0.0))
        (stored,) = store.recent()

        assert stored.duration is not None
        assert stored.duration == 0.0
    finally:
        close_database(connection)


def test_fractional_seconds_are_not_rounded_away(database_path: Path):
    """The evidence that a twenty-second break was cut at 19.9 is the .9."""
    connection, store = open_event_store(database_path)
    try:
        store.record(an_event(duration=19.937))
        (stored,) = store.recent()

        assert stored.duration == pytest.approx(19.937)
    finally:
        close_database(connection)


def test_every_kind_of_break_event_can_be_told_apart_in_the_log(database_path: Path):
    """Offered, taken, ended early, postponed by whom, and discharged by a rest.

    The list the schema exists to answer questions about. If two of these ever
    collapse into one kind, the question "how many breaks did you actually
    take" stops having an answer.
    """
    kinds = (
        SessionEventKind.BREAK_DUE,
        SessionEventKind.BREAK_STARTED,
        SessionEventKind.BREAK_STARTED_BY_USER,
        SessionEventKind.BREAK_COMPLETED,
        SessionEventKind.BREAK_SKIPPED,
        SessionEventKind.BREAK_DEFERRED,
        SessionEventKind.BREAK_SNOOZED,
        SessionEventKind.BREAK_SATISFIED,
    )
    connection, store = open_event_store(database_path)
    try:
        for kind in kinds:
            store.record(an_event(kind=kind))

        stored = {row.kind for row in store.recent()}
        assert stored == {str(kind) for kind in kinds}
        assert len(stored) == len(kinds), "two kinds were flattened into one"
    finally:
        close_database(connection)


# --- a failed write costs history and never a break ------------------------


def make_read_only(path: Path) -> None:
    """Everything SQLite would have to write to, not only the main file."""
    companions = (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm"))
    for companion in companions:
        if companion.exists():
            os.chmod(companion, stat.S_IREAD)


def make_writable(path: Path) -> None:
    """Undo it, or the temporary directory cannot be cleaned up on Windows."""
    companions = (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm"))
    for companion in companions:
        if companion.exists():
            os.chmod(companion, stat.S_IWRITE)


def test_a_read_only_database_still_reads_and_refuses_the_write(database_path: Path):
    """The shape of a locked-down profile, an antivirus hold, a read-only volume.

    History that cannot be added to is still history worth reading, so the open
    is expected to succeed. The write is expected to fail honestly, as a
    StorageError and never as a sqlite3 exception, which no caller above this
    package is allowed to catch.
    """
    connection, store = open_event_store(database_path)
    store.record(an_event(detail="written while it was still writable"))
    close_database(connection)
    make_read_only(database_path)

    connection, store = open_event_store(database_path)
    try:
        assert store.count() == 1, "a read-only file must still be readable"
        assert store.recent()[0].detail == "written while it was still writable"

        with pytest.raises(StorageError):
            store.record(an_event(detail="this one cannot land"))
    finally:
        close_database(connection)
        make_writable(database_path)


def test_a_read_only_database_does_not_interrupt_a_break(database_path: Path, caplog):
    """The requirement, end to end: the engine runs on a file it cannot write to.

    Not a stand-in journal that raises on cue, but the real EventStore on a real
    file the process genuinely cannot write to, behind the real presenter. A
    stand-in proves the presenter survives what the test author imagined; this
    proves it survives what the filesystem actually does.
    """
    close_database(open_database(database_path))
    make_read_only(database_path)

    connection, store = open_event_store(database_path)
    try:
        schedule = BreakSchedule(focus_interval=1200.0, break_duration=30.0, defer_interval=300.0)
        clock = FakeMonotonicClock()
        presenter = BreakPresenter(
            schedule, clock, FakeWallClock(), ScriptedContext(), journal=store
        )

        presenter.start()
        clock.advance(schedule.focus_interval)
        view = presenter.tick()
        assert view.state is TimerState.ON_BREAK, "a failed write stopped the break starting"

        clock.advance(schedule.break_duration)
        view = presenter.tick()
        assert view.state is TimerState.FOCUSING, "a failed write stopped the break finishing"
        assert view.breaks_taken == 1

        # It cost the user their history, said so, and cost them nothing else.
        assert store.count() == 0
        assert any("history is incomplete" in record.message for record in caplog.records)
    finally:
        close_database(connection)
        make_writable(database_path)


def test_writing_to_a_closed_database_reports_rather_than_returns_quietly(database_path: Path):
    connection, store = open_event_store(database_path)
    close_database(connection)

    with pytest.raises(StorageError):
        store.record(an_event())
