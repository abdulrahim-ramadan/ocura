"""The seam between the engine and any user interface.

The presenter owns a BreakSession, advances it, and renders everything a view
needs into one immutable SessionView. A widget reads that snapshot and nothing
else: no BreakTimer, no BreakPolicy, no detector, no domain enum arithmetic.

Nothing here imports Qt, and nothing here needs a QApplication to test. A tick
is delivered from outside, but what a tick *means* is decided here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from ocura.application import reasons
from ocura.application.i18n import QT_TRANSLATE_NOOP, clock_text, translate
from ocura.application.journal import NullJournal, SessionJournal
from ocura.application.session import BreakSession, SessionEvent, SessionEventKind
from ocura.application.settings import DEFAULTS, Settings
from ocura.domain.clock import MonotonicClock, WallClock
from ocura.domain.context import ContextSource
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerState

logger = logging.getLogger(__name__)

#: How often a view should pulse the presenter. Advisory: every duration is read
#: from the monotonic clock, so a late or missed pulse costs refresh latency and
#: never corrupts a measurement.
TICK_SECONDS = 1.0

#: This session only, cleared on restart. P4 makes history persistent.
MAX_EVENTS = 100

#: Translation contexts are written as literals at every call site, never as
#: constants. lupdate reads the source rather than running it, so
#: `translate(STATUS, "Focusing")` extracts nothing at all — which is exactly
#: how this was first written, and the catalogue came out with the whole
#: application layer missing. The contexts here are "Status", "Events",
#: "Tips" and "Tray": one per surface, because a translator seeing "Status"
#: knows where the sentence appears, which is the only thing a context is for.

#: Mirrors the domain guard on take_break_now, so the view never offers a
#: control the timer would refuse.
_USER_MAY_ASK = frozenset({TimerState.FOCUSING, TimerState.BREAK_DUE, TimerState.DEFERRED})

#: The line at the foot of the break screen. One per break, rotated so the same
#: sentence is not read twice in a row.
#:
#: Each states the evidence the break rests on and stops there. It is not a
#: second instruction: the screen already says what to do, and a smaller voice
#: repeating it in the corner is nagging. The attribution is part of the text
#: rather than decoration — a claim about someone's eyes that cannot be traced
#: back to anyone is not worth putting on the screen at all.
#: Marked, not translated. A constant translated at import is fixed to the
#: language Python happened to be started in, which is the bug that makes a
#: language switch look like it half-worked.
BREAK_TIPS = (
    QT_TRANSLATE_NOOP(
        "Tips",
        "Every 20 minutes, look at something 20 feet away for 20 seconds "
        "— American Academy of Ophthalmology",
    ),
    QT_TRANSLATE_NOOP(
        "Tips",
        "Close work holds the lens under tension; looking into the distance is what "
        "lets it relax — American Optometric Association",
    ),
    QT_TRANSLATE_NOOP(
        "Tips",
        "Blink rate falls by about half at a screen, which is what leaves eyes dry "
        "— American Optometric Association",
    ),
)


@runtime_checkable
class PollableContext(Protocol):
    """A context source that also needs watching when no break is owed."""

    def poll(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EventLine:
    at: datetime
    text: str

    @property
    def time_text(self) -> str:
        return self.at.astimezone().strftime("%H:%M")


@dataclass(frozen=True, slots=True)
class SessionView:
    """Everything a view renders, already in the words it should say.

    Text lives here rather than in widgets because the language rules — calm,
    informational, never accusatory — are a product decision worth testing, and
    a widget test cannot assert them without a display.
    """

    state: TimerState
    running: bool
    paused: bool
    break_owed: bool

    headline: str
    detail: str

    focus_elapsed: float
    focus_remaining: float
    break_remaining: float
    focus_elapsed_text: str
    countdown_text: str
    progress: float

    #: Set only while a break is owed and something is in the way.
    waiting_reason: str | None

    #: The pre-break warning is showing. One state, one moment to fire on.
    warning_visible: bool
    #: The break overlay should be on screen. Driven by ON_BREAK and nothing
    #: else — never by BREAK_DUE, which is a decision point, not an occurrence.
    overlay_visible: bool

    breaks_taken: int
    rests_credited: int

    #: False once the cap is reached, so a view can drop the control rather than
    #: offer an action that would be refused.
    can_snooze: bool
    snoozes_used: int

    events: tuple[EventLine, ...] = field(default_factory=tuple)

    #: False when no session is running, so a view can disable the control
    #: rather than offer an action that would be refused.
    can_take_break_now: bool = False

    #: The evidence line for the break screen. Chosen here rather than in the
    #: widget: it is language, and the language rules are testable without a
    #: display. Stable for the whole of one break, since it is keyed to the
    #: count of breaks finished and that does not move while one is running.
    tip: str = ""

    #: The one sentence on the pre-break toast. Here rather than assembled in
    #: `OcuraApp` from an f-string, which is what it was and which meant the
    #: one message that has to arrive before a break was the one message no
    #: translator ever saw. Empty whenever the warning is not showing.
    warning_text: str = ""


class BreakPresenter:
    def __init__(
        self,
        schedule: BreakSchedule,
        monotonic: MonotonicClock,
        wall_clock: WallClock,
        context: ContextSource,
        *,
        max_events: int = MAX_EVENTS,
        journal: SessionJournal | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._schedule = schedule
        self._settings = settings or DEFAULTS
        self._session = BreakSession(schedule, monotonic, wall_clock, context)
        self._context = context
        self._max_events = max_events
        self._journal = journal or NullJournal()
        self._events: list[EventLine] = []
        self._waiting_reason: str | None = None
        self._breaks_taken = 0
        self._rests_credited = 0
        self._running = False
        self._paused = False

    # --- commands, each returning the view the caller should render ---------

    def apply(self, settings: Settings) -> SessionView:
        """Adopt new settings, immediately, on whatever the session is doing.

        Already validated: this takes a `Settings`, and one cannot be built
        past `validate()` in a state the domain would refuse. Validation
        belongs at the boundary where the user typed, not here where the only
        honest response to a bad value would be to throw it at a running timer.

        The elapsed focus time survives — see `BreakTimer.reschedule`, which
        owns that decision and explains it. Nothing transitions here; the next
        tick notices what the new numbers have made true.
        """
        self._settings = settings
        self._schedule = settings.schedule()
        self._session.reschedule(self._schedule)
        return self.view()

    @property
    def settings(self) -> Settings:
        return self._settings

    def start(self) -> SessionView:
        self._running = True
        self._paused = False
        self._absorb([self._session.start()])
        return self.view()

    def tick(self) -> SessionView:
        if not self._running:
            return self.view()
        # Detectors observe on every pulse, not only when a break is owed: a lock
        # that began twenty minutes ago has to have been watched all along.
        if isinstance(self._context, PollableContext):
            self._context.poll()
        self._absorb(self._session.tick())
        return self.view()

    def set_paused(self, paused: bool) -> SessionView:
        if not self._running or paused == self._paused:
            return self.view()
        self._absorb([self._session.pause() if paused else self._session.resume()])
        self._paused = paused
        return self.view()

    def toggle_paused(self) -> SessionView:
        return self.set_paused(not self._paused)

    def take_break_now(self) -> SessionView:
        if not self.view().can_take_break_now:
            return self.view()
        self._absorb([self._session.take_break_now()])
        return self.view()

    def snooze(self) -> SessionView:
        if not self.view().can_snooze:
            return self.view()
        self._absorb([self._session.snooze()])
        return self.view()

    def skip_break(self) -> SessionView:
        """End the break now. A legitimate choice, and reported as nothing more."""
        if self._session.state is not TimerState.ON_BREAK:
            return self.view()
        self._absorb([self._session.skip_break()])
        return self.view()

    def stop(self) -> SessionView:
        if self._running:
            self._absorb([self._session.stop()])
        self._running = False
        self._paused = False
        return self.view()

    # --- rendering ---------------------------------------------------------

    def view(self) -> SessionView:
        snapshot = self._session.snapshot()
        state = snapshot.state
        headline, detail = self._describe(state, snapshot.break_remaining, snapshot.focus_remaining)

        if state is TimerState.ON_BREAK:
            span = self._schedule.break_duration
            progress = 1.0 - (snapshot.break_remaining / span) if span else 0.0
            countdown = clock_text(snapshot.break_remaining)
        else:
            span = self._schedule.focus_interval
            progress = min(1.0, snapshot.focus_elapsed / span) if span else 0.0
            countdown = clock_text(snapshot.focus_remaining)

        return SessionView(
            state=state,
            running=self._running,
            paused=self._paused,
            break_owed=snapshot.break_owed,
            headline=headline,
            detail=detail,
            focus_elapsed=snapshot.focus_elapsed,
            focus_remaining=snapshot.focus_remaining,
            break_remaining=snapshot.break_remaining,
            focus_elapsed_text=clock_text(snapshot.focus_elapsed),
            countdown_text=countdown,
            progress=max(0.0, min(1.0, progress)),
            waiting_reason=(
                reasons.phrase(self._waiting_reason)
                if snapshot.break_owed and self._waiting_reason
                else None
            ),
            warning_visible=state is TimerState.PRE_BREAK,
            overlay_visible=state is TimerState.ON_BREAK,
            breaks_taken=self._breaks_taken,
            rests_credited=self._rests_credited,
            can_snooze=self._running and self._session.can_snooze,
            snoozes_used=self._session.snoozes_used,
            events=tuple(self._events),
            can_take_break_now=self._running and state in _USER_MAY_ASK,
            # Empty rather than absent when the user has turned them off: the
            # break screen hides a tip it has not been given, and "no tip" is a
            # thing the view can say without a second flag to say it with.
            tip=(
                translate("Tips", BREAK_TIPS[self._breaks_taken % len(BREAK_TIPS)])
                if self._settings.tips
                else ""
            ),
            # The same context the toast widget's own strings are extracted
            # into, so a translator is handed the whole window at once.
            warning_text=(
                translate("BreakToast", "A break in %1").replace("%1", countdown)
                if state is TimerState.PRE_BREAK
                else ""
            ),
        )

    def tooltip(self) -> str:
        """One line for the tray, which has room for nothing more."""
        view = self.view()
        if view.state is TimerState.ON_BREAK:
            return translate("Tray", "Ocura — on a break, %1 left").replace(
                "%1", view.countdown_text
            )
        if view.waiting_reason:
            return translate("Tray", "Ocura — waiting, %1").replace("%1", view.waiting_reason)
        if view.state is TimerState.PRE_BREAK:
            return translate("Tray", "Ocura — break in %1").replace("%1", view.countdown_text)
        if view.state is TimerState.PAUSED:
            return translate("Tray", "Ocura — reminders paused")
        if view.state is TimerState.IDLE:
            return translate("Tray", "Ocura — not running")
        return translate("Tray", "Ocura — next break in %1").replace("%1", view.countdown_text)

    # --- internals ---------------------------------------------------------

    def _describe(self, state: TimerState, break_left: float, focus_left: float) -> tuple[str, str]:
        """Every sentence takes its numbers through a placeholder.

        A translator needs to move "in 5:00" to the other end of the sentence
        in German and to the other end of the line in Arabic, and cannot do
        either if the number is glued on here.
        """
        match state:
            case TimerState.IDLE:
                return (
                    translate("Status", "Not running"),
                    translate("Status", "Start a session when you are ready."),
                )
            case TimerState.FOCUSING:
                return (
                    translate("Status", "Focusing"),
                    translate("Status", "Next break in %1.").replace("%1", clock_text(focus_left)),
                )
            case TimerState.PRE_BREAK:
                return (
                    translate("Status", "Break soon"),
                    translate("Status", "In %1. Finish your thought.").replace(
                        "%1", clock_text(focus_left)
                    ),
                )
            case TimerState.BREAK_DUE:
                return (
                    translate("Status", "Break ready"),
                    translate("Status", "Whenever suits you."),
                )
            case TimerState.ON_BREAK:
                return (
                    translate("Status", "On a break"),
                    translate("Status", "%1 left. Look somewhere far away.").replace(
                        "%1", clock_text(break_left)
                    ),
                )
            case TimerState.PAUSED:
                return (
                    translate("Status", "Reminders paused"),
                    translate("Status", "Nothing is counting. Resume when you like."),
                )
            case TimerState.DEFERRED:
                headline = translate("Status", "Waiting for a good moment")
                if self._waiting_reason:
                    return headline, translate("Status", "Break owed — %1.").replace(
                        "%1", reasons.phrase(self._waiting_reason)
                    )
                return headline, translate("Status", "Break owed.")

    def _keep(self, event: SessionEvent) -> None:
        """Persistence is best-effort. The break engine is not.

        A full disk, a file an antivirus scanner has locked, or a database
        written by a newer Ocura must cost the user their history and never
        their break. This is the one place that decision is made, which is why
        the `except` is deliberately broad: a journal is a protocol, and an
        implementation failing in a way nobody anticipated must still not be
        able to stop the timer.

        Events are rare — a handful per break — so a failure is logged every
        time rather than sampled. A wall of these is a wall of real problems.
        """
        try:
            self._journal.record(event)
        except Exception:
            logger.warning("could not record %s; history is incomplete", event.kind, exc_info=True)

    def _absorb(self, events: Sequence[SessionEvent]) -> None:
        for event in events:
            # Every event is kept, including the ones the event list does not
            # show. BREAK_DUE is noise on a dashboard and evidence in a log.
            self._keep(event)

            match event.kind:
                case SessionEventKind.BREAK_DEFERRED:
                    self._waiting_reason = event.detail or None
                case SessionEventKind.BREAK_SNOOZED:
                    self._waiting_reason = reasons.POSTPONED
                # A break ended early is still a break that happened, and the
                # count means "breaks that happened". The two kinds diverge in
                # the log, which is where the difference is a fact worth
                # keeping, and nowhere on screen, which is where it would read
                # as a judgement.
                case SessionEventKind.BREAK_COMPLETED | SessionEventKind.BREAK_SKIPPED:
                    self._breaks_taken += 1
                    self._waiting_reason = None
                case SessionEventKind.BREAK_SATISFIED:
                    self._rests_credited += 1
                    self._waiting_reason = None
                case SessionEventKind.STARTED | SessionEventKind.STOPPED:
                    self._waiting_reason = None
                case _:
                    pass

            text = self._phrase(event)
            if text is not None:
                self._events.append(EventLine(at=event.at, text=text))
        del self._events[: max(0, len(self._events) - self._max_events)]

    def _phrase(self, event: SessionEvent) -> str | None:
        # break_due is a decision point, not an outcome, and it is emitted even on
        # ticks where the break is discharged immediately. Showing it would make
        # the list read as though something happened when nothing did.
        match event.kind:
            case SessionEventKind.STARTED:
                return translate("Events", "Session started")
            case SessionEventKind.BREAK_STARTED | SessionEventKind.BREAK_STARTED_BY_USER:
                return translate("Events", "Break started")
            case SessionEventKind.BREAK_COMPLETED | SessionEventKind.BREAK_SKIPPED:
                # Deliberately the same sentence for both. Ocura does not force
                # breaks, and a list that announced a shorter one differently
                # would be commenting on a choice it has no business having an
                # opinion about.
                return translate("Events", "Break finished")
            case SessionEventKind.BREAK_DEFERRED:
                if event.detail:
                    return translate("Events", "Waiting — %1").replace(
                        "%1", reasons.phrase(event.detail)
                    )
                return translate("Events", "Waiting for a good moment")
            case SessionEventKind.BREAK_SNOOZED:
                return translate("Events", "Break postponed")
            case SessionEventKind.BREAK_SATISFIED:
                if event.detail:
                    return translate("Events", "Rest credited — %1").replace(
                        "%1", reasons.phrase(event.detail)
                    )
                return translate("Events", "Rest credited")
            case SessionEventKind.PAUSED:
                return translate("Events", "Reminders paused")
            case SessionEventKind.RESUMED:
                return translate("Events", "Reminders resumed")
            case SessionEventKind.STOPPED:
                return translate("Events", "Session stopped")
            case _:
                return None
