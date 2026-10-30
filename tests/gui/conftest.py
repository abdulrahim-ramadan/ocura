from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="Qt is not installed")

if sys.platform.startswith("linux") and not (
    os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
):
    pytest.skip("no display available", allow_module_level=True)


def pytest_collection_modifyitems(items):
    # This hook is handed the whole collection even though it lives in a
    # subdirectory conftest, so mark only the tests that are actually ours.
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.gui)


@pytest.fixture
def icon():
    from ocura.ui.resources import app_icon

    return app_icon()


@pytest.fixture
def settings(tmp_path):
    """A throwaway INI so a test never touches the real registry keys."""
    from PySide6.QtCore import QSettings

    return QSettings(str(tmp_path / "ocura.ini"), QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def own_stylesheet(qapp):
    """Every test starts with the application's stylesheet as it found it.

    The stylesheet belongs to the QApplication the whole run shares, and a
    test that sets one and leaves it decides what the next test's widgets
    look like. Before this fixture, 88 of the GUI tests started under a
    stylesheet some earlier test had left, and the bar tests passed only
    because one had: the suite's verdict depended on its order.

    Asking for `qapp` is half the point. A test that builds a pixmap without
    one aborts the interpreter, with no traceback, unless an earlier test
    happened to create the application first.
    """
    was = qapp.styleSheet()
    yield
    qapp.setStyleSheet(was)


@pytest.fixture(autouse=True)
def own_translator():
    """Every test starts with Ocura's translator as it found it.

    The same leak as the stylesheet, one module over. `i18n.install` sets a
    global every later `translate` call goes through, and the language
    fixtures used to "restore" by applying English — which installs the
    English catalogue rather than removing anything. Every test after them,
    in this directory and in tests/unit, then ran with that catalogue, and
    one unit test passed only because of it: alone, it failed.
    """
    from ocura.application import i18n

    was = i18n.active()
    yield
    i18n.install(was)


@pytest.fixture(autouse=True)
def still():
    """Widget tests assert final values, so motion is off unless asked for.

    Animation is verified on its own terms in the motion tests rather than by
    making every other test wait for a fade to finish.
    """
    from ocura.ui.motion import MOTION

    was = MOTION.enabled
    MOTION.enabled = False
    yield MOTION
    MOTION.enabled = was
