# Roadmap

**Design principle: Ocura must earn the right to interrupt.** Every feature is
judged by whether it improves the quality of the interruption decision. A
feature that adds noise without improving that decision does not ship, however
easy it would be to build.

## P0 — Domain core (done)

Break state machine, monotonic and calendar clock abstractions, schedule
validation, deferral and satisfaction as distinct outcomes, deterministic tests,
CI.

## P1 — Windows context layer

The signals that make an interruption well-timed:

- idle detection
- session lock and unlock
- full screen and display state

All behind an extensible `ContextDetector` abstraction, so detectors can be
added, replaced, or disabled without touching the state machine. P0 already
defines what a detector is allowed to say: `Interruptible`, `Deferral`, or
`RestSatisfied`.

Call detection is deliberately deferred. There is no reliable, privacy-respecting
way to know a user is on a call across every conferencing app, and a detector
that is wrong half the time makes the interruption decision worse, not better.
It waits until there is a method worth trusting.

## P2 — Application shell

Tray icon, main window, navigation. The visible surface, with the domain
already finished behind it.

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
