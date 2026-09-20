"""Widget tests for the Settings page and the first-run dialog.

`isVisibleTo(parent)` rather than `isVisible()` throughout: a child of a window
that has never been shown is not visible whatever its own flag says, and these
pages are built and driven without being put on screen. `isVisibleTo` asks the
question actually being asked — would this be shown, if the window were.

Only what needs a display. What a setting is allowed to be, what a refusal
says, what each first-run screen says and what answering it does are all
settled headlessly in `tests/unit/`. What is left here is the behaviour that
only exists once there are controls: that a refused value stays in its box and
is not applied, that the refusal is visible, and that the three screens advance.
"""

from __future__ import annotations

import pytest

from ocura.application.autostart import AutostartUnavailable
from ocura.application.onboarding import Onboarding, Step
from ocura.application.settings import DEFAULTS
from ocura.ui.onboarding import OnboardingDialog
from ocura.ui.settings_page import SPIN_CEILING, SettingsPage


class FakeAutostart:
    """A startup list that can be told to refuse."""

    available = True

    def __init__(self, enabled: bool = False, refuse: bool = False) -> None:
        self.enabled = enabled
        self.refuse = refuse

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        if self.refuse:
            raise AutostartUnavailable("Windows would not let Ocura change its start-up entry.")
        self.enabled = enabled


class UnavailableAutostart:
    available = False

    def is_enabled(self) -> bool:
        return False

    def set_enabled(self, enabled: bool) -> None:
        raise AutostartUnavailable("nope")


@pytest.fixture
def page(qtbot):
    widget = SettingsPage(DEFAULTS, FakeAutostart())
    qtbot.addWidget(widget)
    return widget


# --- the settings page -----------------------------------------------------


def test_the_controls_show_the_settings_they_were_given(qtbot):
    settings = DEFAULTS.replace(
        focus_interval=2700.0, break_duration=30.0, pre_break_warning=90.0, theme="light"
    )
    page = SettingsPage(settings, FakeAutostart())
    qtbot.addWidget(page)

    assert page._interval.value() == 45, "minutes at the edge, seconds in the model"
    assert page._duration.value() == 30
    assert page._warning.value() == 90
    assert page._theme.currentData() == "light"


def test_a_valid_change_is_emitted_once(page, qtbot):
    with qtbot.waitSignal(page.settingsChanged, timeout=500) as caught:
        page._interval.setValue(30)

    assert caught.args[0].focus_interval == 30 * 60


def test_a_refused_value_is_not_emitted_and_not_reverted(page):
    """Both halves matter. Nothing downstream may see it, and the box must keep
    what was typed so the user is not retyping to find the next problem."""
    seen = []
    page.settingsChanged.connect(seen.append)

    page._duration.setValue(1500)  # a 25-minute break in a 20-minute interval

    assert seen == []
    assert page._duration.value() == 1500, "the control snapped back"


def test_the_refusal_is_visible_and_says_what_is_wrong(page):
    page._duration.setValue(1500)

    problem = page._rows["break_duration"]._problem
    assert problem.isVisibleTo(page)
    assert "does not fit" in problem.text()


def test_the_refusal_sits_beside_the_control_that_caused_it(page):
    page._warning.setValue(99999)

    assert page._rows["pre_break_warning"]._problem.isVisibleTo(page)
    assert not page._rows["break_duration"]._problem.isVisibleTo(page)


def test_a_later_valid_change_clears_the_refusal(page):
    page._duration.setValue(1500)
    assert page._rows["break_duration"]._problem.isVisibleTo(page)

    page._duration.setValue(25)

    assert not page._rows["break_duration"]._problem.isVisibleTo(page)


def test_the_spin_boxes_do_not_clamp_before_ocura_can_refuse(page):
    """If Qt clamps first the user gets a number they never typed and no
    reason for it, which is the one thing this page exists not to do."""
    for box in (page._interval, page._duration, page._warning, page._idle):
        assert box.maximum() >= SPIN_CEILING
        box.setValue(SPIN_CEILING)
        assert box.value() == SPIN_CEILING


def test_loading_settings_is_not_treated_as_an_edit(page):
    seen = []
    page.settingsChanged.connect(seen.append)

    page.load(DEFAULTS.replace(focus_interval=1800.0))

    assert seen == [], "showing a value emitted it back out"


# --- autostart -------------------------------------------------------------


def test_the_checkbox_shows_the_registry_not_the_stored_setting(qtbot):
    """They can disagree, and what runs at sign-in is what the registry says."""
    page = SettingsPage(DEFAULTS.replace(autostart=False), FakeAutostart(enabled=True))
    qtbot.addWidget(page)

    assert page._autostart_box.isChecked() is True


def test_turning_it_on_asks_windows(qtbot):
    autostart = FakeAutostart()
    page = SettingsPage(DEFAULTS, autostart)
    qtbot.addWidget(page)

    page._autostart_box.setChecked(True)

    assert autostart.enabled is True


def test_a_refused_write_puts_the_checkbox_back_and_says_why(qtbot):
    """Otherwise the page is showing a promise the machine has not made."""
    page = SettingsPage(DEFAULTS, FakeAutostart(refuse=True))
    qtbot.addWidget(page)
    seen = []
    page.settingsChanged.connect(seen.append)

    page._autostart_box.setChecked(True)

    assert page._autostart_box.isChecked() is False
    assert page._rows["autostart"]._problem.isVisibleTo(page)
    assert seen == []


def test_a_machine_with_no_startup_list_disables_the_control_and_explains(qtbot):
    page = SettingsPage(DEFAULTS, UnavailableAutostart())
    qtbot.addWidget(page)

    assert page._autostart_box.isEnabled() is False
    assert page._rows["autostart"]._problem.isVisibleTo(page)


# --- the first-run dialog --------------------------------------------------


@pytest.fixture
def dialog(qtbot):
    widget = OnboardingDialog(Onboarding(DEFAULTS))
    qtbot.addWidget(widget)
    return widget


def test_the_dialog_opens_on_the_first_screen(dialog):
    from ocura.application.onboarding import SCREENS

    assert dialog._title.text() == SCREENS[Step.WELCOME].title
    assert dialog._position.text() == "1 of 3"
    assert not dialog._back.isVisibleTo(dialog)


def test_advancing_walks_the_three_screens(dialog, qtbot):
    dialog._advance.click()
    assert dialog._position.text() == "2 of 3"

    dialog._advance.click()
    assert dialog._position.text() == "3 of 3"
    assert dialog._advance.text() == "Start using Ocura"


def test_the_rhythm_screen_offers_the_presets_and_a_way_out(dialog):
    dialog._advance.click()

    labels = [button.text() for button in dialog._rhythms.buttons()]
    assert "Every 20 minutes" in labels
    assert "Every 45 minutes" in labels
    assert any("Settings" in label for label in labels), "no escape from the presets"


def test_choosing_a_rhythm_reaches_the_finished_settings(dialog, qtbot):
    dialog._advance.click()
    for button in dialog._rhythms.buttons():
        if button.text() == "Every 45 minutes":
            button.setChecked(True)
    dialog._advance.click()

    with qtbot.waitSignal(dialog.completed, timeout=500) as caught:
        dialog._advance.click()

    assert caught.args[0].focus_interval == 45 * 60
    assert caught.args[0].introduced is True


def test_the_autostart_answer_reaches_the_finished_settings(dialog, qtbot):
    dialog._advance.click()
    dialog._advance.click()
    dialog._autostart_yes.setChecked(True)

    with qtbot.waitSignal(dialog.completed, timeout=500) as caught:
        dialog._advance.click()

    assert caught.args[0].autostart is True


def test_going_back_shows_the_previous_screen(dialog):
    dialog._advance.click()
    dialog._advance.click()
    assert dialog._back.isVisibleTo(dialog)

    dialog._back.click()
    assert dialog._position.text() == "2 of 3"


def test_escape_does_not_dismiss_it(dialog, qtbot):
    """Three questions, and the application behind it is not configured until
    they are answered."""
    from PySide6.QtCore import Qt

    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.isVisible()


def test_the_screen_before_last_does_not_finish(dialog):
    seen = []
    dialog.completed.connect(seen.append)

    dialog._advance.click()
    dialog._advance.click()

    assert seen == [], "the flow finished before the last screen"


def test_changing_screens_does_not_leave_the_old_choices_behind(dialog):
    from PySide6.QtWidgets import QRadioButton

    dialog._advance.click()
    rhythms = len(dialog.findChildren(QRadioButton))
    dialog._back.click()
    dialog._advance.click()

    assert len(dialog.findChildren(QRadioButton)) == rhythms
