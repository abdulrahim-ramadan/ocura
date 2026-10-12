# Roadmap

**Design principle: Ocura must earn the right to interrupt.** Every feature is
judged by whether it improves the quality of the interruption decision. A
feature that adds noise without improving that decision does not ship, however
easy it would be to build.

## P0 — Domain core (done)

Break state machine, monotonic and calendar clock abstractions, schedule
validation, deferral and satisfaction as distinct outcomes, deterministic tests,
CI.

## P1 — Windows context layer (complete)

The signals that make an interruption well-timed:

- idle detection (`GetLastInputInfo`)
- session lock and unlock (`WTSQuerySessionInformationW`)
- fullscreen, presentation mode and Focus Assist (`SHQueryUserNotificationState`)
- screensaver state (`SPI_GETSCREENSAVERRUNNING`)

All behind an extensible `ContextDetector` abstraction, so detectors can be
added, replaced, or disabled without touching the state machine. P0 already
defines what a detector is allowed to say: `Interruptible`, `Deferral`, or
`RestSatisfied`.

Rest observed before a break is owed is carried as expiring credit by the
detector itself, in `infrastructure/`, and reported at the first tick where a
break becomes owed. The design and its constraints — consumed once, 30-minute
staleness window — are specified in
[architecture.md](architecture.md#rest-taken-before-a-break-is-owed). The domain
does not change.

**Verified on real hardware**, not only in tests:

- **Lock detection** via `WTSQuerySessionInformationW`. The first implementation
  used `OpenInputDesktop`, which lagged a real lock by 27 seconds and, worse,
  oscillated mid-lock; both measurements are in
  [architecture.md](architecture.md#verified-against-the-real-api).
- **Rest credit end to end**: locked, accumulated, held across 17 ticks in
  `DEFERRED`, discharged the owed break on unlock with focus resetting to zero.
- **Fullscreen detection** via `SHQueryUserNotificationState`: F11 reported
  `BUSY`, while a maximized window correctly did not.
- **Known limitation**: fullscreen on a non-primary display is not detected.
  Carried to P6 below rather than papered over.

Call detection is deliberately deferred. There is no reliable, privacy-respecting
way to know a user is on a call across every conferencing app, and a detector
that is wrong half the time makes the interruption decision worse, not better.
It waits until there is a method worth trusting.

## P2 — Application shell (complete)

Tray icon, main window, navigation, and a live dashboard. The visible surface,
with the domain already finished behind it.

The Qt boundary is described in
[architecture.md](architecture.md#the-qt-boundary): widgets read an immutable
`SessionView` from `BreakPresenter` and never touch the engine, the presenter
owns the tick while Qt only delivers the pulse, and one QSS template built from
tokens carries both themes so P6 can restyle without touching a widget.

Statistics and Settings are navigable and honestly empty — they say what is
coming and when, rather than showing invented data.

## P3 — Break experience (complete)

Overlay across all monitors, countdown, skip, snooze, and a pre-break warning.
Snooze is capped at two — beyond that the reminder has stopped being a reminder,
and nagging is not a feature. The design and its guarantees are in
[architecture.md](architecture.md#the-break-experience).

**Ocura draws its own pre-break toast; it does not use OS notifications.**
Measured on the development machine, `QSystemTrayIcon.supportsMessages()`
returns **False**, so balloon notifications are simply unavailable there — and a
capability that varies silently by machine is the wrong foundation for the one
message that has to arrive before a break. A small always-on-top window Ocura
draws itself works everywhere, is styled from the same tokens as the rest of the
app, and can be tested without a notification service.

Two conditions on it, decided now rather than discovered later:

- **It must not take focus.** `Qt::WindowDoesNotAcceptFocus` and
  `WA_ShowWithoutActivating`, no activation, no keyboard steal. A toast that
  interrupts typing is worse than the notification it replaced.
- **It does not inherit Focus Assist for free.** An OS notification would be
  suppressed during Do Not Disturb; a self-drawn window would not. Ocura is
  covered because `PresentationDetector` already consults
  `SHQueryUserNotificationState` — which reports `QUNS_QUIET_TIME` and the
  fullscreen states — and defers the break before any toast is considered.
  That suppression lives in the detector layer, so removing or weakening the
  detector would silently make the toast rude.

**The guided blink cue and the receding focus shape live here, not on the
dashboard.** Both were considered for the P2 dashboard and rejected: peripheral
motion pulls the eye involuntarily, so a permanently animating element on a
glance surface interrupts the user without asking, which is what the product
exists to prevent. On the break screen the same motion is purposeful and bounded
to the twenty seconds of the break — the user has already agreed to look away,
and the animation is the instruction rather than decoration. Recorded so it is
not relitigated as a dashboard feature. See the motion policy in
[architecture.md](architecture.md#motion-policy).

## P4 — Persistence (in progress)

SQLite: sessions, settings, daily metrics.

**No user identifier in the schema, ever.** Not a UUID, not a machine ID, not a
hashed one. This is a permanent architectural constraint, not a default to be
revisited: data that cannot identify anyone cannot leak anyone. It is enforced
by a test that reads the real `PRAGMA table_info` of a migrated database rather
than the DDL that was meant to produce it.

**Stage 1 — the event log (done).** One SQLite file at
`%LOCALAPPDATA%\Ocura\ocura.db`, a versioned schema with an all-or-nothing
migration path, and every `SessionEvent` written to it as the application runs.
The seam is `SessionJournal`, a one-method protocol in the application layer,
so nothing above `ocura.infrastructure.storage` knows a database exists — and
`sqlite3` is now banned in the application layer too. Persistence is
best-effort by design: a disk that cannot be written costs the user their
history and never their break. See
[architecture.md](architecture.md#p4--local-history).

Every break event is told apart rather than flattened: offered, begun by the
engine, begun by the user, run to its end, ended early, postponed by a detector,
postponed by the user, and discharged by a rest already taken. Each row carries
the detector's reason where there was one and the span of time it is about where
one applies — nullable, because a break of no length and an event that was never
about length are different rows.

Verified end to end, not only by tests: the real application, on the real
default schedule, took a real twenty-second break, and the four rows it wrote
were read back out of the file by a separate process. Repeated for the v2
schema, on the same file: the v1 database left behind by that first run was
upgraded in place, its four rows survived with NULL durations, and the break
taken afterwards recorded a duration of 20.0.

**Stage 2 — the statistics page (done).** Today and the last seven days, read
from the Stage 1 log: time at the screen per day, breaks taken, the average
focus block, and — given the most weight on the page — every time Ocura held a
break back, counted by why. That last section is the one that answers "it
interrupted me too often" with evidence rather than with an opinion.

Informational only, and enforced as such: no streaks, no goals, nothing
"missed", no percentage "achieved", and no colour that sorts days into good and
bad. The language rule is a shared word list that the dashboard's test and this
page's test both run against. A first week with nothing in it says so plainly
and says when there will be something, rather than drawing an empty chart. The
week chart is painted with Qt — no charting dependency for one bar chart — and
takes its colours from the tokens in both themes.

Verified by looking at it, not only by tests: rendered over a seeded database
at the default window size in both themes, which is how the deferral bars were
found to be drawing along the wrong axis and reading as equal lengths whatever
their counts were.

P4 is done. The settings that were going to be its third stage moved to P5,
where they belong beside the first-run screens that set them; the daily metrics
that were going to be a stage of their own are counted over the event log on
demand, so there was no rollup left to build.

## P5 — Onboarding and settings (done)

**Settings.** Break interval, break length, warning lead time, idle threshold,
theme, break-screen evidence, and autostart. They live in the `settings` table
beside the history, which is the move `shell/theme` was parked in the shell
namespace to make easy. Window geometry stays in the shell namespace: a setting
is something the user chose and would be annoyed to lose, geometry is where a
window happened to be.

Validation refuses and never repairs. Nothing the user typed is clamped, a
refused value keeps its place in the box, and the message says what is wrong in
the terms they set it in. Changes reach the running session at once, and a
change to the interval keeps the focus time already accrued — shortening it
below what has passed makes a break due on the next tick, which is the honest
answer rather than a glitch.

Autostart is the per-user Run key, and the registry rather than the setting is
what the checkbox shows, because the registry is what actually runs at sign-in.

**First run.** Three screens: what Ocura does and that it makes no medical
claims, a rhythm with the 20-20-20 origin sourced from
[EVIDENCE.md](EVIDENCE.md), and whether to start with Windows, asked rather
than assumed. Then it gets out of the way. No splash screen — an artificial
delay to look professional contradicts a product built on respecting the user's
time. `--first-run` shows it again, for testing; there is no button for it.

Verified end to end on a real database: a legacy `shell/theme` moved out and
its key removed, three screens answered, a 45-minute rhythm written to the file
at schema v3, and no dialog on the second launch.

## P6 — Visual polish

Animations, typography, accessibility, dark and light themes.

**Languages (done).** Arabic, German and English, through Qt Linguist, with
English as the source language and no catalogue of its own. The language is
chosen in Settings, defaults to following Windows, and falls back to English
for anything unsupported. **The switch is live** — no restart, and that was
checked rather than claimed: installing a translator makes Qt re-ask every
widget for its strings, and everything else on screen is rendered from a
presenter on the next tick.

Every user-facing string is externalised, and a test walks the AST of the
source to keep it that way — three rules now, because the first one only saw
literals handed to Qt's own text setters, and the defects that actually
survived the first pass went in by other routes. They are listed in
[architecture.md](architecture.md#what-the-translation-pass-found).

**Arabic means the whole interface turns round**, not a font change. Qt
mirrors layouts, alignment and text direction from one property on the
application; what it does not mirror is a stylesheet, a paint event, or
`text-align` — which it mirrors *twice* if you help it. The three exceptions
and the break overlay's rule, that the text block mirrors while the focus
shape stays centred, are in
[architecture.md](architecture.md#arabic-turns-the-interface-round).

German is the longest of the three and clipped three surfaces; each is fixed
structurally rather than by padding a number, and the list is in
[architecture.md](architecture.md#german-is-longer-and-it-clipped-three-things).

**Icon redesign.** The P2 icon is a placeholder generated by
`scripts/make_icon.py` — a ring, a core, a gap and an edge. Four competing
elements do not survive 16px, and in the title bar it reads as an indistinct
green blob. A real mark needs to be designed at 16px first and scaled up, not
drawn large and shrunk. Deliberately not attempted in P2, which had no business
inventing a visual identity.

**Open question: detecting fullscreen on non-primary displays.**
`SHQueryUserNotificationState` watches the primary display only — measured, a
window covering a secondary monitor exactly still reports
`ACCEPTS_NOTIFICATIONS`, so a fullscreen video on a second screen is not
detected. This needs a method that does not rely on window geometry; falling
back to rectangle comparison reintroduces the maximized-window defect. See
[architecture.md](architecture.md#known-limitation-fullscreen-on-a-non-primary-display).

Also flagged for here: "idle **and** the foreground window has not changed for
N minutes" as a reading discriminator, which would make long idle with a
*changed* window creditable rest.

## P7 — Packaging

Windows installer, code signing, GitHub Releases.

## After the first release

**An ubuntu CI job running the domain tests only**, as execution-level proof
of the layer boundary. The point is not Linux support. The docs claim the
domain layer runs without Windows; the banned-api rule in
`src/ocura/domain/.ruff.toml` prevents the import, and running the domain
tests on a machine with no Windows would prove it by execution. Deliberately
its own change after the release, not an untested commit ahead of a tag.

## Explicitly out of scope

**Streaks and gamification.** A streak turns a missed break into a failure, and
guilt is the opposite of what a calm tool should produce.

**Accounts and cloud sync.** Nothing here is worth an account, and the moment
data leaves the machine, "privacy-first" becomes a claim rather than a fact.

**Camera-based posture tracking.** Pointing a camera at the user is a
disproportionate price for a marginally better break decision, and it
contradicts the local-first promise.
