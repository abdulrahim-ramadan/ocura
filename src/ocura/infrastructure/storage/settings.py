"""Settings, in the same file as the history. One place to back up, one to lose.

Stored as name/value text. Everything that reads them comes back through
`Settings`, which refuses a combination it cannot honour, so the typing that a
column-per-setting would have bought is bought there instead — and adding a
preference in P6 is a row rather than a migration.

A value that cannot be read is replaced by its default and logged, not raised.
A hand-edited or half-written row is a reason to start with sensible settings
and say so; it is not a reason to refuse to start, which would leave the user
with no way back into the application that owns the file.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import fields

from ocura.application.settings import DEFAULTS, InvalidSettings, Settings
from ocura.infrastructure.storage.errors import StorageError

logger = logging.getLogger(__name__)

TABLE = "settings"


class SettingsStore:
    """Loads and saves one `Settings`. Owns no connection lifetime."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def load(self) -> Settings:
        """The stored settings, or the defaults for anything unreadable."""
        try:
            rows = self._connection.execute(f"SELECT name, value FROM {TABLE}").fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"could not read settings: {exc}") from exc

        stored = {row[0]: row[1] for row in rows}
        known = {field.name: field.type for field in fields(Settings)}
        values: dict[str, object] = {}
        for name, raw in stored.items():
            if name not in known:
                # Written by a newer Ocura that knows a preference this build
                # does not. Left alone rather than dropped: saving must not
                # quietly delete the other build's settings.
                continue
            parsed = _parse(name, raw)
            if parsed is not None:
                values[name] = parsed

        candidate = DEFAULTS.replace(**values)
        try:
            return candidate.validate()
        except InvalidSettings as exc:
            logger.warning("stored settings are not usable (%s); starting from defaults", exc)
            return DEFAULTS

    def save(self, settings: Settings) -> None:
        """Write every field, in one transaction.

        All of them rather than a diff: a partial write is a settings file that
        half agrees with the object the application is running on, and there
        are nine rows.
        """
        try:
            self._connection.execute("BEGIN")
            try:
                self._connection.executemany(
                    f"INSERT OR REPLACE INTO {TABLE} (name, value) VALUES (?, ?)",
                    [
                        (field.name, _render(getattr(settings, field.name)))
                        for field in fields(Settings)
                    ],
                )
            except sqlite3.Error:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")
        except sqlite3.Error as exc:
            raise StorageError(f"could not save settings: {exc}") from exc


def _render(value: object) -> str:
    if isinstance(value, bool):
        # Before the numeric branch: bool is an int, and "True" would then be
        # written as "1" by one path and parsed as a float by the other.
        return "1" if value else "0"
    return str(value)


def _parse(name: str, raw: object) -> object | None:
    """Turn one stored string back into a value, or None if it is unreadable."""
    text = str(raw).strip()
    default = getattr(DEFAULTS, name)
    try:
        if isinstance(default, bool):
            return text in ("1", "true", "True")
        if isinstance(default, float | int):
            return float(text)
        return text
    except ValueError:
        logger.warning("setting %r holds %r, which is not a number; using the default", name, raw)
        return None
