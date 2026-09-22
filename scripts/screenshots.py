"""The read-me screenshots, taken from the running application.

    .venv\\Scripts\\python.exe scripts\\screenshots.py

Writes `docs/screenshots/*.png`. Every image in the read-me comes from here, so
a screenshot that no longer matches the product is one command away from being
right again — which is the only reason screenshots in a read-me are worth
having. A retouched image, or one taken by hand and never taken again, starts
lying the first time a widget moves and nothing says so.

**It runs against a throwaway profile**, not the one on this machine.
`%LOCALAPPDATA%` is pointed at a temporary folder before anything reads it, so
the images can never contain somebody's real history, and the statistics page
has something on it either way.

**The history behind the statistics image is generated, and says so in the
read-me.** It is written through the real `EventStore`, at real past moments,
and read back by the real query — an invented *screenshot* of the statistics
page would be a drawing of a product feature, which is the thing this project
does not do; a real page over a stated demonstration profile is not.

**Each image is taken after the fade that precedes it has finished.** Grabbing
a widget mid-animation produces a washed-out page that looks like a rendering
bug, and the first set taken here were exactly that.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"

#: Pointed somewhere disposable before `default_database_path` is ever called,
#: which is why this happens here and not in main(): the storage layer reads
#: the variable at import-adjacent time and the UI package pulls it in.
PROFILE = Path(tempfile.mkdtemp(prefix="ocura-screenshots-"))
os.environ["LOCALAPPDATA"] = str(PROFILE)

sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ocura.application.session import SessionEvent, SessionEventKind  # noqa: E402
from ocura.application.settings import Settings  # noqa: E402
from ocura.domain.timer import TimerState  # noqa: E402
from ocura.infrastructure.storage import (  # noqa: E402
    SettingsStore,
    close_database,
    default_database_path,
    open_event_store,
)

#: The window is sized here rather than left wherever it opened, so the images
#: are the same shape every time they are regenerated and a diff of the folder
#: shows a change in the product rather than a change in the window.
WINDOW = (1040, 740)

#: Longer than the page fade, in milliseconds. See the module docstring.
SETTLE = 700

FOCUS = 20 * 60.0

#: A fortnight of plausible days: focus blocks, breaks taken, breaks ended
#: early, and the deferrals with the detector's own words for why. Two quiet
#: days in each week, because a week of uniform bars is not what anyone's week
#: looks like and a screenshot that claims otherwise is a worse advertisement
#: than an honest one.
DAYS: tuple[tuple[int, int, int, tuple[tuple[str, int], ...]], ...] = (
    (9, 8, 1, (("fullscreen or presenting", 1),)),
    (11, 10, 1, (("idle for 240s", 1),)),
    (6, 5, 1, ()),
    (13, 11, 2, (("fullscreen or presenting", 2), ("session locked", 1))),
    (10, 9, 1, (("idle for 240s", 1),)),
    (4, 4, 0, ()),
    (2, 2, 0, ()),
    (12, 10, 2, (("fullscreen or presenting", 1),)),
    (8, 7, 1, (("session locked", 1),)),
    (14, 12, 2, (("idle for 305s", 2), ("fullscreen or presenting", 1))),
    (7, 6, 1, ()),
    (10, 9, 1, (("session locked", 1),)),
    (5, 5, 0, ()),
    (6, 5, 0, (("idle for 240s", 1),)),
)


def seed() -> None:
    """Write the demonstration history through the real store."""
    path = default_database_path()
    connection, store = open_event_store(path)

    def record(
        kind: SessionEventKind, at: datetime, detail: str = "", duration: float | None = None
    ) -> None:
        store.record(
            SessionEvent(
                kind=kind, at=at, state=TimerState.FOCUSING, detail=detail, duration=duration
            )
        )

    # Nine in the morning, local, because the day bucketing is a local-day
    # question and a UTC midnight would land these on the wrong bars.
    start_of_day = datetime.now().astimezone().replace(hour=9, minute=12, second=0, microsecond=0)

    for back, (blocks, taken, early, waits) in enumerate(reversed(DAYS)):
        day = start_of_day - timedelta(days=len(DAYS) - 1 - back)
        moment = day
        for index in range(blocks):
            moment = day + timedelta(minutes=index * 25)
            # The duration on BREAK_DUE is what screen time is counted from.
            record(SessionEventKind.BREAK_DUE, moment, duration=FOCUS)
            if index < taken:
                record(SessionEventKind.BREAK_COMPLETED, moment, duration=20.0)
            elif index < taken + early:
                record(SessionEventKind.BREAK_SKIPPED, moment, duration=7.0)
        for reason, count in waits:
            for index in range(count):
                record(
                    SessionEventKind.BREAK_DEFERRED,
                    moment + timedelta(minutes=index + 1),
                    detail=reason,
                    duration=300.0,
                )

    # English, and past the first run. The read-me is in English and its
    # screenshots have to be, on a machine whose Windows is not — the language
    # setting defaults to following Windows, which is right for a user and
    # wrong for a document.
    SettingsStore(connection).save(Settings(language="en", introduced=True))
    close_database(connection)
    print(f"seeded {path}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seed()

    from ocura.ui.app import OcuraApp
    from ocura.ui.main_window import MainWindow

    app = QApplication([])
    ocura = OcuraApp(app)
    ocura.start(first_run=False)

    window = ocura.window
    window.resize(*WINDOW)
    window.show()

    def save(widget, name: str) -> None:
        shot = widget.grab()
        shot.save(str(OUT / name))
        print(f"{name}: {shot.width()}x{shot.height()}")

    def show(index: int):
        # Clicked rather than switched, so the sidebar in the image shows the
        # page that is actually on screen as the selected one.
        return lambda: window._nav.button(index).click()

    steps = [
        lambda: save(window, "dashboard.png"),
        show(MainWindow.STATISTICS),
        lambda: save(window, "statistics.png"),
        show(MainWindow.SETTINGS),
        lambda: save(window, "settings.png"),
        show(0),
        ocura.driver.take_break_now,
        # One screen's overlay. They are identical but for their geometry, and
        # a read-me does not need the same image once per monitor.
        lambda: save(next(iter(ocura.overlay.windows.values())), "break.png"),
        ocura.driver.skip_break,
    ]

    def advance() -> None:
        if not steps:
            print(f"\n    {OUT}\n")
            # Hard exit rather than app.quit(): the overlay and the tray keep
            # their own references, and this script has nothing left to do.
            sys.stdout.flush()
            os._exit(0)
        steps.pop(0)()
        QTimer.singleShot(SETTLE, advance)

    # The first wait is longer: the window has to be mapped and themed before
    # anything is worth photographing.
    QTimer.singleShot(2000, advance)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
