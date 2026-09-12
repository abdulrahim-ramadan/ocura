# Architecture

## Layers

```
Domain  <-  Application  <-  Infrastructure  <-  UI (P2+)
```

Dependencies point inwards. Each layer knows the ones inside it and nothing
about the ones outside it.

**Domain** (`src/ocura/domain/`) — the break state machine, the schedule and its
validation, and the vocabulary for context decisions. Pure Python and the
standard library. It imports no Qt, no `ctypes`, no `winreg`, and it never reads
a clock by itself.

**Application** (`src/ocura/application/`) — wiring. `BreakSession` owns a timer,
asks a context source when a break is owed, hands the answer to the policy, and
emits `SessionEvent`s. It knows about clocks and context sources as protocols,
never as concrete Windows things.

**Infrastructure** (`src/ocura/infrastructure/`) — the adapters. Today: the real
monotonic and wall clocks, plus a placeholder context source that always says
"go ahead". In P1 this is where the Windows detectors land. This is the only
layer permitted to import platform APIs.

**UI** (P2) — tray, window, overlay. It will consume `SessionEvent`s and call
session commands. It will not contain break logic, and no domain module will
ever import it.

`pyproject.toml` enforces part of this mechanically: `ruff`'s banned-api rule
fails the build if `PySide6` or `ctypes` is imported anywhere it should not be.

## Why the domain stays framework-free

The break logic is the part of Ocura most likely to be wrong and most expensive
to get wrong, so it has to be the part that is trivial to test. A domain with no
Qt event loop, no window handles and no Windows API can be exercised in
microseconds, from any process, with no display attached. The suite runs in
about a quarter of a second.

It is also insurance against churn in the layers that churn most. A tray icon
redesign, a switch of UI toolkit, or a change in how idle time is detected must
not be able to alter when a break becomes due.

## Why elapsed time and calendar time are separate abstractions

The domain depends on two protocols, `MonotonicClock` and `WallClock`, and they
are deliberately not interchangeable.

Measuring how long someone has been focusing is a *duration* question. The only
correct source is a monotonic counter, which never jumps and never runs
backwards. If the timer read the calendar instead, a clock correction from 09:30
to 10:15 — a daylight-saving change, an NTP step, a user fixing their clock —
would instantly convince it that 45 minutes of focus had happened. Waking a
laptop from sleep would do the same. `test_wall_clock_jump_does_not_corrupt_elapsed`
pins this behaviour.

Knowing that it is 22:30 on a Tuesday is a *calendar* question that a monotonic
counter cannot answer at all. P0 needs it in exactly one place: stamping session
events, which is what P4 will persist and what the UI will show as "your last
break was at 14:20". Future quiet-hours rules will need it too.

Both come with a production implementation in the infrastructure layer and a
deterministic fake in the tests. The fake monotonic clock only moves when a test
tells it to, so nothing in the suite ever sleeps.

## Why DEFERRAL and SATISFACTION are distinct outcomes

When a break is due, the environment can report two very different things, and
collapsing them into one boolean would be a design error rather than a
simplification.

**Deferral** — the break is due, but this is a bad moment (full screen, a
presentation, a call). The user has not rested. The break **stays owed** and
comes back at a retry deadline, which is shorter than a fresh focus interval:
`BREAK_DUE -> DEFERRED -> BREAK_DUE`.

**Satisfaction** — the environment already gave the user a genuine break. The
session was locked for twenty minutes; they were away from the screen. Asking
them to rest now would be absurd. The owed break is **discharged** and focus
accumulation **resets**: `BREAK_DUE -> FOCUSING`, `DEFERRED -> FOCUSING`.

These reach the timer through separate methods (`defer` and `satisfy_break`) on
separate branches of `BreakPolicy`, and produce separate outcome types
(`BreakDeferred`, `BreakSatisfied`). Nothing downstream has to inspect a flag to
work out which happened. Satisfaction additionally demands evidence: it takes a
`rest_duration` and refuses anything shorter than the break it would discharge,
raising `InsufficientRestError`. A deferral needs no such evidence, because it
discharges nothing.

Keeping them apart is what lets P1 add real detectors without reopening the
state machine.

## No flag for an owed break

`DEFERRED` **is** the owed break, postponed. There is no `break_owed` field
anywhere in the timer; owed-ness is `state in (BREAK_DUE, DEFERRED)`, exposed as
a derived read-only property on `TimerSnapshot`. A stored flag would be a second,
invisible state machine running alongside the visible one, free to disagree with
it. A derived property cannot drift.

## States

```
IDLE ──start──> FOCUSING ──focus interval elapses──> BREAK_DUE
                                                      │
                        suitable context ─────────────┤──> ON_BREAK ──break ends──> FOCUSING
                        unsuitable context ───────────┤──> DEFERRED ──retry deadline──> BREAK_DUE
                        genuine external rest ────────┴──> FOCUSING (owed break discharged)

any active state ──pause──> PAUSED ──resume──> the exact prior state
```

`PAUSED` freezes every stopwatch and remembers what it interrupted, so resuming
returns to `ON_BREAK` or `DEFERRED` — not just to `FOCUSING` — with the same
progress it had.

Focus keeps accruing through `BREAK_DUE` and `DEFERRED`, so `focus_elapsed`
stays honest about the real stretch at the screen instead of freezing the moment
a break went untaken.
