"""What the storage layer is allowed to raise at anything above it.

`sqlite3.Error` never leaves this package. The UI is forbidden from importing
`sqlite3` at all — `src/ocura/ui/.ruff.toml` enforces it — so a caller that had
to catch a sqlite3 exception could not be written without breaking the layering
that ban exists to protect.
"""

from __future__ import annotations


class StorageError(RuntimeError):
    """History could not be opened, written or read.

    Always survivable. Ocura keeps time with a monotonic clock and a state
    machine, neither of which needs a database, so every caller of this package
    is expected to carry on without one.
    """


class FutureSchemaError(StorageError):
    """The file was written by a newer Ocura than this one.

    Refused rather than migrated backwards. A newer version may have added a
    NOT NULL column this build knows nothing about, and writing into it would
    produce rows that the version the user actually uses cannot read. Losing
    history is bad; silently corrupting it is worse.
    """

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"history is at schema version {found}, this build understands {supported}"
        )
        self.found = found
        self.supported = supported
