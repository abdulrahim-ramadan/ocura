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

## P3 — Break experience

Overlay across all monitors, countdown, skip, snooze, notifications. Snooze is
capped at two — beyond that the reminder has stopped being a reminder, and
nagging is not a feature.

## P4 — Persistence

SQLite: sessions, settings, daily metrics.

**No user identifier in the schema, ever.** Not a UUID, not a machine ID, not a
hashed one. This is a permanent architectural constraint, not a default to be
revisited: data that cannot identify anyone cannot leak anyone.

## P5 — Onboarding and settings

First-run setup and full configuration of schedules and detectors.

## P6 — Visual polish

Animations, typography, accessibility, dark and light themes.

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

## Explicitly out of scope

**Streaks and gamification.** A streak turns a missed break into a failure, and
guilt is the opposite of what a calm tool should produce.

**Accounts and cloud sync.** Nothing here is worth an account, and the moment
data leaves the machine, "privacy-first" becomes a claim rather than a fact.

**Camera-based posture tracking.** Pointing a camera at the user is a
disproportionate price for a marginally better break decision, and it
contradicts the local-first promise.
