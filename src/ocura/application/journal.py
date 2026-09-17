"""Where session events go to be kept, and the seam that keeps storage out of here.

The application layer produces `SessionEvent`s. It must not learn what a
database is, for the same reason it does not learn what a Windows API is: the
layer below supplies a thing with the right shape, and this layer only knows
the shape. `src/ocura/application/.ruff.toml` enforces that mechanically.

Three implementations exist. `ocura.infrastructure.storage.EventStore` writes
SQLite. Tests use a list. `NullJournal` is what runs when there is nowhere to
write, and the session behaves identically with it — which is the whole point:
history is a record of the product working, never a part of it working.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ocura.application.session import SessionEvent


@runtime_checkable
class SessionJournal(Protocol):
    """Somewhere durable for events to go. Write-only from up here.

    Reading history back is a query, and queries belong to whatever is asking
    the question — the Statistics view, later in P4 — not to the presenter,
    which already holds the events of the current run in memory.
    """

    def record(self, event: SessionEvent) -> None: ...


class NullJournal:
    """History is unavailable. Nothing else changes.

    Not an error state and not a degraded mode as far as the engine is
    concerned: the break timer is a monotonic clock and a state machine, and
    neither of them has ever needed a disk.
    """

    def record(self, event: SessionEvent) -> None:
        del event
