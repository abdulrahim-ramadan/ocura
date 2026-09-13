"""DEVELOPMENT HARNESS - not part of the ocura package, not shipped, not tested.

A terminal window onto the P0 engine so you can watch the state machine run and
poke it by hand. P2 replaces this entirely with the real tray and window; nothing
here is a preview of the UI, and no logic lives in this file that should not
already be in the domain.

    python scripts/demo.py [--ticks N] [--auto] [--real]

Keys, read once per tick without blocking:

    b  take the break now      p  pause
    d  defer it                r  resume
    s  end the break early     q  quit

--real swaps your keyboard for the actual P1 Windows detectors, so you can lock
the machine or go fullscreen and watch the engine react.

Windows only: it uses msvcrt for non-blocking keyboard reads. Standard library
only, no PySide6.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocura.application.session import BreakSession, SessionEvent
from ocura.domain.context import (
    ContextAssessment,
    Deferral,
    Interruptible,
)
from ocura.domain.errors import TransitionError
from ocura.domain.schedule import BreakSchedule
from ocura.domain.timer import TimerSnapshot, TimerState
from ocura.infrastructure.clock import SystemMonotonicClock, SystemWallClock
from ocura.infrastructure.windows.context import build_windows_context

SCHEDULE = BreakSchedule(focus_interval=10.0, break_duration=5.0, defer_interval=8.0)
TICK_SECONDS = 1.0


class KeyboardContext:
    """A context source driven by your keyboard, standing in for P1's detectors.

    With nothing queued it defers by one second, which parks an owed break in a
    one-second retry loop until you answer. That is the engine's real behaviour,
    not a harness trick: BREAK_DUE always resolves to something on the same tick.

    Under --auto there is nobody to wait for, so it accepts every break instead
    and the whole cycle runs unattended.
    """

    def __init__(self, interactive: bool) -> None:
        self.pending: ContextAssessment | None = None
        self._interactive = interactive

    def poll(self) -> None:
        """Nothing to observe: the keyboard is read by the loop, not by polling."""

    def assess(self, snapshot: TimerSnapshot) -> ContextAssessment:
        if self.pending is not None:
            pending, self.pending = self.pending, None
            return pending
        if self._interactive:
            return Deferral(reason="waiting for a key", retry_after=TICK_SECONDS)
        return Interruptible()


def read_key() -> str | None:
    """Last key pressed since the previous tick, or None. Never blocks."""
    if not sys.stdin.isatty():
        return None
    import msvcrt

    key = None
    while msvcrt.kbhit():
        key = msvcrt.getwch().lower()
    return key


def describe(snapshot: TimerSnapshot) -> str:
    focus = f"focus {snapshot.focus_elapsed:5.1f}s"
    match snapshot.state:
        case TimerState.ON_BREAK:
            taken = SCHEDULE.break_duration - snapshot.break_remaining
            return f"break {taken:5.1f}s  remaining {snapshot.break_remaining:.1f}s"
        case TimerState.DEFERRED:
            return f"{focus}  owed, retry in {snapshot.deferral_remaining:.1f}s"
        case TimerState.BREAK_DUE:
            return f"{focus}  break owed"
        case TimerState.FOCUSING:
            return f"{focus}  next break in {snapshot.focus_remaining:.1f}s"
        case _:
            return focus


def render(started: float, snapshot: TimerSnapshot, events: list[SessionEvent], note: str) -> str:
    elapsed = time.monotonic() - started
    stamp = f"[{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}]"
    line = f"{stamp} {snapshot.state.upper():<10} {describe(snapshot)}"
    if events:
        line += "   events: " + ", ".join(
            f"{event.kind.value} ({event.detail})" if event.detail else event.kind.value
            for event in events
        )
    if note:
        line += f"   <- {note}"
    return line


def apply_key(key: str, session: BreakSession, context: KeyboardContext) -> str:
    match key:
        case "b":
            context.pending = Interruptible()
            return "taking the break"
        case "d":
            context.pending = Deferral(reason="you deferred", retry_after=SCHEDULE.defer_interval)
            return "deferred"
        case "s":
            session.skip_break()
            return "break ended early"
        case "p":
            session.pause()
            return "paused"
        case "r":
            session.resume()
            return "resumed"
        case _:
            return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=0, help="stop after N ticks (0 = until q)")
    parser.add_argument("--auto", action="store_true", help="take every break, ignore the keyboard")
    parser.add_argument("--real", action="store_true", help="use the real Windows detectors")
    args = parser.parse_args()

    monotonic = SystemMonotonicClock()
    context = (
        build_windows_context(monotonic)
        if args.real
        else KeyboardContext(interactive=not args.auto)
    )
    session = BreakSession(SCHEDULE, monotonic, SystemWallClock(), context)

    print(__doc__.split("Keys,")[0].strip())
    print(
        f"\nfocus {SCHEDULE.focus_interval:.0f}s | break {SCHEDULE.break_duration:.0f}s | "
        f"defer {SCHEDULE.defer_interval:.0f}s     keys: b d s p r q\n"
    )

    started = time.monotonic()
    session.start()
    ticks = 0

    while args.ticks == 0 or ticks < args.ticks:
        time.sleep(TICK_SECONDS)
        ticks += 1

        note = ""
        key = read_key()
        if key == "q":
            break
        if key:
            try:
                note = apply_key(key, session, context)
            except TransitionError as exc:
                note = f"ignored: {exc}"

        # Detectors observe every tick, not only when a break is owed: a lock that
        # started twenty minutes ago has to have been watched all along.
        context.poll()
        events = session.tick()
        print(render(started, session.snapshot(), events, note))

    session.stop()
    print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
