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
- credit **expires 30 minutes after the rest ended**. Staleness is measured from
  the end of the rest, not from its start and not against its length: a
  45-minute lock still counts in full the moment the user sits back down, and
  goes stale half an hour later. Expiring long rests on arrival would punish
  exactly the breaks that were most real. Rest from three hours ago is not rest
  now, and stale credit silently cancelling a genuine break is worse than no
  credit at all
- the accumulating, expiring and clearing all live in
  `ocura/infrastructure/`. The domain never learns that pending credit exists;
  it only ever sees a `RestSatisfied` arriving at a moment when a break is owed,
  which is a thing it already understands

The domain keeps its existing veto either way: a credit shorter than
`break_duration` is refused with `InsufficientRestError`, whatever the detector
believes it saw.

## What counts as rest: lock yes, idle no

Two signals could plausibly mean "the user is away". Only one of them is allowed
to discharge a break.

**Session lock is satisfaction, unconditionally.** Locking is a deliberate act
that means "I am leaving". There is no ambiguity in it and therefore no
threshold on it: lock duration feeds the credit accumulator directly, subject
only to the 30-minute staleness window and the domain's `break_duration` veto.

**Idle alone is deferral only, and never satisfaction.** Not gated behind a
setting, not configurable — excluded by design.

The reason is the reading case. A person reading a long document produces no
keyboard and no mouse input for many minutes while their eyes are in the worst
state they get into: sustained fixation, blink rate collapsed. That user looks
identical to an empty chair through `GetLastInputInfo`, and they are precisely
the user who most needs the break. Crediting idleness as rest would make Ocura
go quiet on them.

The asymmetry of the two mistakes settles it. A break offered to someone who had
already stepped away is a small cost — a notification nobody was there to see.
A break silently cancelled for a reader is the product failing at its one job.
When the evidence is ambiguous, Ocura pays the small cost.

So idle **defers** the offer, because interrupting an empty chair accomplishes
nothing, and the owed break simply waits and fires when they come back. Idle
never discharges anything.

The credit accumulator therefore observes lock duration only. Idle feeds
`Deferral` and nothing else. The accumulator takes credit through a single
entry point that names the source of the rest rather than hard-coding the lock
detector, so a future signal can feed it without restructuring: P6 may add
"idle **and** the foreground window has not changed for N minutes" as a reading
discriminator, at which point long idle with a *changed* window becomes
creditable. That is not built now, and idle remains non-creditable until it is.

## The P1 Windows context layer

Four detectors, each answering for one signal, composed by `DetectorChain`:

| Detector | Signal | Answer |
| --- | --- | --- |
| `SessionLockDetector` | `OpenInputDesktop` fails | `Deferral` while locked, `RestSatisfied` on return |
| `IdleDetector` | `GetLastInputInfo` ≥ 120s | `Deferral`, never anything else |
| `PresentationDetector` | `SHQueryUserNotificationState` | `Deferral` |
| `ScreensaverDetector` | `SPI_GETSCREENSAVERRUNNING` | `Deferral` |

Every detector is consulted on every assessment and the order they are listed in
does not change the result, because `combine()` reduces their answers by rank
rather than by position: **rest beats deferral beats interruptible**. Rest wins
because it discharges the break outright — if the user genuinely rested, a bad
moment to interrupt is moot, there is nothing left to interrupt them for.
Returning from lunch into a fullscreen app therefore pays the break rather than
postponing it. Among several deferrals the shortest explicit `retry_after` wins:
asking again too early costs a wasted question, asking too late costs the moment
the user became free.

Adding a detector is adding one class with an `assess` method and one entry in
`build_windows_context`. Nothing else changes, which is the whole point of the
abstraction.

### Two entry points, because a break is not always owed

`assess()` runs only when a break is owed, which is right for deciding whether
to interrupt and useless for watching a lock that started twenty minutes ago.
`WindowsContext.poll()` therefore runs on **every** application tick and drives
the observation that has to happen regardless — currently just the lock detector
accumulating away-time into the ledger. The application loop calls `poll()` and
then `tick()`; P2's UI timer will do the same.

### Polling, not window messages

Lock and unlock notifications (`WTSRegisterSessionNotification`,
`WM_WTSSESSION_CHANGE`) need an `HWND` and a message pump. Taking them would drag
a UI dependency into the infrastructure layer and invert the direction of the
architecture, so P1 polls once per second instead. At this scale the cost is
nothing and the layering stays intact.

`api.py` is the one module with no test coverage: it is the boundary where
mocking stops meaning anything. Everything above it takes its signal as a plain
callable, which is why the detectors are fully tested without a Windows API in
sight. What that buys in testability it gives back in risk, which the next
section is about.

## Verified against the real API

Two defects in `api.py` were found by running it against a real Windows desktop
and reading the numbers, not by testing and not by reasoning. Both versions read
as obviously correct. They are recorded here with the measurements so that a
future refactor cannot reintroduce either by arguing from first principles.

**A maximized window is not a fullscreen window.**

The first `PresentationDetector` asked whether the foreground window's rectangle
covered its monitor's rectangle. Measured on a maximized (not fullscreen)
terminal:

```
window rect : (-1088,  -8,    8, 1928)
monitor     : (-1080,   0,    0, 1920)
work area   : (-1080,   0,    0, 1920)
=> covered the monitor on all four edges: True
```

A maximized window overhangs its monitor by the invisible 8px resize border, so
it passes the test on every edge. The work area was identical to the monitor
rectangle here, so falling back to that would not have helped either. *Every
maximized window* would have read as fullscreen and Ocura would have deferred
every break forever — a permanently silent app that looks like it is working.

`SHQueryUserNotificationState` reports `QUNS_ACCEPTS_NOTIFICATIONS` (5) for that
same window. It is the OS's own answer to "is this a good moment to show
something", it distinguishes maximized from fullscreen correctly, and it knows
about presentation mode and Focus Assist, which no rectangle comparison can.

Do not replace it with geometry.

**`GetLastInputInfo` returns a 32-bit tick count.**

`LASTINPUTINFO.dwTime` is a `DWORD` sourced from `GetTickCount`, which wraps
every 49.7 days. `GetTickCount64` does not. Subtracting one from the other is
correct until the machine has been up for 49.7 days and then reports roughly
`2**32 / 1000` seconds — about 50 days — of idleness, permanently, on every
call. Ocura would deem the user eternally absent.

```python
now = _kernel32.GetTickCount64() & 0xFFFFFFFF
return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0
```

Truncating to 32 bits and taking the difference modulo 2³² makes the wrap
cancel. Do not "simplify" this by dropping the masks; nothing in the test suite
or in a short manual run will notice, and the bug reappears after seven weeks of
uptime.

**`OpenInputDesktop` does not detect a lock. It detects the secure desktop.**

The first `is_locked()` opened the input desktop and treated failure as a lock.
That is the widely repeated recipe and it is wrong: the handle does not start
failing when the session locks, it starts failing once the secure desktop
actually *becomes* the input desktop, which typically waits for the display to
sleep. Measured against `WTSQuerySessionInformationW` across one real lock:

```
00:38  WTS SessionFlags -> 0 (LOCKED)      OpenInputDesktop -> still a handle
01:05  WTS SessionFlags -> 0 (LOCKED)      OpenInputDesktop -> NULL (27s late)
01:08  WTS SessionFlags -> 1 (unlocked)    OpenInputDesktop -> handle
```

Worse than lagging, it **oscillates**. Across one continuous lock, with WTS
holding `LOCKED` from 00:31 to 01:16 without interruption:

```
00:31  OpenInputDesktop -> NULL     (LOCKED)
00:32  OpenInputDesktop -> handle   (unlocked)   <- the session never unlocked
01:13  OpenInputDesktop -> NULL     (LOCKED)
01:16  OpenInputDesktop -> handle   (unlocked)   <- the real unlock
```

This is the stronger argument, and it is fatal rather than merely inaccurate.
`SessionLockDetector.observe()` banks the elapsed away-time and clears
`_locked_since` the moment its signal reads unlocked, so a flip mid-lock does
not shorten the measurement — it *restarts* it. The 45-second absence above was
recorded as a 1-second fragment followed by a 3-second one, and because a newer
credit replaces an older one rather than summing, only the 3 seconds survived.
**No amount of staying away could ever have produced enough credit**, at any
schedule, on any machine where the signal flickers.

The 3 seconds then met the demo's 5s `break_duration`, so `satisfy_break`
refused it with `InsufficientRestError`, the policy turned that into `NoAction`,
and no break was ever discharged. **Every part of the rest-credit mechanism was
correct and it produced nothing, because it was fed a bad measurement.** A wrong
number is harder to see than a wrong branch, and a number that is wrong
*intermittently* is harder still.

Note what this implies about the detector's contract: it trusts its signal to be
stable, because a lock genuinely is. Any future lock source must be edge-stable
for the whole absence, not merely correct on average.

`is_locked()` now asks WTS (`WTSSessionInfoEx` → `SessionFlags`, `0` meaning
locked) and falls back to `OpenInputDesktop` only when the WTS query itself
fails. Do not promote the fallback back to primary — not for simplicity, not to
drop a DLL dependency.

### Verified end to end on real hardware

```
[00:25] DEFERRED  focus 10.0s  break_due, break_deferred (session locked)
[00:42] DEFERRED  focus 27.0s  owed
[00:43] FOCUSING  focus  0.0s  break_satisfied (session lock)
```

Credit accumulated during the lock, the owed break survived 17 ticks in
`DEFERRED`, and unlocking discharged it with focus accumulation resetting to
zero. Two normal cycles followed immediately.

**`SHQueryUserNotificationState` works, and only for the primary display.**

Confirmed working: F11 in a browser moved it to `2 BUSY(fullscreen)`, and a
maximized Brave window at `(-8, -8, 2568, 1448)` against a monitor of
`(0, 0, 2560, 1440)` — `covers=True` by rectangle — correctly stayed at
`5 ACCEPTS_NOTIFICATIONS`. The maximized-window fix is independently
reconfirmed on a second app and a second monitor.

Its limitation is recorded in the next section.

## Known limitation: fullscreen on a non-primary display

`SHQueryUserNotificationState` watches the primary display only. Measured on a
two-monitor setup — primary `(0, 0, 2560, 1440)`, portrait secondary
`(-1080, 0, 0, 1920)` — a window covering the *secondary* monitor exactly:

```
01:18  foreground win=(-1080, 0, 0, 1920)  mon=(-1080, 0, 0, 1920)
       primary=False  covers=True  exact=True
       notification state: 5 ACCEPTS_NOTIFICATIONS
```

So a fullscreen video or presentation on a secondary monitor is **not**
detected, and Ocura will offer a break through it.

Do not fix this by falling back to comparing window and monitor rectangles when
the window is off-primary. That reintroduces the maximized-window defect
described above, on exactly the monitor where it is least likely to be noticed,
and trades a rare missed deferral for a permanent one. A missed deferral costs
one badly-timed offer; a false deferral costs every break.

Detecting fullscreen on non-primary displays needs a method that does not rely
on geometry. That is an open question for P6, recorded in
[ROADMAP.md](ROADMAP.md); until it is answered, the limitation stands as
written.

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
