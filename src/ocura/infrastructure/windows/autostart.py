"""The Windows Run key, which is how a desktop application starts with Windows.

HKEY_CURRENT_USER, never HKEY_LOCAL_MACHINE. The per-user key needs no elevation
and affects only the person who asked; the machine-wide one would need Ocura to
ask for administrator rights to arrange its own start-up, which is a large
request for a small favour and would start it for people who never installed it.

No scheduled task either, for the same reason: registering one is a heavier
privilege and a heavier uninstall than a single registry value that the user
can also see and remove in Task Manager's Startup tab, where they will look for
it.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Callable

from ocura.application.autostart import AutostartUnavailable

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

#: The value name under that key. What the user sees in Task Manager's Startup
#: tab, so it is the product's name and nothing more technical.
VALUE_NAME = "Ocura"


def startup_command() -> str:
    """The command line that starts Ocura, quoted for the registry.

    A frozen build is one executable and says so. Running from a checkout,
    the interpreter is asked for the module — which works, and is honest about
    being a development arrangement rather than pretending a source tree is an
    installed application.
    """
    executable = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{executable}"'
    return f'"{executable}" -m ocura.ui.app'


class RegistryAutostart:
    """Reads and writes one value under the per-user Run key.

    The three winreg calls arrive as arguments so that every branch below is
    testable without touching the real registry of the machine running the
    tests — the same arrangement the detectors use for the Win32 API.
    """

    available = True

    def __init__(
        self,
        command: str | None = None,
        open_key: Callable[..., object] | None = None,
        read_value: Callable[[object, str], tuple[object, int]] | None = None,
        write_value: Callable[[object, str, int, int, str], None] | None = None,
        delete_value: Callable[[object, str], None] | None = None,
        root: object | None = None,
        access: tuple[int, int] | None = None,
    ) -> None:
        # Imported here rather than at module scope so this file stays
        # importable off Windows, which is what lets the tests above run
        # anywhere and what keeps `import ocura` from binding the registry.
        import winreg

        self._command = command or startup_command()
        self._open = open_key or winreg.OpenKey
        self._read = read_value or winreg.QueryValueEx
        self._write = write_value or winreg.SetValueEx
        self._delete = delete_value or winreg.DeleteValue
        self._root = root if root is not None else winreg.HKEY_CURRENT_USER
        self._read_access, self._write_access = access or (winreg.KEY_READ, winreg.KEY_SET_VALUE)
        self._string_type = winreg.REG_SZ

    def is_enabled(self) -> bool:
        """Whether the value is there. Never raises: a read is only ever a question.

        A missing value and an unreadable key are the same answer — Ocura will
        not start with Windows — and the difference is worth a log line rather
        than an exception the caller has to decide about on every render.
        """
        try:
            with self._open(self._root, RUN_KEY, 0, self._read_access) as key:  # type: ignore[union-attr]
                value, _ = self._read(key, VALUE_NAME)
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.warning("could not read the startup entry: %s", exc)
            return False
        return bool(value)

    def set_enabled(self, enabled: bool) -> None:
        """Add or remove the value. Raises AutostartUnavailable if it did not happen.

        Raising rather than reporting quietly, because this one is a direct
        answer to something the user just clicked: a switch that silently
        fails to move is worse than one that says why it could not.
        """
        try:
            with self._open(self._root, RUN_KEY, 0, self._write_access) as key:  # type: ignore[union-attr]
                if enabled:
                    self._write(key, VALUE_NAME, 0, self._string_type, self._command)
                else:
                    # Already absent is success. Asking for off and finding it
                    # off is not an error to report to somebody.
                    with contextlib.suppress(FileNotFoundError):
                        self._delete(key, VALUE_NAME)
        except OSError as exc:
            raise AutostartUnavailable(
                "Windows would not let Ocura change its start-up entry. "
                "You can add or remove it yourself in Task Manager, under Startup."
            ) from exc


def build_autostart() -> RegistryAutostart:
    return RegistryAutostart()
