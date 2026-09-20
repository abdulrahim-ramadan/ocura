"""The first-run flow, headless: three screens, what they say, and what they leave.

The state machine is the whole of this. A widget test can show that a dialog
appears; only this can show that quitting halfway writes nothing, that the flag
which stops it happening again is set in exactly one place, and that the
sentences on screen say what the product is allowed to claim.
"""

from __future__ import annotations

import pytest

from ocura.application.onboarding import (
    ADVANCE_LABELS,
    SCREENS,
    Onboarding,
    Step,
    needs_introduction,
)
from ocura.application.settings import DEFAULTS, RHYTHM_MINUTES, InvalidSettings


@pytest.fixture
def flow() -> Onboarding:
    return Onboarding()


# --- walking the screens ---------------------------------------------------


def test_it_starts_on_the_first_screen(flow: Onboarding):
    view = flow.view()

    assert view.step is Step.WELCOME
    assert view.position == 1
    assert view.total == 3
    assert view.can_go_back is False
    assert view.is_last is False


def test_next_walks_forward_and_stops_at_the_last_screen(flow: Onboarding):
    assert flow.next() is Step.RHYTHM
    assert flow.next() is Step.AUTOSTART
    assert flow.next() is Step.AUTOSTART, "walked off the end"
    assert flow.view().is_last is True


def test_back_walks_backward_and_stops_at_the_first(flow: Onboarding):
    flow.next()
    flow.next()

    assert flow.back() is Step.RHYTHM
    assert flow.back() is Step.WELCOME
    assert flow.back() is Step.WELCOME, "walked off the front"


def test_going_back_keeps_the_answers_already_given(flow: Onboarding):
    flow.next()
    flow.choose_rhythm(45)
    flow.next()
    flow.set_autostart(True)
    flow.back()

    assert flow.view().chosen_minutes == 45
    assert flow.settings.autostart is True


def test_the_last_button_says_what_it_does(flow: Onboarding):
    """ "Next" on a final screen is a button hiding what it is about to do."""
    assert ADVANCE_LABELS[Step.AUTOSTART] != "Next"
    assert "Ocura" in ADVANCE_LABELS[Step.AUTOSTART]


def test_every_step_has_a_screen_and_a_button_label():
    for step in Step:
        assert step in SCREENS
        assert step in ADVANCE_LABELS
        assert SCREENS[step].title and SCREENS[step].body


# --- the answers -----------------------------------------------------------


@pytest.mark.parametrize("minutes", RHYTHM_MINUTES)
def test_every_offered_rhythm_is_one_ocura_accepts(minutes: int):
    """A preset that fails validation would be an unpressable button."""
    flow = Onboarding()

    settings = flow.choose_rhythm(minutes)
    assert settings.focus_interval == minutes * 60
    assert flow.view().chosen_minutes == minutes


def test_twenty_is_offered_first_because_it_is_the_guideline():
    assert RHYTHM_MINUTES[0] == 20


def test_a_rhythm_ocura_will_not_accept_is_refused_here_too(flow: Onboarding):
    """First run is not a place where the rules are relaxed."""
    with pytest.raises(InvalidSettings):
        flow.choose_rhythm(0)


def test_a_refused_rhythm_leaves_the_flow_as_it_was(flow: Onboarding):
    before = flow.settings

    with pytest.raises(InvalidSettings):
        flow.choose_rhythm(100000)

    assert flow.settings == before


def test_autostart_is_off_until_it_is_asked_for(flow: Onboarding):
    """Asked, not assumed. The default answer on the screen is no."""
    assert flow.view().autostart is False
    assert flow.set_autostart(True).autostart is True
    assert flow.set_autostart(False).autostart is False


# --- what the flow leaves behind -------------------------------------------


def test_finishing_marks_the_settings_introduced(flow: Onboarding):
    settings = flow.finish()

    assert settings.introduced is True
    assert needs_introduction(settings) is False


def test_nothing_is_marked_introduced_before_finishing(flow: Onboarding):
    """A user who quits halfway leaves nothing behind and is asked again."""
    flow.next()
    flow.choose_rhythm(30)
    flow.next()
    flow.set_autostart(True)

    assert flow.settings.introduced is False
    assert needs_introduction(flow.settings) is True


def test_starting_from_settings_that_claim_to_be_introduced_clears_the_claim(flow):
    """Otherwise --first-run would show the screens and then have nothing to
    set, because the flag it exists to re-ask was already true."""
    already = DEFAULTS.replace(introduced=True)

    assert Onboarding(already).settings.introduced is False


def test_the_finished_settings_carry_every_answer():
    flow = Onboarding()
    flow.choose_rhythm(45)
    flow.set_autostart(True)

    settings = flow.finish()

    assert settings.focus_interval == 45 * 60
    assert settings.autostart is True
    assert settings.introduced is True


def test_the_flow_keeps_settings_it_was_given_and_was_not_asked_about():
    """Someone re-running the introduction keeps their theme and their tips."""
    existing = DEFAULTS.replace(theme="light", tips=False, idle_threshold=300.0)

    settings = Onboarding(existing).finish()

    assert settings.theme == "light"
    assert settings.tips is False
    assert settings.idle_threshold == 300.0


def test_finishing_validates_on_the_way_out(monkeypatch, flow: Onboarding):
    """Whatever route was taken through the flow, what leaves it is honourable."""
    monkeypatch.setattr(flow, "_settings", DEFAULTS.replace(break_duration=99999.0))

    with pytest.raises(InvalidSettings):
        flow.finish()


# --- whether to run it at all ----------------------------------------------


def test_a_new_user_is_introduced():
    assert needs_introduction(DEFAULTS) is True


def test_somebody_already_introduced_is_not():
    assert needs_introduction(DEFAULTS.replace(introduced=True)) is False


def test_the_flag_asks_again_for_somebody_who_has_been(flow):
    """--first-run, which exists because there is no button for this."""
    assert needs_introduction(DEFAULTS.replace(introduced=True), forced=True) is True


# --- what the screens are allowed to say -----------------------------------


def test_the_first_screen_says_what_ocura_does_and_makes_no_medical_claim():
    screen = SCREENS[Step.WELCOME]
    words = f"{screen.title} {screen.body} {screen.note}".lower()

    assert "break" in words
    assert "not a medical device" in words
    assert "no medical claims" in words


def test_the_first_screen_says_it_tries_not_to_interrupt_badly():
    words = SCREENS[Step.WELCOME].body.lower()

    assert "locked" in words
    assert "full screen" in words
    assert "away from the keyboard" in words


def test_the_rhythm_screen_explains_where_the_guideline_comes_from():
    words = SCREENS[Step.RHYTHM].body

    assert "20 minutes" in words
    assert "20 seconds" in words
    assert "American Academy of Ophthalmology" in words
    assert "American Optometric Association" in words


def test_the_rhythm_screen_does_not_overstate_the_evidence():
    """docs/EVIDENCE.md records this as widely recommended and sparsely
    trialled. The screen has to say the same thing."""
    words = SCREENS[Step.RHYTHM].body.lower()

    assert "rather than as a result from a trial" in words
    for overclaim in ("proven", "clinically", "studies show", "scientifically"):
        assert overclaim not in words


def test_no_screen_points_the_user_at_a_file_they_do_not_have():
    for screen in SCREENS.values():
        words = f"{screen.title} {screen.body} {screen.note}"
        assert "docs/" not in words
        assert ".md" not in words


def test_the_autostart_screen_says_what_happens_either_way():
    screen = SCREENS[Step.AUTOSTART]
    words = f"{screen.body} {screen.note}".lower()

    assert "if you say no" in words
    assert "if you say yes" in words
    assert "task manager" in words


def test_no_screen_is_accusatory():
    """The same rule as every other surface, off the same shared list."""
    from .conftest import ACCUSATORY_WORDS

    words = " ".join(
        f"{screen.title} {screen.body} {screen.note}" for screen in SCREENS.values()
    ).lower()

    assert not [bad for bad in ACCUSATORY_WORDS if bad in words]
