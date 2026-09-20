"""The Windows Run key, driven against a fake registry.

Never the real one. A test that wrote to HKCU\\...\\Run would add Ocura to the
startup list of whoever ran the suite, and a test that read it would pass or
fail depending on whether they happened to have it installed. The three winreg
calls arrive as arguments precisely so this file can supply its own.
"""

from __future__ import annotations

import pytest

from ocura.application.autostart import Autostart, AutostartUnavailable, NoAutostart
from ocura.infrastructure.windows.autostart import (
    RUN_KEY,
    VALUE_NAME,
    RegistryAutostart,
    startup_command,
)


class FakeKey:
    def __init__(self, registry: FakeRegistry) -> None:
        self.registry = registry

    def __enter__(self) -> FakeKey:
        return self

    def __exit__(self, *exception: object) -> bool:
        return False


class FakeRegistry:
    """One key, its values, and whatever it has been told to refuse."""

    def __init__(self, values: dict[str, str] | None = None, refuse: type | None = None) -> None:
        self.values = dict(values or {})
        self.refuse = refuse
        self.opened: list[str] = []

    def open_key(self, root, path, reserved, access):
        del root, reserved, access
        self.opened.append(path)
        if self.refuse is not None:
            raise self.refuse("the registry said no")
        return FakeKey(self)

    def read(self, key, name):
        del key
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], 1

    def write(self, key, name, reserved, kind, value):
        del key, reserved, kind
        self.values[name] = value

    def delete(self, key, name):
        del key
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def an_autostart(registry: FakeRegistry, command: str = '"C:\\Ocura.exe"') -> RegistryAutostart:
    return RegistryAutostart(
        command=command,
        open_key=registry.open_key,
        read_value=registry.read,
        write_value=registry.write,
        delete_value=registry.delete,
        root=object(),
        access=(0, 0),
    )


# --- reading ---------------------------------------------------------------


def test_an_absent_value_means_it_will_not_start():
    assert an_autostart(FakeRegistry()).is_enabled() is False


def test_a_present_value_means_it_will():
    registry = FakeRegistry({VALUE_NAME: '"C:\\Ocura.exe"'})

    assert an_autostart(registry).is_enabled() is True
    assert registry.opened == [RUN_KEY]


def test_an_unreadable_key_is_the_same_answer_as_an_absent_value(caplog):
    """Ocura will not start with Windows either way, and a read is only ever a
    question — the caller renders a checkbox, it cannot handle an exception."""
    registry = FakeRegistry(refuse=PermissionError)

    assert an_autostart(registry).is_enabled() is False
    assert any("could not read" in record.message for record in caplog.records)


# --- writing ---------------------------------------------------------------


def test_turning_it_on_writes_the_command():
    registry = FakeRegistry()

    an_autostart(registry, command='"C:\\Ocura.exe"').set_enabled(True)

    assert registry.values[VALUE_NAME] == '"C:\\Ocura.exe"'


def test_turning_it_off_removes_the_value():
    registry = FakeRegistry({VALUE_NAME: '"C:\\Ocura.exe"'})

    an_autostart(registry).set_enabled(False)

    assert VALUE_NAME not in registry.values


def test_turning_off_something_already_off_is_success_not_an_error():
    """Asking for off and finding it off is what was wanted."""
    an_autostart(FakeRegistry()).set_enabled(False)


def test_a_refused_write_raises_with_something_the_user_can_act_on():
    registry = FakeRegistry(refuse=PermissionError)

    with pytest.raises(AutostartUnavailable) as raised:
        an_autostart(registry).set_enabled(True)

    assert "Task Manager" in str(raised.value), "no way out was offered"


def test_a_refused_write_does_not_leave_a_half_written_entry():
    registry = FakeRegistry(refuse=OSError)

    with pytest.raises(AutostartUnavailable):
        an_autostart(registry).set_enabled(True)

    assert registry.values == {}


def test_it_writes_to_the_per_user_key_and_not_the_machine_one():
    """HKLM would need elevation for a small favour and would start Ocura for
    people who never installed it."""
    registry = FakeRegistry()
    an_autostart(registry).set_enabled(True)

    assert registry.opened == [RUN_KEY]
    assert not RUN_KEY.lower().startswith("hkey_local_machine")


# --- the command it writes -------------------------------------------------


def test_the_startup_command_is_quoted():
    """An unquoted path with a space in it is two arguments to Windows."""
    command = startup_command()

    assert command.startswith('"')
    assert '"' in command[1:]


def test_a_frozen_build_is_just_the_executable(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", r"C:\Program Files\Ocura\Ocura.exe")

    assert startup_command() == r'"C:\Program Files\Ocura\Ocura.exe"'


def test_a_checkout_asks_the_interpreter_for_the_module(monkeypatch):
    monkeypatch.delattr("sys.frozen", raising=False)
    monkeypatch.setattr("sys.executable", r"C:\Python\python.exe")

    assert startup_command() == r'"C:\Python\python.exe" -m ocura.ui.app'


# --- the stand-in ----------------------------------------------------------


def test_the_stand_in_reports_itself_unavailable_rather_than_off():
    """So a page can disable the control and say why, instead of offering a
    switch that does nothing when it is flicked."""
    stand_in = NoAutostart()

    assert isinstance(stand_in, Autostart)
    assert stand_in.available is False
    assert stand_in.is_enabled() is False
    with pytest.raises(AutostartUnavailable):
        stand_in.set_enabled(True)


def test_the_real_one_satisfies_the_protocol():
    assert isinstance(an_autostart(FakeRegistry()), Autostart)
