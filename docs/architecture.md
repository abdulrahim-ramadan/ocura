# Architecture

## Verification discipline

**Never state that something works unless the thing itself was observed, in the
form the user encounters it.** Not a proxy, not a re-render, not a grep over
output, not a passing test that exercises a different path.

Every claim about this project carries the ground it rests on:

| Label | Means |
| --- | --- |
| **MEASURED** | The actual artifact was observed, and the output is shown |
| **TESTED** | A test asserts it, and what the test checks is stated |
| **INFERRED** | Reasoned from code that was read, not observed running |
| **UNVERIFIED** | Not checked |

An INFERRED claim never gets the wording of a MEASURED one. "It should now
work" and "it works" are different sentences, and the right one gets used. A
failure is reported as a failure: "the build failed", never "the build
completed with an issue". Where something cannot be verified, that is one line
and then the work moves on — an honest UNVERIFIED costs nothing, and a
confident claim that turns out to be false costs an hour and the credibility
behind every other claim.

Before calling anything done: *was this observed, or was something observed
that stands in for it?* If the second, the proxy gets named along with what it
cannot show.

### The three incidents this rule is made of

This is not a principle borrowed from somewhere. Three times in this project
the verification method itself reported something other than reality, and each
claim was made in good faith and was still wrong.

**`QWidget.grab()` re-renders the widget and bypasses composited output.** It
was used to screenshot the overlay throughout the life of the overlapping-label
defect, and every screenshot looked correct while the real screen did not.
`QGuiApplication.primaryScreen().grabWindow(0)` reproduced the fault on the
first try. A re-render cannot show a compositing fault, because compositing is
the step it skips.

**Grepping build output instead of reading it hid a failing build for two
days.** A release build was failing on `PermissionError: dist\Ocura` — a running
`Ocura.exe` holding the folder — while a `| grep` over its output showed only
the lines that were being looked for. The icon under investigation was being
extracted from a stale binary from the previous day the whole time. When the
question is "did this work", pipe to `tail` and read it; a grep can only
confirm what was already assumed.

**Capturing the break overlay with motion disabled showed the focus shape at
its receded size.** Reduced motion applies the end state of an animation
immediately, so the capture showed the shape at `SHAPE_MIN_SCALE` — a third of
the size the break opens with. Two rounds of retuning went into a shape that
was never wrong. A capture taken in a mode the user is not in is a capture of
a different screen.

The common shape of all three: the proxy was cheaper than the real thing, and
the difference between them was exactly where the defect lived.

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

## The Qt boundary

`ocura.ui` is the only package permitted to import a UI toolkit, enforced by
`src/ocura/ui/.ruff.toml` — which drops the inherited `PySide6` ban and restates
the platform and storage bans, since a child table replaces rather than merges.
It additionally bans `ocura.domain.timer.BreakTimer` and `ocura.domain.policy`
outright: a widget that reaches for either has crossed the line this section
exists to draw.

### The presenter holds the seam

`BreakPresenter` owns the `BreakSession`, advances it, and renders everything a
view needs into one immutable `SessionView`. Widgets read that snapshot and
nothing else. They never see a `BreakTimer`, a `BreakPolicy` or a detector, and
they do no arithmetic on domain enums.

Finished **text** lives in the snapshot too — `headline`, `detail`,
`countdown_text`, `waiting_reason`. That is deliberate: the language rules are a
product decision, and `test_no_event_text_is_accusatory` can assert them across
every state without a display, which a widget test could not.

The presenter is testable with a `FakeMonotonicClock` and a scripted context, no
`QApplication` and no widget anywhere. If it ever needs a window to test, the
seam has moved to the wrong place.

### The presenter owns the tick; Qt delivers the pulse

`TickDriver` is a `QTimer` and a signal. It holds no state and decides nothing.

A pulse must never mean *"one second has passed."* Qt timers coalesce under
load, stall behind modal dialogs and drift across sleep and resume. Every
duration in Ocura is re-read from the monotonic clock on each pulse, so a late,
dropped or doubled pulse costs refresh latency and cannot corrupt a measurement
— the same property that makes `BreakTimer.tick()` safe to call at any rate.
`TICK_SECONDS` therefore lives in the presenter as advisory cadence, and tests
pulse in a plain loop.

Detector polling rides on the same pulse: `BreakPresenter.tick()` calls
`context.poll()` when the context satisfies `PollableContext`, so lock time
accumulates even when no break is owed.

### One engine per machine

Two processes would tick two independent `BreakTimer`s against the same person,
double-count every break and disagree in the tray. `SingleInstance` claims a
`QLocalServer` pipe; a second launch finds it, asks the first to show itself and
exits. A pipe rather than a lock file because a lock file outlives the crash
that left it behind and then blocks every future launch.

### Styling

One QSS template built from `Tokens`, applied once at application level. No
widget names a colour and none calls `setStyleSheet` — `test_no_widget_module_hardcodes_a_colour`
greps the package to keep it that way, so P6 can restyle by editing token values
rather than hunting through widgets. Dark and light are the same template with
different token values.

Layout margins live in Python because Qt layouts cannot be reached from QSS, but
they read the same `Spacing` scale, and `test_no_widget_module_hardcodes_spacing`
fails the build on a literal in `setContentsMargins`, `setSpacing`, `addSpacing`,
`setFixedWidth` or `setMaximumWidth`.

### Assets

Icons are package data under `ocura/ui/assets/`, read through
`importlib.resources` as bytes rather than as a path relative to the source
tree. A path built from `__file__` and `parents[n]` resolves only while there is
a repository around the code, which stops being true the moment P7 packages it.
`scripts/make_icon.py` regenerates a plain fallback used only if the real icon
is missing.

### Theme choice, and where it lives for now

The dark/light choice is stored in `QSettings` under `shell/theme`, alongside
window geometry. Both are shell state rather than user settings, and the theme
control lives in the sidebar footer rather than in Settings, which is P5 and
stays honestly empty until it has something real to write into.

**P5 moves the theme into the real settings model** and the sidebar control
becomes a shortcut to it. The `shell/` namespace exists so that migration is a
move rather than an excavation.

On first run, with nothing stored, Ocura follows the system colour scheme via
`QStyleHints.colorScheme()` and falls back to dark when Qt reports `Unknown`.

## Motion policy

The dashboard is a two-second glance surface and must be still.

Peripheral motion pulls the eye involuntarily. An eye-care application that
animates continuously is interrupting the user without permission — the exact
behaviour the entire product exists to avoid — so a permanently moving element
on the dashboard is not a decoration to be tuned, it is a contradiction. An
animated blinking eye was considered for the dashboard and **rejected on this
ground**, not on grounds of effort or taste.

What is allowed, and nothing else:

- the countdown fill glides to its new value rather than stepping once a second
- page transitions cross-fade over 200ms
- a state change fades rather than snaps

Every one of those is triggered by a change and runs exactly once. Nothing
loops, nothing pulses, nothing moves while the state is unchanged. The countdown
fill is the only continuous-*looking* animation and it is not a loop: each tick
starts a single interpolation that happens to arrive as the next begins.

The break overlay's own fade is the fourth, and it is a transition rather than
an ornament: a full screen changing colour in one frame is a shock to the eye.

All animation is skipped when Windows reports reduced motion
(`SPI_GETCLIENTAREAANIMATION`, read in the infrastructure layer since it is a
platform call). A failed read leaves motion on: motion is the normal case, and
an unreadable setting is not consent either way.

Animations are created in `ocura/ui/motion.py` and nowhere else, which
`tests/unit/test_motion_policy.py` enforces by parsing the package: only
`driver.py` may own a repeating timer, `setLoopCount` must be exactly 1,
`QMovie` and `QTimeLine` are banned outright, and the dashboard's fade must stay
guarded by a state comparison.

Purposeful motion belongs in the P3 break screen, where it is bounded to the
length of a break and is the point of the screen rather than a background
texture.

## The break experience

### Two windows with opposite focus rules

The **toast** must never take keyboard focus. It appears while the user is
mid-sentence by definition — that is what a warning is — so a stolen keystroke
there is the worst failure in the milestone. Three things enforce it, because
any one alone is easy to undo by accident: `Qt::WindowDoesNotAcceptFocus`,
`WA_ShowWithoutActivating`, and `Qt::Tool`. Its buttons are `NoFocus` and
reachable by mouse only, since a focusable button means a focusable window.
`test_showing_the_toast_does_not_steal_the_keystroke` types half a sentence,
raises the toast, and finishes the sentence.

The **overlay** does take focus, deliberately. Esc has to reach it, and an
unavoidable full-screen window that cannot be dismissed from the keyboard is a
worse outcome than a taken focus. The guarantee about keystrokes therefore sits
entirely on the toast: the warning is what gives the user time to finish before
the screen is covered.

### Cover, do not capture

The overlay sets no keyboard hook, holds no grab, runs no timer re-asserting
z-order, and never takes the fullscreen *window state* — which is exclusive on
Windows and makes several windows fight over the shell. Ctrl+Alt+Del, the lock
screen and the task switcher behave exactly as they would if Ocura were not
running, because the secure desktop is a separate desktop and nothing here
tries to follow it there. Skip is always visible; the snooze control is the
only one that can disappear.

### Screens

One window per screen at `screen.geometry()` — the full rectangle, taskbar
included, since a break screen that leaves the taskbar showing has a bright
strip along one edge. Every screen event runs the same idempotent `_sync()`,
which diffs windows against screens; `plan()` is its pure core and is tested
with plain strings. Losing every display is survivable: zero windows, a logged
warning, and the manager stays open, because the break is timed by the engine
rather than by a window.

Content is sized against `min(width, height)`, so the portrait monitor gets a
circle rather than a landscape composition stretched sideways, and the leftover
vertical space is left empty. Empty space on a break screen is the point.

**Pending hardware confirmation.** Reconciliation is verified by *simulating*
the screen list — a monitor cannot be unplugged from a test. Qt's real
`screenRemoved` timing on a physical disconnect mid-break has not yet been
observed, and the handler drops the window explicitly before reconciling
precisely because that timing is not guaranteed. To be confirmed or corrected
against hardware.

### Motion, bounded to the break

Two animations, each started once when the overlay opens and each lasting
exactly the break: the focus shape recedes from 1.0 to 0.35, and an eyelid line
closes three times. The blinks are key frames on a *single* animation rather
than a repeating timer or an animation group, so when the run finishes nothing
is left scheduled. A third, the 400ms fade the window arrives and leaves on,
is bounded by its own duration. All three are skipped under reduced motion,
leaving a still screen with the number.

This is the exception the motion policy allows, and it is bounded by the break's
own length. An animated element on the *dashboard* remains ruled out for the
reasons in that policy.

### The screen is a ladder, not a palette

Every colour on the overlay is in `theme.Tokens._OVERLAY`, identical in both
themes, and what matters about them is their order. Measured as WCAG contrast
against the background:

| Element | Ratio | Why there |
| --- | --- | --- |
| focus shape | 1.9:1 | a distant object; it was the *brightest* thing here |
| eyelid cue | 2.9:1 | only while closing; 1.1:1 the rest of the time |
| tip | 2.2:1 | found only if looked for |
| countdown, controls | 5.1:1 | available, never competing |
| instruction | 7.6:1 | the one thing meant to be read |

The background is a low-saturation brown-charcoal rather than a neutral grey.
At this lightness neutral grey reads as switched-off hardware; the warmth is
what makes the screen read as *dimmed*. The text is a muted sand and never
white — presence comes from the type scale, not from luminance.

`tests/unit/test_theme.py` asserts the ordering rather than the values, so P6
can retune every colour and still fail the moment the argument stops holding.

### Nothing on it has an edge

The focus shape is painted with a radial alpha falloff: solid to 60% of its
radius, gone by the rim. A hard circle is a luminance step, and a luminance
step is precisely what the eye fixates on — on the one screen asking it to
fixate on nothing. `test_the_shape_has_no_edge_to_fixate_on` walks inwards
from the rim and fails if any neighbouring pair of pixels differs by more than
four levels of lightness.

Its box is exactly its extent, not a stretch weight. A box larger than what it
paints put two hundred pixels of nothing between the shape and its own
instruction, which is what made the text look stranded at the foot of the
screen. Shape, cue, instruction, countdown and controls are one optical group
in the upper third, each gap stated on its own line rather than by a uniform
`setSpacing`; the emptiness is at the outer edges, where it belongs.

### The eyelid closes, it does not fade

A full-width hairline is a separator, and a separator is furniture — read once
and never looked at again. The cue is a third of the screen wide, centred,
eight pixels thick with rounded ends, and it **closes from both ends towards
its centre**, because that is what a lid does. What fades is only its presence
between blinks: at rest it sits at 1.1:1, which is there but not a line.

### The tip

The evidence-sourced line at the foot of the screen did not exist. There was no
widget for it, no rule in the stylesheet, and no field on `SessionView` for one
to come through — it had never been built, so "why does it not appear" has the
dull answer. It now comes from `presenter.BREAK_TIPS` like every other piece of
language in the product, one per break, keyed to the count of breaks finished
so it cannot rewrite itself mid-break.

Each states the evidence the break rests on and stops there. It is not a second
instruction — the screen already says what to do, and a smaller voice repeating
it in the corner is nagging — and each carries its source, because a claim
about someone's eyes that cannot be traced back to anyone is not worth putting
on screen at all.

### Arriving and leaving

The overlay fades in over 400ms and out again, through `windowOpacity` rather
than a `QGraphicsOpacityEffect` — the effect's cached source pixmap is the
defect described under the motion policy, and this window contains a label that
repaints every second. An abrupt full-screen change is itself a shock to the
eye, which is the one thing this screen exists not to be.

That makes closing asynchronous, so `OverlayManager` drops a window from its
map immediately and holds it in `_closing` only until the fade ends: the
manager's own state never waits on an animation, and `close()` leaves nothing
behind for a caller that looks straight afterwards. Under reduced motion the
callback runs synchronously — it is what actually disposes of the window, so a
branch that skipped it would leave an invisible always-on-top window over the
desktop.

### Snooze, and where the cap lives

`MAX_SNOOZES = 2`, in the domain, enforced by `BreakTimer.snooze()` raising
`SnoozeLimitReached` past the cap. Snoozing is available from the warning, the
offer and the break itself — all three are moments where the user is being asked
"now?" — and lands in `DEFERRED`, because a postponed break is an owed break
with a deadline whoever asked for it.

Past the cap the break is offered again **without** the option, which is not the
same as forcing it: the user can still skip, and skipping says nothing about
having skipped. The count is consecutive: a break actually taken resets it, so
the cap limits a run of postponements rather than a day of them.

## P4 — local history

One SQLite file, written by `ocura.infrastructure.storage` and reached from
above through a protocol that never mentions a database.

### The seam

`SessionJournal` (`application/journal.py`) is one method: `record(event)`.
`BreakPresenter` takes one and tees every `SessionEvent` into it. Storage
implements it, tests use a list, and `NullJournal` is what runs when there is
nowhere to write — with the session behaving identically, which is the point.
History is a record of the product working, never a part of it working.

`sqlite3` is now banned in three layers rather than two:
`src/ocura/application/.ruff.toml` joins the domain's and the UI's, because P4
is the first milestone where the application layer would have had a reason to
reach for it. Each of those tables *replaces* the parent's rather than merging
with it, so each restates the `PySide6` ban — verified with a probe file,
which showed `sqlite3`, `PySide6` and `ctypes` all refused in `application/`
and `sqlite3` still allowed in `infrastructure/`.

Nothing above the package ever sees a `sqlite3.Error`. Everything that leaves
it is a plain dataclass or a `StorageError`, and the connection type is
re-exported as `storage.Connection` so a caller can name one without importing
the module it is banned from.

### Persistence is best-effort; the engine is not

A full disk, a file an antivirus scanner has locked, or a database written by a
newer Ocura costs the user their history and must never cost them a break. The
store reports failures honestly and `BreakPresenter._keep` is the single place
that decides they are survivable. Its `except` is deliberately broad: a journal
is a protocol, and an implementation failing in an unanticipated way still must
not be able to stop the timer.

Proven against a file the process genuinely cannot write to, not against a
stand-in that raises on cue: a test makes a real database read-only, opens it —
which still succeeds, because history that cannot be added to is still worth
reading — and runs a whole break through the real `EventStore` behind the real
presenter. The break starts, finishes and counts; nothing reaches the file; the
warning is logged. A stand-in proves the presenter survives what the test
author imagined, and that is a weaker claim.

The same rule at start-up. `open_history()` logs and returns a `NullJournal`
rather than refusing to launch: everything the product actually does works with
no database at all, and a start-up error about SQLite on a machine where the
timer would have run fine is worse than the problem it reports.

### One table, because a total is a second copy of the truth

There is no `sessions` table and no `daily_metrics` table. A session is the run
of events between a STARTED and the next STOPPED; a day's metrics are a count
over a date range. Both are questions the log already answers, and a stored
total is free to disagree with the events it claims to summarise — the same
argument this codebase already made about owed breaks under "No flag for an
owed break".

`run` is the one column that is not an event: a local counter, incremented per
launch, which exists because STARTED and STOPPED cannot delimit a run that
ended in a crash, and two runs merged into one would be history that never
happened. It says which launch a row belongs to and nothing else.

### Every break event, told apart

The log keeps the distinctions the product makes rather than the ones a
dashboard happens to show. A break offered, begun by the engine, begun by the
user, run to its end, ended early, postponed by a detector, postponed by the
user, and discharged by a rest the user had already taken are eight kinds, not
three. `BREAK_SKIPPED` is the newest of them: the presenter counts it exactly
as `BREAK_COMPLETED` and the event list says "Break finished" for both, because
skipping says nothing about having skipped and a list that commented on it
would be a list with an opinion. The difference is a fact, so it is kept where
facts are kept.

`detail` carries the detector's reason where there was one, and nothing where
nothing had to be explained.

`duration` carries the span the event is about, in seconds, and is NULL where
no span applies. Nullable rather than defaulted to zero on purpose: a break
skipped the instant it began lasted no time, a session being paused was never
about time at all, and those two must not read the same. Which span it is
depends on the kind — the stretch at the screen that earned an offer, how long
a break lasted, how long a postponement runs for, how long the external rest
was — and in each case it is read from the timer rather than assumed from the
schedule, so a detector's own retry deadline or a focus block stretched by a
deferral lands as the number it really was.

A break that ran its course records exactly the scheduled duration, because the
snapshot clamps at zero remaining. That is deliberate: a pulse arriving half a
second after the twenty seconds are up is latency in the timer that observed
the break, not extra break. The number nobody scheduled only appears on a break
ended early, which is the one worth reading.

**No user identifier, ever.** Not a UUID, not a machine ID, not a hashed one.
`test_no_table_carries_anything_that_could_identify_anyone` migrates a real
file, reads its actual `PRAGMA table_info`, and fails on any column name
containing any of a list of words — so the constraint is checked against the
schema that exists rather than against the one that was intended.

### Migrations

`PRAGMA user_version` is the marker: one integer in the file header, written
inside the same transaction as the DDL it describes, so it cannot get out of
step with the schema it claims to describe. Migrations are a tuple in a module
rather than a directory of numbered files — at this size the whole history fits
on one screen, and a step that cannot be read next to the one before it is a
step nobody will check.

The `schema_version` table beside it is a **ledger, not a second marker**: one
row per version applied, with the time it was applied. It answers what the
pragma cannot — *when did this file become a v2* — which is the first thing
worth knowing when one tester's database behaves unlike everybody else's, and
it is readable with the same `sqlite3` command as everything else. `migrate()`
reads the pragma and never the ledger, so the two cannot disagree about what
the schema *is*; a ledger that has been truncated or dropped cannot make a v2
file migrate itself twice. There is a test that deletes every row in it and
asserts exactly that.

The ledger is created outside the migration list rather than by a step in it,
because the first step has to be able to record itself — including on a file
being created from nothing. `applied_at` is NULL for a version reached before
the ledger existed, which is every database the first release wrote. When is
not recoverable for those, and inventing a timestamp would make the column
worthless for the ones that are real.

**v1 → v2** adds `events.duration`. It exists partly to carry the number and
partly because P5 will change this schema and an upgrade path first exercised
when it is needed is an upgrade path nobody has run. A test builds a real v1
file — by running the shipped migration with the version pinned, not by
hand-copying its DDL into the test, and then dropping the ledger the first
release did not have — upgrades it, and asserts the rows are still there with
NULL in the new column. Not zero: nobody measured those breaks, and a
backfilled zero would be a measurement nobody took.

A step that fails rolls back with the version untouched. A half-applied
migration carrying a version that claims otherwise is a database that fails the
same way on every launch afterwards, with no way back, and there is a test that
breaks a migration on purpose to prove it does not happen.

A file from a **newer** Ocura is refused rather than migrated backwards. That
build may have added a NOT NULL column this one knows nothing about, and
writing rows the user's actual version cannot read is worse than losing the
history.

`isolation_level=None` with explicit BEGIN/COMMIT, because sqlite3's implicit
handling opens a transaction before DML but not before DDL — exactly the wrong
way round for a migration that has to be all-or-nothing.

### The statistics page

A second seam, built the same way as the first. `StatisticsSource`
(`application/statistics.py`) is a one-method protocol — `read(days)` — and the
shapes it returns live up there with it, exactly as `SessionEvent` does.
`StatisticsStore` implements it over SQLite, `NullStatistics` is what runs when
there is nowhere to read from, and the page behaves identically with it.

There is no `daily_metrics` table. A day is a count over the log, a week is
seven of them, and a stored rollup would be a second copy of the truth free to
disagree with the events it summarises — the argument this codebase has already
made twice, about owed breaks and about session totals. A week is a few hundred
rows.

**Day bucketing is done in Python, not in SQL.** Rows are stored in UTC because
a log ordered in mixed zones is not ordered, and a day is a local thing.
SQLite's `datetime(..., 'localtime')` reads the host's zone and cannot be
pointed at another one for a test, so the range filter runs in SQL over UTC
text and `datetime.astimezone` does the conversion. The tests drive it at fixed
offsets on both sides of UTC, across a midnight, a month end and a year end.

**"At the screen" is the sum of measured focus blocks**, taken from the
`duration` on each `BREAK_DUE` row — a monotonic measurement made when the
block completed. Not the wall-clock gap between rows: a laptop that slept for
three hours between two events would book that sleep as three hours of screen
time. The cost is that a block still running, or one ended by stopping the
session before a break came due, is not counted, so today's figure can lag by
up to one focus interval. The page says as much in its own subheading. A number
that is honestly incomplete beats one that is silently wrong.

**Deferral reasons are folded into families.** The idle detector writes its
measurement into its reason — `idle for 312s` — so grouping on the raw string
would produce one bucket per deferral and a list nobody can read. The folding
is prefix-matched in one place, and a reason this build has never heard of is
kept verbatim rather than swept into an "Other": a detector added later shows
up as itself on the day it ships, the same rule that makes `StoredEvent.event_kind`
return None for an unknown kind instead of refusing the row.

That section is the reason the page exists. It is what answers "it interrupted
me too often" with evidence — how often Ocura held a break back and why — so it
gets a card of its own at the foot of the column, a sentence explaining itself,
and a proportional bar per reason. `CHART_HEIGHT` is set so that all of it fits
above the fold in a default-sized window rather than being chosen by eye.

### What the statistics page refuses to show

No streaks. No goals. Nothing "missed" and nothing "achieved". No percentage of
breaks taken against a target, because there is no target. No colour that sorts
days into good and bad — there is one bar colour, and today's column is drawn
in the accent for the same reason the sidebar marks the current section, which
is a statement about which day is now and not about how the day went.

The moment a number has a score attached, the rational thing to do with it is
to game it, and a break taken to keep a number up is not a break.

The rule is enforced rather than remembered. `ACCUSATORY_WORDS` lives in
`tests/unit/conftest.py` and is shared by the dashboard's
`test_no_event_text_is_accusatory` and the statistics page's: a rule checked on
one screen and not the other is a rule the next screen quietly breaks.

### The chart

Qt, not a charting library. A dependency for one bar chart is a dependency to
package, license, audit and carry into every build, in exchange for a rounded
rectangle. What it costs instead is `Bar`, a `QWidget` that fills a fraction of
itself — vertically for a day column, horizontally for a deferral row.

Its colour comes from the token set the same way the break overlay's shape
does: QSS sets `color` on the object name and `paintEvent` reads it back off
the palette, so no colour is written in Python and a theme is still only
`style.qss` plus `theme.py`. `chart_bar` is a token of its own rather than a
border or a surface reused, because bars are a measurement and retuning the
chrome should not silently retune them.

Two things here are asserted against pixels rather than against wiring. A bar
drawn along the wrong axis passes every test that only reads its fraction back
— which is how the deferral rows first shipped all the same length — so the
tests render a bar and count the pixels it actually painted, in the colour it
actually resolved to.

### WAL, read back rather than requested

`PRAGMA journal_mode = WAL` **returns the mode SQLite settled on** instead of
failing when it cannot honour the request, which a network share will do. The
result is read back and a warning logged if it is not `wal`, and
`synchronous = NORMAL` is applied only in that case — safe under WAL, where a
power cut can cost the last transaction but never the integrity of the file.

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

## Tooling gotchas

Each of these cost real time and none is guessable from the documentation. They
are written down because remembering them has already failed.

Three of them appear again under [Verification discipline](#verification-discipline),
where they are the evidence for the rule rather than the trap to avoid. The
entries here are the operational form: what to do instead, next time.

**A child `.ruff.toml` replaces a table, it does not merge it.**
`src/ocura/ui/.ruff.toml` and `src/ocura/domain/.ruff.toml` both restate bans
that `pyproject.toml` already declares. Dropping a line by "tidying up" does not
inherit it — it removes it. The first version of the domain config silently made
the domain the one layer where importing Qt was allowed.

**`pytest_collection_modifyitems` in a subdirectory conftest receives the whole
collection.** `tests/gui/conftest.py` marks tests `gui`, and the first version
marked *every* test in the run, so `-m "not gui"` deselected all 216. The hook
must filter by path.

**Read build output, do not grep it.** A release build was failing on
`PermissionError: dist\Ocura` — a running `Ocura.exe` holding the folder — for
two runs while a `| grep` over its output hid the failure, so the icon under
investigation was being extracted from a stale binary from the previous day.
`build_release.py` now reports that case in one sentence, but the habit is the
fix: pipe to `tail`, never to `grep`, when the question is "did this work".

**`QWidget.grab()` cannot show a compositing fault.** It re-renders the widget
directly, so screenshots taken that way looked correct for the entire life of
the overlapping-label defect. Capturing the actual screen with
`QGuiApplication.primaryScreen().grabWindow(0)` reproduced it immediately.

**Reduced motion hides the composition you are trying to photograph.** A
capture of the overlay taken with motion off shows the focus shape at
`SHAPE_MIN_SCALE` — its *receded* size, a third of what the break opens with —
because that is what the reduced-motion branch applies immediately. Two rounds
of retuning went into a shape that was never the wrong size. Capture the break
screen with motion **on**, timed a beat after the entry fade.

**Microsoft Store Python redirects `%LOCALAPPDATA%` and says nothing.** A
`.venv` built on the Store build of Python 3.13 runs inside the MSIX package
sandbox, so a write to `C:\Users\<name>\AppData\Local\Ocura\ocura.db` actually
lands in
`...\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_*\LocalCache\Local\Ocura\`.
The redirection is invisible from inside that process: `Path.exists()` returns
True for the path that was asked for, `PRAGMA database_list` reports that same
path back, and a log line saying where the database is can only ever repeat
what it was told. The first end-to-end run of P4 therefore looked like a silent
write failure and was not one. Only a look at the filesystem from **outside**
the process settles where a file went. The packaged PyInstaller build is not
redirected — measured with `Ocura.exe --self-check`, which reported a separate,
empty database at the real location while the venv's copy held four rows.

**`git add -A` sweeps in whatever else is in the tree.** It has put unrelated
work into the wrong commit twice: the presenter into
`feat: add user-initiated break command`, and the overlay geometry into
`feat: add pre-break toast warning`. Neither was recoverable without rewriting
pushed history. Stage explicit paths, always — `git add <paths>`, never `-A`
or `.`, when a commit is meant to say one thing.

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
