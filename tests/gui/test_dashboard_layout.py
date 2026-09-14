"""Regression tests for the overlapping status card.

The visible fault was the headline and the countdown printed on top of each
other. The cause was not duplicated widgets — the card holds exactly the right
ones — but widgets allocated less height than their text needs: a 44px
countdown drawn into a 20px box spills out of its rectangle and collides with
its neighbour, while `geometry().intersects()` stays False throughout.

So there are two kinds of test here. The widget count catches a structural
regression, and the height assertions catch the one that actually happened.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QProgressBar

from ocura.domain.timer import TimerState
from ocura.ui.views import DashboardView

from .test_shell import a_view

#: Everything in the status card whose text is sized by the theme and must
#: therefore be given the room it asks for.
SIZED_LABELS = ("_headline", "_display", "_detail")


def height_needed(label) -> int:
    """What the text actually needs at the width it actually has.

    Not sizeHint(): for a word-wrapping QLabel that is the one-line size and is
    routinely larger than the laid-out height without anything being wrong,
    which makes it useless as a squeeze test.
    """
    if label.hasHeightForWidth():
        return label.heightForWidth(label.width())
    return label.sizeHint().height()


def squeezed(dashboard) -> list[str]:
    return [
        name
        for name in SIZED_LABELS
        if getattr(dashboard, name).height() < height_needed(getattr(dashboard, name))
    ]


def a_focusing_view(**overrides):
    defaults = {
        "state": TimerState.FOCUSING,
        "headline": "Focusing",
        "detail": "Next break in 19:49.",
        "countdown_text": "19:49",
    }
    return a_view(**(defaults | overrides))


def test_the_status_card_holds_exactly_one_of_each_widget(qtbot, qapp):
    """Structural: nothing is added twice, however many times it is rendered."""
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.resize(880, 660)
    dashboard.show()

    for second in range(100):
        dashboard.render(a_focusing_view(countdown_text=f"19:{second % 60:02d}"))
    qtbot.wait(50)

    labels = dashboard._status.findChildren(QLabel)
    bars = dashboard._status.findChildren(QProgressBar)

    assert len(bars) == 1, "more than one progress bar in the status card"
    # headline, countdown, detail, waiting note.
    assert len(labels) == 4, [label.text() for label in labels]
    assert labels.count(dashboard._display) == 1
    assert labels.count(dashboard._headline) == 1
    assert labels.count(dashboard._detail) == 1


def test_no_label_is_squeezed_below_the_height_its_text_needs(qtbot, qapp):
    """The regression itself: a label given less room than its font requires
    draws outside its rectangle and collides with the next one."""
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.resize(880, 660)
    dashboard.show()
    dashboard.render(a_focusing_view())
    qtbot.wait(50)

    assert squeezed(dashboard) == [], (
        "a label has less height than its text needs and will be drawn "
        "outside its box, over its neighbour"
    )


@pytest.mark.parametrize(("width", "height"), [(480, 400), (520, 520), (760, 640), (1400, 900)])
def test_the_layout_holds_at_every_size(qtbot, qapp, width: int, height: int):
    """Including sizes below MIN_SIZE: the page scrolls, so nothing is squeezed
    even where the window manager would not normally allow it."""
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.resize(width, height)
    dashboard.show()
    dashboard.render(a_focusing_view())
    qtbot.wait(50)

    assert squeezed(dashboard) == [], "the page must scroll rather than squeeze"


@pytest.mark.parametrize("state", list(TimerState))
def test_no_state_squeezes_the_card(qtbot, qapp, state: TimerState):
    """The waiting note appears in some states and must not push others out."""
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.resize(520, 520)
    dashboard.show()
    dashboard.render(
        a_focusing_view(
            state=state,
            waiting_reason="session locked" if state is TimerState.DEFERRED else None,
        )
    )
    qtbot.wait(20)

    assert squeezed(dashboard) == [], f"squeezed in {state}"


def test_repeated_rendering_leaves_no_graphics_effect_attached(qtbot, qapp):
    """A QGraphicsEffect renders its widget from a cached pixmap, and a child
    repainting on its own does not invalidate that cache. One left attached to a
    card whose text changes every second composites stale frames with live ones,
    so the fade must remove itself when it ends."""
    from ocura.ui.motion import FADE_MS, MOTION

    dashboard = DashboardView()
    qtbot.addWidget(dashboard)
    dashboard.show()

    was = MOTION.enabled
    MOTION.enabled = True
    try:
        for index in range(5):
            dashboard.render(a_focusing_view(headline=f"State {index}"))
            qtbot.wait(FADE_MS + 80)
        assert dashboard._status.graphicsEffect() is None
    finally:
        MOTION.enabled = was
