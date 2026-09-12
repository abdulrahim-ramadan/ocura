# Ocura

**Better screen habits.**

Ocura is a calm, privacy-first eye-care and screen-habit companion for Windows.
It watches how long you have been at the screen and offers a break when one is
due — and, crucially, tries to offer it at a moment that is actually good for
you.

Ocura is a wellness and productivity tool. It is not a medical device, it does
not diagnose anything, and it makes no medical claims.

## Philosophy

**It must earn the right to interrupt.** An interruption at the wrong moment is
worse than no interruption at all. Every feature in Ocura is judged by whether
it improves the quality of the interruption decision, not by how many
notifications it can produce.

**Calm, never guilt-driven.** No streaks to break, no failure states, no
red numbers, no "you missed 4 breaks today". Metrics exist to inform you, never
to accuse you. A break you skipped is not a moral event.

**No forced breaks.** You can defer a break, and you can end one early. Ocura
never locks you out of your own machine.

**Windows-first.** Ocura is built for Windows rather than ported to it. The
context signals that make the interruption decision good — session lock, full
screen, display state — are platform-specific by nature.

**Privacy-first and local-first.** No accounts, no sign-in, no cloud sync, no
telemetry, no analytics. Nothing leaves the machine. When persistence arrives in
P4, the schema will carry no user identifier of any kind.

## Current status: P0, domain core only

P0 is the framework-free core: the break state machine, the clock abstractions
it runs on, and the vocabulary for context-aware decisions. There is no user
interface yet. Running `pytest` is currently the only way to exercise Ocura.

| Area | Status |
| --- | --- |
| Break state machine (focus, break, pause, defer, satisfaction) | Implemented |
| Monotonic elapsed time, separate calendar clock | Implemented |
| Schedule validation | Implemented |
| Deferral and satisfaction as distinct outcomes | Implemented |
| Context abstraction for future detectors | Implemented (vocabulary only) |
| Deterministic test suite | Implemented |
| Windows context detection (idle, session lock, full screen) | Planned, P1 |
| Tray icon, main window | Planned, P2 |
| Break overlay, countdown, notifications, snooze | Planned, P3 |
| Persistence, settings, daily metrics | Planned, P4 |
| Onboarding | Planned, P5 |
| Installer and packaging | Planned, P7 |

Nothing in the "Planned" rows exists yet, in any form. See
[docs/ROADMAP.md](docs/ROADMAP.md).

## Development

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run the tests:

```powershell
pytest
```

Run the linter and the formatter check:

```powershell
ruff check .
ruff format --check .
```

The suite is fully deterministic and never sleeps: tests drive a fake clock and
advance it instantly, so the whole run takes well under a second.

## Architecture

Domain -> Application -> Infrastructure -> future UI, with dependencies pointing
inwards only. The domain layer imports no Qt, no `ctypes`, and no Windows API,
which is what will let the UI and the Windows detectors be added later without
touching the break logic. See [docs/architecture.md](docs/architecture.md).

## Licensing

Ocura is **source-available, not open source**.

- Free for personal use.
- The source is published for transparency and evaluation. You can read it and
  audit what the application does.
- You may not use, copy, modify, distribute, sublicense, or sell this software
  or any derivative work without a written commercial license.

See [LICENSE](LICENSE) for the exact terms.

Commercial enquiries: **Abdalrhim19991@gmail.com**

Copyright (c) 2026 Abdulrahim Ramadan. All rights reserved.
