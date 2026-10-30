"""Arabic is not German with different words: the whole interface turns round.

What Qt does by itself is most of it — layouts, alignment, the direction text
flows in — and what it does not do is the list this module exists to hold:
a stylesheet is not mirrored, a paint event is not mirrored, and a countdown
must not be localised at all.

The composition of the break screen is tested here too, because "the text
block mirrors, the focus shape stays centred" is a claim about geometry that a
screenshot can only suggest and a reader of the source cannot check at all.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QWidget

from ocura.application.i18n import clock_text
from ocura.application.settings import is_rtl
from ocura.ui.break_screen import BreakScreen
from ocura.ui.language import Language
from ocura.ui.statistics import Bar

ARABIC = "ar"
ENGLISH = "en"


@pytest.fixture
def language(qapp):
    """Switch the application's language, and put it back afterwards.

    Afterwards matters: the translator and the layout direction are properties
    of the QApplication, which every other test in this run shares.
    """
    handle = Language(qapp)
    was = qapp.layoutDirection()
    yield handle
    # Off, not back to English: applying English installs a catalogue the
    # test did not start with. The translator global is put back by the
    # autouse `own_translator`.
    handle._remove_existing()
    qapp.setLayoutDirection(was)


# --- the direction itself --------------------------------------------------


def test_arabic_turns_the_application_round(language, qapp):
    language.apply(ARABIC)
    assert qapp.layoutDirection() is Qt.LayoutDirection.RightToLeft

    language.apply(ENGLISH)
    assert qapp.layoutDirection() is Qt.LayoutDirection.LeftToRight


def test_the_direction_is_a_fact_about_the_language_not_about_the_catalogue():
    """So a language with no catalogue yet still lays out correctly, and so
    this can be asserted without a display."""
    assert is_rtl("ar")
    assert not is_rtl("de")
    assert not is_rtl("en")


# --- what Qt does not mirror ----------------------------------------------


#: What the bar is told to paint, through its own stylesheet, which outranks
#: whatever stylesheet another test left on the application.
BAR_COLOUR = 0xFFC03A8A

#: What the image holds before the bar paints. Neither the bar nor anything
#: in the theme paints it, so a pixel still this colour was not painted.
UNPAINTED = 0xFF00FF00


def painted(bar: Bar, size: QSize) -> QImage:
    """One bar, rendered on its own over the sentinel, in a colour set here.

    The colour is set, not read back. Read back, it was whatever the palette
    happened to hold — the system's translucent text colour in light mode,
    which no painted pixel ever equals — and the test agreed or disagreed with
    the environment rather than with the bar.
    """
    bar.setStyleSheet(f"color: #{BAR_COLOUR & 0xFFFFFF:06x};")
    bar.ensurePolished()
    bar.resize(size)
    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(UNPAINTED)
    # Children only: the default flags fill the window background first, and
    # the sentinel would be painted over before the bar ever drew.
    bar.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return image


def is_bar(image: QImage, x: int, y: int) -> bool:
    return image.pixelColor(x, y).rgba() == BAR_COLOUR


def test_a_deferral_bar_grows_from_the_edge_the_row_is_read_from(qtbot):
    """A proportion that grows away from its own label cannot be compared to
    the one under it, which is the only thing this row is for."""
    bar = Bar(horizontal=True)
    qtbot.addWidget(bar)
    bar.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    bar.set_fraction(0.5)
    shot = painted(bar, QSize(200, 6))

    assert is_bar(shot, 180, 3), "nothing at the right of the row"
    assert not is_bar(shot, 20, 3), "the row filled its whole width"


# --- the break overlay -----------------------------------------------------


def test_the_focus_shape_stays_centred_and_the_controls_mirror(qtbot, qapp):
    """The one composition on which the two rules pull in opposite directions.

    The shape is a circle on the screen's axis and has no reading direction,
    so mirroring it would mean moving it off centre for no reason. The
    controls are a row that is read, so they do turn round: in English the
    postponement sits left of the skip, and in Arabic it sits right of it.
    """
    screen = BreakScreen()
    qtbot.addWidget(screen)
    screen.resize(1200, 800)
    screen.show()
    qtbot.waitExposed(screen)

    def geometry():
        qapp.processEvents()
        return (
            screen.shape.geometry().center().x(),
            screen._snooze.geometry().center().x(),
            screen._skip.geometry().center().x(),
        )

    screen.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    shape, snooze, skip = geometry()
    assert abs(shape - screen.width() // 2) <= 1
    assert snooze < skip

    screen.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    mirrored_shape, snooze, skip = geometry()
    assert mirrored_shape == shape, "the focus shape moved when the text mirrored"
    assert snooze > skip


# --- digits ----------------------------------------------------------------


def test_the_countdown_stays_in_western_digits_in_arabic(language):
    """Read at a glance from the corner of the eye. Arabic-Indic digits are
    right for Arabic prose and wrong for a timer, and QLocale would give them,
    which is why this formats with Python."""
    language.apply(ARABIC)

    assert clock_text(125) == "2:05"
    assert clock_text(3725) == "1:02:05"
