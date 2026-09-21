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

from ocura.application.i18n import QT_TRANSLATE_NOOP, translate

#: Why a machine has no startup list at all. Marked here and translated where
#: it is raised: an `AutostartUnavailable` is one of the two exceptions in
#: Ocura whose message is shown to a person rather than written to a log, so
#: its text is language and belongs in the catalogue with the rest.
NO_STARTUP_LIST = QT_TRANSLATE_NOOP(
    "Autostart", "Ocura cannot manage startup entries on this machine."
)


class AutostartUnavailable(RuntimeError):
    """The startup entry could not be read or written, and why.

    **Its message is user-facing.** The settings page puts `str(exc)` under the
    control that caused it, which is the whole point of raising rather than
    logging — so every message handed to one is translated at the moment it is
    raised, and `tests/unit/test_no_bare_strings.py` checks that it is.
    """


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
        raise AutostartUnavailable(translate("Autostart", NO_STARTUP_LIST))
