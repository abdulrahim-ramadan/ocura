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

`ruff`'s banned-api rule enforces part of this mechanically, at two levels.
`pyproject.toml` bans `PySide6` everywhere below the UI. `src/ocura/domain/.ruff.toml`
additionally bans `ctypes`, `sqlite3`, `winreg`, `msvcrt` and the `win32*` modules
inside the domain only — infrastructure is the layer that is supposed to import
those. Note that the child table *replaces* the parent's rather than merging with
it, so the domain config restates the `PySide6` ban; dropping that line would make
the domain the one layer where a UI toolkit is allowed.

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

## What happens when two things land in the same tick

The ordering is defined by two pieces of code, not left to chance.

`BreakTimer.tick()` matches on a single subject, `self._state`, across three
mutually exclusive guarded arms with no loop: **at most one time-driven
transition per tick, and it never cascades**. A tick can move `FOCUSING ->
BREAK_DUE`, but it cannot then move on to a third state on the same tick.

`BreakSession.tick()` then fixes the order between the two kinds of event:

1. time first — `self._timer.tick()`
2. a gate — detectors are consulted only if a break is now owed
3. context second — `policy.resolve(timer, context.assess(snapshot))`

So a tick applies at most one time transition followed by at most one context
transition, and the context source is called exactly once, only when its answer
can change something. Time wins the ordering because whether a break is owed has
to be settled before asking whether interrupting is wise.

| Situation | States traversed in one tick | Events, in order |
| --- | --- | --- |
| Retry deadline reached, detector reports rest | `DEFERRED -> BREAK_DUE -> FOCUSING` | `break_due`, `break_satisfied` |
| Retry deadline reached, still unsuitable | `DEFERRED -> BREAK_DUE -> DEFERRED` | `break_due`, `break_deferred` |
| Focus interval expires, detector reports rest | `FOCUSING -> BREAK_DUE -> FOCUSING` | `break_due`, `break_satisfied` |
| Focus interval expires, nothing in the way | `FOCUSING -> BREAK_DUE -> ON_BREAK` | `break_due`, `break_started` |

Two state changes in one tick is normal and deterministic. These sequences are
asserted in full, in order, by `tests/unit/test_session.py`.

**A `break_due` event is not an instruction to interrupt.** It records that a
decision point was reached, and it is emitted even when the break is discharged
later in the same tick. The UI in P3 opens the break overlay on `break_started`
and never on `break_due`; keying off `break_due` would flash an overlay for a
break that was satisfied microseconds later.

## Rest taken before a break is owed

Rest during `FOCUSING` is **not** satisfaction. Nothing is owed yet, so there is
nothing to discharge. It is a *pending observation*, and it is consumed at the
next `BREAK_DUE`.

This is why `satisfy_break` remains reachable only from `BREAK_DUE` and
`DEFERRED`. The alternative — letting rest discharge a break that does not exist
— would put a second, invisible accumulator inside `FOCUSING`, which is the same
mistake as a stored `break_owed` flag wearing a different hat.

The consequence is a requirement on P1, not on the domain. Without it, a
twenty-minute lock at minute five of a focus block is invisible: the session
gate never even consults the detector, focus accrues straight through the
absence, and the user is prompted having just returned from twenty minutes away.

P1's idle/lock detector therefore carries the credit itself:

- it accumulates uninterrupted away-time while the session is `FOCUSING`, and
  reports it as `RestSatisfied` at the first tick where a break becomes owed
- credit is **consumed once and then cleared** — one rest can never satisfy two
  breaks
- credit **expires after 30 minutes**. Rest from three hours ago is not rest
  now, and stale credit silently cancelling a genuine break is worse than no
  credit at all
- the accumulating, expiring and clearing all live in
  `ocura/infrastructure/`. The domain never learns that pending credit exists;
  it only ever sees a `RestSatisfied` arriving at a moment when a break is owed,
  which is a thing it already understands

The domain keeps its existing veto either way: a credit shorter than
`break_duration` is refused with `InsufficientRestError`, whatever the detector
believes it saw.

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
