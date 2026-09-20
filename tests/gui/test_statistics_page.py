"""Widget tests for the statistics page.

Only what a headless test cannot say. Every number and every sentence is
decided by `StatisticsPresenter` and tested in `tests/unit/test_statistics.py`;
what is left for a display is that the page puts them on screen, that the empty
state hides the chart rather than drawing an empty one, and that the bars take
their colour from the token set in both themes.

The views here are built by hand rather than read from a database, because the
question is what the page does with a view, not what the query returned.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QPalette

from ocura.application.statistics import DayBar, DeferralLine, StatisticsPageView
from ocura.ui.statistics import Bar, ReasonRow, StatisticsPage
from ocura.ui.theme import DARK, LIGHT, stylesheet

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def a_page_view(**overrides) -> StatisticsPageView:
    base = StatisticsPageView(
        headline="The last seven days",
        subheading="What Ocura recorded while it was running.",
        empty=False,
        empty_message="Nothing to show yet.",
        today_text="1h 20m",
        week_text="9h 45m",
        breaks_text="14",
        average_focus_text="22m",
        chart_visible=True,
        chart_note="No focus block has finished yet.",
        bars=tuple(
            DayBar(
                weekday=name,
                day_of_month=str(14 + index),
                value_text="1h",
                fraction=(index + 1) / 7,
                is_today=index == 6,
            )
            for index, name in enumerate(WEEKDAYS)
        ),
        deferrals_title="When Ocura waited",
        deferrals_note="Ocura held a break back 9 times this week.",
        deferrals=(
            DeferralLine(reason="Fullscreen or presenting", count_text="6", fraction=1.0),
            DeferralLine(reason="Screen locked", count_text="3", fraction=0.5),
        ),
    )
    return replace(base, **overrides)


@pytest.fixture
def page(qtbot):
    widget = StatisticsPage()
    qtbot.addWidget(widget)
    return widget


def rendered(page, view, qtbot):
    """Render, then let the deferred deletes actually happen.

    The chart is rebuilt from scratch on every render, so without pumping the
    loop a test can find both the old bars and the new ones.
    """
    page.render(view)
    qtbot.wait(1)
    return page


def bars_of(page, name: str) -> list[Bar]:
    return [bar for bar in page.findChildren(Bar) if bar.objectName() == name]


# --- it renders what it was given ------------------------------------------


def test_the_page_shows_the_numbers_the_view_carried(page, qtbot):
    rendered(page, a_page_view(), qtbot)

    assert page._headline.text() == "The last seven days"
    assert page._today.text() == "1h 20m"
    assert page._week.text() == "9h 45m"
    assert page._breaks.text() == "14"
    assert page._average.text() == "22m"


def test_there_is_one_column_per_day_and_one_of_them_is_today(page, qtbot):
    rendered(page, a_page_view(), qtbot)

    assert len(bars_of(page, "Bar")) == 6
    assert len(bars_of(page, "TodayBar")) == 1


def test_each_bar_is_given_the_fraction_the_view_asked_for(page, qtbot):
    rendered(page, a_page_view(), qtbot)

    columns = [bar for bar in page.findChildren(Bar) if bar.objectName() != "ReasonBar"]
    fractions = sorted(bar._fraction for bar in columns)
    assert fractions == pytest.approx([(index + 1) / 7 for index in range(7)])


def test_the_weekday_and_the_date_are_both_on_screen(page, qtbot):
    rendered(page, a_page_view(), qtbot)

    text = " ".join(label.text() for label in page._chart.findChildren(type(page._headline)))
    for weekday in WEEKDAYS:
        assert weekday in text
    assert "20" in text


def test_one_row_per_deferral_reason(page, qtbot):
    rendered(page, a_page_view(), qtbot)

    rows = page.findChildren(ReasonRow)
    assert len(rows) == 2
    label_type = type(page._headline)
    text = " ".join(label.text() for row in rows for label in row.findChildren(label_type))
    assert "Fullscreen or presenting" in text
    assert "Screen locked" in text
    assert "6" in text


def test_rendering_twice_does_not_leave_the_first_chart_behind(page, qtbot):
    """The chart is rebuilt each time; the old columns have to actually go."""
    rendered(page, a_page_view(), qtbot)
    rendered(page, a_page_view(), qtbot)

    assert len(page.findChildren(Bar)) == 7 + 2
    assert len(page.findChildren(ReasonRow)) == 2


# --- what the bars actually paint ------------------------------------------


def painted(bar, size: QSize) -> tuple[QImage, int]:
    """Render one bar on its own, and say which colour its paintEvent used.

    A bar that is wired up correctly and draws along the wrong axis passes
    every test that only reads `_fraction` back. This one does not.

    The colour is read off the bar rather than forced onto it. `QWidget.render`
    fills the background first, so "any opaque pixel" is not the bar; and a
    palette set here would lose to whatever stylesheet is on the application,
    which another test module may well have left there.
    """
    bar.ensurePolished()
    bar.resize(size)

    image = QImage(size, QImage.Format.Format_ARGB32)
    image.fill(0)
    bar.render(image)

    colour = bar.palette().color(QPalette.ColorRole.WindowText).rgb()
    background = bar.palette().color(QPalette.ColorRole.Window).rgb()
    assert colour != background, "the bar and what it is drawn on are the same colour"
    return image, colour


def is_bar(shot: tuple[QImage, int], x: int, y: int) -> bool:
    image, colour = shot
    return image.pixelColor(x, y).rgb() == colour


def bar_pixels(shot: tuple[QImage, int], y: int, width: int) -> int:
    return sum(1 for x in range(width) if is_bar(shot, x, y))


def test_a_chart_bar_grows_from_the_bottom(qtbot):
    bar = Bar()
    qtbot.addWidget(bar)
    bar.set_fraction(0.5)
    shot = painted(bar, QSize(40, 100))

    assert is_bar(shot, 20, 90), "nothing at the bottom of the column"
    assert not is_bar(shot, 20, 10), "the column filled its whole height"


def test_a_deferral_bar_grows_from_the_left(qtbot):
    """Horizontal, so the commonest reason is the longest line. Drawn on the
    other axis, every reason looks the same length whatever its count is."""
    bar = Bar(horizontal=True)
    qtbot.addWidget(bar)
    bar.set_fraction(0.5)
    shot = painted(bar, QSize(200, 6))

    assert is_bar(shot, 20, 3), "nothing at the left of the row"
    assert not is_bar(shot, 180, 3), "the row filled its whole width"


def test_two_different_counts_do_not_paint_the_same_length(qtbot):
    """The bug this section exists to catch: proportions that are not."""
    filled = []
    for fraction in (1.0, 0.25):
        bar = Bar(horizontal=True)
        qtbot.addWidget(bar)
        bar.set_fraction(fraction)
        shot = painted(bar, QSize(200, 6))
        filled.append(bar_pixels(shot, 3, 200))

    assert filled[0] > filled[1] * 2


def test_a_day_with_nothing_on_it_paints_nothing(qtbot):
    bar = Bar()
    qtbot.addWidget(bar)
    bar.set_fraction(0.0)
    shot = painted(bar, QSize(40, 100))

    assert not any(is_bar(shot, 20, y) for y in range(0, 100, 5))


def test_a_very_short_day_still_paints_something(qtbot):
    """Without a floor, twenty minutes beside eight hours rounds to nothing and
    reads as a day Ocura was not running, which is a different fact."""
    bar = Bar()
    qtbot.addWidget(bar)
    bar.set_fraction(0.004)
    shot = painted(bar, QSize(40, 100))

    assert any(is_bar(shot, 20, y) for y in range(97, 100))


# --- the empty state -------------------------------------------------------


def test_an_empty_week_says_so_instead_of_drawing_an_empty_chart(page, qtbot):
    """An empty chart with labels and no bars reads as a measurement of zero
    rather than as an absence of measurements."""
    rendered(page, a_page_view(empty=True, empty_message="Nothing to show yet."), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._empty.isVisible()
    assert page._empty.text() == "Nothing to show yet."
    assert not page._chart_card.isVisible()
    assert not page._metrics.isVisible()


def test_the_chart_comes_back_when_there_is_something_to_draw(page, qtbot):
    rendered(page, a_page_view(empty=True), qtbot)
    rendered(page, a_page_view(empty=False), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._chart_card.isVisible()
    assert page._metrics.isVisible()
    assert not page._empty.isVisible()


def test_the_deferral_card_is_on_screen_even_with_nothing_in_it(page, qtbot):
    """It is the section the page exists for, so it explains itself rather than
    disappearing on the days when Ocura never had to wait."""
    rendered(page, a_page_view(deferrals=(), deferrals_note="It has not needed to yet."), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._reasons_note.isVisible()
    assert page._reasons_note.text() == "It has not needed to yet."
    assert page.findChildren(ReasonRow) == []


def test_a_week_with_breaks_but_no_finished_block_has_no_chart(page, qtbot):
    """What a database written by someone who only ever pressed "Take a break
    now" looks like: not empty, and still nothing to chart. Seven bars of zero
    height under a title is an empty chart by another name."""
    rendered(page, a_page_view(empty=False, chart_visible=False), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._metrics.isVisible(), "the breaks that did happen still count"
    assert not page._chart_card.isVisible()
    assert page._chart_note.isVisible()
    assert page._chart_note.text() == "No focus block has finished yet."


def test_the_note_gives_way_to_the_chart_once_there_is_one(page, qtbot):
    rendered(page, a_page_view(chart_visible=False), qtbot)
    rendered(page, a_page_view(chart_visible=True), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._chart_card.isVisible()
    assert not page._chart_note.isVisible()


def test_an_empty_week_shows_neither_the_chart_nor_the_note(page, qtbot):
    """One sentence, not two saying nearly the same thing."""
    rendered(page, a_page_view(empty=True, chart_visible=False), qtbot)
    page.show()
    qtbot.waitExposed(page)

    assert page._empty.isVisible()
    assert not page._chart_note.isVisible()
    assert not page._chart_card.isVisible()


# --- both themes -----------------------------------------------------------


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=["dark", "light"])
def test_the_bars_take_their_colour_from_the_token_set(page, qtbot, qapp, tokens):
    """No colour is written in Python: QSS sets it and paintEvent reads it back.

    Asserted against the token values rather than against a screenshot, which
    is the difference between "the theme is wired up" and "it looked right on
    one machine once".
    """
    was = qapp.styleSheet()
    try:
        qapp.setStyleSheet(stylesheet(tokens))
        rendered(page, a_page_view(), qtbot)

        ordinary, today = bars_of(page, "Bar")[0], bars_of(page, "TodayBar")[0]
        ordinary.ensurePolished()
        today.ensurePolished()

        assert ordinary.palette().color(QPalette.ColorRole.WindowText).name() == tokens.chart_bar
        assert today.palette().color(QPalette.ColorRole.WindowText).name() == tokens.accent
        # Today is marked, not graded: a different colour from the other six,
        # and the same one every day of the week.
        assert tokens.chart_bar != tokens.accent
    finally:
        qapp.setStyleSheet(was)


def test_the_stylesheet_carries_a_rule_for_every_painted_bar():
    """A bar whose object name has no rule falls back to the default text
    colour and quietly stops being themed at all."""
    for tokens in (DARK, LIGHT):
        qss = stylesheet(tokens)
        assert "#Bar {" in qss
        assert "#TodayBar {" in qss
        assert "#ReasonBar {" in qss
        assert tokens.chart_bar in qss
