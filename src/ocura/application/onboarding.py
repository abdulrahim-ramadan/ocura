"""First run: three screens, and the only place Ocura explains itself at length.

This is where the explanation lives. Not a splash screen, not a tour with
callouts over a window the user has not looked at yet, and not a manual nobody
opens — three screens, answered once, that leave behind a configured
application and never appear again.

**There is no splash screen, deliberately.** Ocura starts in well under two
seconds and showing a logo for a manufactured pause would be a product built on
respecting people's time spending some of it on looking busy. The effort went
into these three instead.

The state machine is here, with no widget in sight, because what the screens
say and what answering them does are the parts worth testing — and because the
flow has to end in exactly one thing: a validated `Settings` with `introduced`
set, which is the fact that stops it happening again.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from ocura.application.settings import DEFAULTS, RHYTHM_MINUTES, Settings


class Step(IntEnum):
    """Ordered, because "next" and "back" are the whole navigation."""

    WELCOME = 0
    RHYTHM = 1
    AUTOSTART = 2


#: What each screen says. Kept here with the machine that shows them for the
#: same reason the dashboard's language lives in the presenter: it is a product
#: decision, and a widget test cannot assert a sentence without a display.
@dataclass(frozen=True, slots=True)
class Screen:
    title: str
    body: str
    #: The second paragraph, where a screen has one to add.
    note: str = ""


WELCOME = Screen(
    title="Ocura watches the clock so you do not have to",
    body=(
        "Ocura times how long you have been at the screen and offers you a short break "
        "when one is due. It tries hard not to interrupt at a bad moment: while your "
        "screen is locked, while something is running full screen, or while you are away "
        "from the keyboard, it waits and offers the break later."
    ),
    note=(
        "You can always postpone a break or end one early — Ocura never locks you out of "
        "your own machine. It is a wellness and productivity tool, not a medical device. "
        "It does not diagnose anything and makes no medical claims."
    ),
)

#: The sentence on this screen is sourced from docs/EVIDENCE.md, which records
#: who makes the claim and how strong it is. The file is not named on screen:
#: a user has an application, not a checkout, and a path they cannot open is
#: not an attribution. The organisations are named instead, which is the part
#: that can actually be followed up.
RHYTHM = Screen(
    title="Pick a rhythm",
    body=(
        "Every 20 minutes, look at something about 20 feet away for 20 seconds. That is "
        "the 20-20-20 guideline, recommended by the American Academy of Ophthalmology and "
        "the American Optometric Association as an easy rhythm to remember rather than as "
        "a result from a trial."
    ),
    note=(
        "Twenty minutes is the guideline, and the longer options are here because a rhythm "
        "you will actually keep beats one you turn off by lunchtime. You can change this "
        "whenever you like in Settings."
    ),
)

AUTOSTART = Screen(
    title="Should Ocura start with Windows?",
    body=(
        "Ocura only helps on the days it is running, so most people want it to start when "
        "they sign in. It starts minimised to the notification area and does not open a "
        "window."
    ),
    note=(
        "Asked rather than assumed. If you say no, nothing is added to your startup list "
        "and you can turn this on later in Settings. If you say yes, you can still remove "
        "it yourself from Task Manager, under Startup."
    ),
)

SCREENS = {Step.WELCOME: WELCOME, Step.RHYTHM: RHYTHM, Step.AUTOSTART: AUTOSTART}

#: The label on the button that leaves each screen. The last one commits, and
#: says so: "Next" on a final screen is a button that hides what it does.
ADVANCE_LABELS = {
    Step.WELCOME: "Next",
    Step.RHYTHM: "Next",
    Step.AUTOSTART: "Start using Ocura",
}


@dataclass(frozen=True, slots=True)
class OnboardingView:
    """One screen, ready to render. No widget computes any of this."""

    step: Step
    title: str
    body: str
    note: str

    #: 1-based, for "2 of 3". People do not count screens from zero.
    position: int
    total: int

    can_go_back: bool
    is_last: bool
    advance_label: str

    #: Minutes, for the rhythm screen's choices. The selected one is
    #: `chosen_minutes`; a custom value picked in Settings later shows up here
    #: as a rhythm none of the presets match, and none of them is selected.
    rhythm_choices: tuple[int, ...]
    chosen_minutes: int
    autostart: bool


class Onboarding:
    """Walks the three screens and hands back the settings they produced.

    Holds a `Settings` throughout rather than loose answers, so the thing the
    flow ends with is the same type everything else in the application already
    takes — and so a user who quits halfway leaves nothing half-written behind,
    because nothing is written until `finish`.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = (settings or DEFAULTS).replace(introduced=False)
        self._step = Step.WELCOME

    @property
    def step(self) -> Step:
        return self._step

    @property
    def settings(self) -> Settings:
        return self._settings

    # --- navigation --------------------------------------------------------

    def next(self) -> Step:
        """Advance, stopping at the last screen. `finish` is what ends the flow."""
        if self._step is not Step.AUTOSTART:
            self._step = Step(self._step + 1)
        return self._step

    def back(self) -> Step:
        if self._step is not Step.WELCOME:
            self._step = Step(self._step - 1)
        return self._step

    # --- answers -----------------------------------------------------------

    def choose_rhythm(self, minutes: int) -> Settings:
        """Set the focus interval in minutes. Validated like anything else.

        Raises `InvalidSettings` for a number Ocura will not accept, which is
        the same refusal the Settings page gives — first run is not a place
        where the rules are relaxed.
        """
        self._settings = self._settings.replace(focus_interval=float(minutes) * 60).validate()
        return self._settings

    def set_autostart(self, enabled: bool) -> Settings:
        self._settings = self._settings.replace(autostart=enabled)
        return self._settings

    def finish(self) -> Settings:
        """The settings to save, marked as introduced so this never runs again.

        Validated on the way out. Everything that set a value validated it
        already; this is the guarantee that what leaves the flow is honourable
        whatever route was taken through it.
        """
        self._settings = self._settings.replace(introduced=True).validate()
        return self._settings

    # --- rendering ---------------------------------------------------------

    def view(self) -> OnboardingView:
        screen = SCREENS[self._step]
        return OnboardingView(
            step=self._step,
            title=screen.title,
            body=screen.body,
            note=screen.note,
            position=int(self._step) + 1,
            total=len(Step),
            can_go_back=self._step is not Step.WELCOME,
            is_last=self._step is Step.AUTOSTART,
            advance_label=ADVANCE_LABELS[self._step],
            rhythm_choices=RHYTHM_MINUTES,
            chosen_minutes=round(self._settings.focus_interval / 60),
            autostart=self._settings.autostart,
        )


def needs_introduction(settings: Settings, forced: bool = False) -> bool:
    """Whether to run the flow. `forced` is the command-line flag.

    The flag exists because there is no button for this. Re-running the
    introduction is a thing developers and testers need and users do not, and
    a "show me the welcome again" control in Settings would be clutter earning
    its place once per install.
    """
    return forced or not settings.introduced
