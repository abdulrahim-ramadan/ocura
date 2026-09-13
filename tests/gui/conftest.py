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
