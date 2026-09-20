# Evidence

Every claim Ocura puts on a screen is listed here with who makes it and how
strong it is. A claim about someone's eyes that cannot be traced back to anyone
is not worth showing, and this file is where the tracing lives.

**Ocura is not a medical device.** It does not diagnose, treat or prevent
anything, and nothing below is medical advice. What follows is public guidance
from professional bodies, reported as guidance.

**On the strength of it.** The guidance here is widely recommended and
sparsely trialled. It is advice from the people who look at eyes for a living,
not a settled result from large randomised trials, and a few small studies have
found the benefit modest or inconsistent. Ocura is built on it anyway, because
the cost of following it is twenty seconds and the cost of being wrong about it
is nothing — but the product does not claim more for it than that, and neither
should any screen in it.

---

## The 20-20-20 guideline

> Every 20 minutes, look at something 20 feet away for 20 seconds.

**Who says so.** The American Academy of Ophthalmology and the American
Optometric Association both recommend it for people working at screens. It is
generally attributed to the optometrist Jeffrey Anshel, who proposed the rule
as a memorable rhythm rather than as a trial result — the three twenties are
chosen to be rememberable, not measured.

**Where Ocura uses it.**

- `DEFAULT_SCHEDULE` — twenty minutes of focus, twenty seconds of break.
- The first-run rhythm screen, which explains where the number comes from.
- `BREAK_TIPS[0]`, on the break screen.

**Why Ocura offers 30 and 45 minutes as well.** A guideline nobody follows
helps nobody. Someone who will accept a break every forty-five minutes is
better served than someone who turns the reminders off at lunchtime, and the
product would rather be used at a rhythm its user keeps than ignored at the
recommended one.

## Accommodation and distance focus

> Close work holds the lens under tension; looking into the distance is what
> lets it relax.

**Who says so.** The American Optometric Association, describing the
accommodative effort of sustained near work and what relieves it. This is the
mechanism behind the "20 feet" in the guideline above: at roughly six metres
the eye is close enough to relaxed focus that the effort of accommodation
stops.

**Where Ocura uses it.** `BREAK_TIPS[1]`, and the break screen's instruction to
look at something far away.

## Blink rate at a screen

> Blink rate falls by about half at a screen, which is what leaves eyes dry.

**Who says so.** The American Optometric Association, in its guidance on
computer vision syndrome. Reported reductions vary by study and by task; "about
half" is the round figure the AOA and others use, and Ocura says "about" for
that reason.

**Where Ocura uses it.** `BREAK_TIPS[2]`, and the closing-eyelid cue on the
break screen — the cue is a prompt to blink, which is the part of the guidance
a static instruction does not deliver.

---

## Rules for adding to this file

1. **Name who makes the claim.** "Studies show" is not an attribution.
2. **Say how strong it is.** Guidance, consensus and trial result are three
   different things and the file says which.
3. **Link it to where it appears**, so a claim cannot be changed on a screen
   without this file disagreeing.
4. **No medical claims.** If a sentence would only be true of a medical device,
   it does not go on a screen.
