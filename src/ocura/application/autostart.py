"""Whether Ocura starts with Windows, as a port rather than a registry call.

The registry is the truth and the setting is a record of what the user asked
for. They can disagree — somebody else's startup manager, a policy, a profile
copied between machines — and when they do, what the checkbox shows is what the
registry says, because that is what will actually happen at the next sign-in.

Every operation here is allowed to fail and none of them may take the
application with them. A machine where the Run key cannot be written is a
machine where Ocura still times breaks perfectly well.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class AutostartUnavailable(RuntimeError):
    """The startup entry could not be read or written, and why."""


@runtime_checkable
class Autostart(Protocol):
    """Reads and writes the machine's "run this at sign-in" list."""

    @property
    def available(self) -> bool:
        """False where there is no such list to write to at all."""
        ...

    def is_enabled(self) -> bool: ...

    def set_enabled(self, enabled: bool) -> None: ...


class NoAutostart:
    """There is no startup list here — another platform, or a locked-down one.

    Reports itself unavailable rather than pretending to be off, so a page can
    disable the control and say why instead of offering a switch that does
    nothing when flicked.
    """

    available = False

    def is_enabled(self) -> bool:
        return False

    def set_enabled(self, enabled: bool) -> None:
        del enabled
        raise AutostartUnavailable("Ocura cannot manage startup entries on this machine.")
