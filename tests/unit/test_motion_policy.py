"""The motion policy, enforced by reading the UI package rather than trusting it.

Ocura's dashboard is a glance surface. Peripheral motion pulls the eye
involuntarily, so anything that moves while the state is unchanged is
interrupting the user without asking — which is the behaviour this whole product
exists to avoid. These tests fail the build if such a thing is added.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[2] / "src" / "ocura" / "ui"

#: The one repeating timer in the application: the tick that drives the engine.
#: It is state-driven by definition — the state it reports is the passage of time.
TICK_OWNER = "driver.py"


def modules() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in sorted(UI.glob("*.py"))]


def calls_named(tree: ast.Module, names: set[str]) -> list[ast.Call]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        label = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if label in names:
            found.append(node)
    return found


def test_only_the_tick_driver_owns_a_repeating_timer():
    offenders = [
        path.name
        for path, tree in modules()
        if path.name != TICK_OWNER and calls_named(tree, {"QTimer", "startTimer"})
    ]
    assert offenders == []


def test_nothing_loops():
    """An animation that repeats is motion with no state change behind it."""
    offenders = []
    for path, tree in modules():
        for call in calls_named(tree, {"setLoopCount"}):
            argument = call.args[0] if call.args else None
            if not isinstance(argument, ast.Constant) or argument.value != 1:
                offenders.append(f"{path.name}:{call.lineno}")
    assert offenders == []


def test_no_looping_media_widgets():
    banned = {"QMovie", "QSequentialAnimationGroup", "QTimeLine"}
    offenders = [
        f"{path.name}: {name}"
        for path, tree in modules()
        for name in banned
        if calls_named(tree, {name})
    ]
    assert offenders == []


def test_animations_are_created_in_one_place():
    """Motion is a policy, not something a widget decides for itself."""
    offenders = [
        path.name
        for path, tree in modules()
        if path.name != "motion.py" and calls_named(tree, {"QPropertyAnimation"})
    ]
    assert offenders == []


def test_the_dashboard_only_fades_on_a_state_change():
    """The fade must be guarded by a comparison, not run on every render."""
    source = (UI / "views.py").read_text(encoding="utf-8")
    assert "if view.headline != self._last_headline:" in source
    assert source.count("MOTION.fade_in") == 1


@pytest.mark.parametrize("name", ["FADE_MS", "FILL_MS"])
def test_durations_are_short_and_bounded(name: str):
    from ocura.ui import motion

    value = getattr(motion, name)
    assert 0 < value <= 1000


def test_page_transitions_are_the_agreed_duration():
    from ocura.ui.motion import FADE_MS

    assert FADE_MS == 200


def test_reduced_motion_defaults_to_allowing_motion_when_it_cannot_be_read(monkeypatch):
    """A failed read is not consent to remove motion, nor to force it on."""
    from ocura.ui import motion

    monkeypatch.setattr(motion, "reduced_motion", lambda: False)
    assert motion.Motion.from_system().enabled is True

    monkeypatch.setattr(motion, "reduced_motion", lambda: True)
    assert motion.Motion.from_system().enabled is False
