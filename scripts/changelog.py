"""Release notes for a tag, generated from the commits since the previous one.

    python scripts/changelog.py vX.Y.Z --output release-notes.md

Called by .github/workflows/release.yml, and runnable by hand to see what a
release would say before tagging anything.

**Why this is a script and not twenty lines inside the workflow.** A step that
only ever runs on a tag push is a step nobody can try out: the first time it
runs is the first release, and a mistake in it is a mistake in something
already public. As a script it can be run against any tag, on any machine,
before the tag exists — which is the difference between a pipeline that was
tested and one that merely has not failed yet.

Commits are grouped by the conventional-commit prefix the history already
uses (`feat:`, `fix:`, `build:` ...). Anything unprefixed still appears, under
"Other": a changelog that silently drops commits is worse than an untidy one,
because the reader has no way to tell the difference between "nothing else
changed" and "the generator did not understand it".
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Conventional-commit prefixes, in the order a reader cares about them. What
#: the user got comes before how it was built; the housekeeping comes last.
GROUPS: dict[str, str] = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "build": "Build and packaging",
    "docs": "Documentation",
    "refactor": "Refactoring",
    "test": "Tests",
    "style": "Style",
    "ci": "Continuous integration",
    "chore": "Housekeeping",
}

OTHER = "Other"

#: Said on the release page rather than only in the read-me, because this is
#: the page somebody is looking at in the moment the warning appears. A user
#: who has been told what "unknown publisher" means is not alarmed by it.
INSTALL_NOTES = """---

### Installing

Download **Ocura-{version}-Setup.exe** below and run it. It installs for your
user only and never asks for an administrator.

**Windows will warn you.** Ocura is not code-signed, so SmartScreen shows
*Windows protected your PC*. Choose **More info**, then **Run anyway**. That
warning means only that the publisher has not paid for a certificate — it is
not a report about this file. The source is public and you can build it
yourself.

Uninstalling leaves your history and settings where they are, unless you tick
the box that asks for them to be removed too.

No account, no cloud, no telemetry. Nothing leaves your machine."""


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )


def previous_tag(tag: str) -> str | None:
    """The tag before this one, or None if this is the first release.

    `git describe` is asked about the tag's *parent*, so that the tag being
    released is not its own answer.
    """
    found = git("describe", "--tags", "--abbrev=0", f"{tag}^")
    return found.stdout.strip() or None if found.returncode == 0 else None


def commits(revision_range: str) -> list[tuple[str, str]]:
    """`(hash, subject)` for each commit in the range, newest first.

    Merges are left out: a merge commit's subject describes the branch
    operation, not anything that changed for a user.
    """
    #: A unit separator, because a commit subject may contain anything a
    #: person can type — including whatever character seemed safe as a
    #: delimiter. This one they cannot type.
    found = git("log", "--no-merges", "--pretty=format:%h\x1f%s", revision_range)
    if found.returncode != 0:
        raise SystemExit(f"git log {revision_range} failed:\n{found.stderr.strip()}")

    parsed: list[tuple[str, str]] = []
    for line in found.stdout.splitlines():
        if not line.strip():
            continue
        commit_hash, _, subject = line.partition("\x1f")
        parsed.append((commit_hash, subject.strip()))
    return parsed


def grouped(entries: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Commits filed under their conventional-commit heading.

    The prefix is taken only when it is one this project uses. `fix: stop the
    dashboard squeezing` is a Fix; `see also: the roadmap` is not a commit type
    and keeps its whole subject under Other, rather than being filed as a
    category called "see also".
    """
    buckets: dict[str, list[str]] = {}
    for commit_hash, subject in entries:
        prefix, separator, rest = subject.partition(":")
        # `feat(ui): ...` is the same type as `feat: ...`.
        kind = prefix.split("(", 1)[0].strip().lower()
        if separator and kind in GROUPS:
            heading, text = GROUPS[kind], rest.strip()
        else:
            heading, text = OTHER, subject
        buckets.setdefault(heading, []).append(f"- {text} ({commit_hash})")
    return buckets


def render(tag: str, version: str, repository: str | None = None) -> str:
    """The whole release body."""
    earlier = previous_tag(tag)
    entries = commits(f"{earlier}..{tag}" if earlier else tag)
    buckets = grouped(entries)

    lines = ["## What changed", ""]
    if not entries:
        # Honest rather than empty. A release with no commits behind it is
        # almost certainly a retag, and saying so beats a blank heading.
        lines += ["Nothing since the previous tag.", ""]

    for heading in [*GROUPS.values(), OTHER]:
        if heading not in buckets:
            continue
        lines += [f"### {heading}", "", *buckets[heading], ""]

    if earlier and repository:
        lines += [
            f"**Full diff:** https://github.com/{repository}/compare/{earlier}...{tag}",
            "",
        ]

    lines.append(INSTALL_NOTES.format(version=version))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="the tag being released, in the form vX.Y.Z")
    parser.add_argument(
        "--version",
        help="the version to name in the install notes (default: the tag without its v)",
    )
    parser.add_argument("--repository", help="owner/name, for the compare link")
    parser.add_argument("--output", type=Path, help="write here instead of to standard output")
    arguments = parser.parse_args(argv)

    # A redirected stdout on Windows gets the ANSI code page, not UTF-8 — and
    # a CI log is always redirected. The fixed text below survives cp1252, but
    # commit subjects are arbitrary: this repository has commits about Arabic
    # translation, and one subject containing the word itself would end the
    # release on a UnicodeEncodeError raised while printing. `replace` keeps
    # the mangling in the log, where it is cosmetic, rather than in the file,
    # which is written as UTF-8 regardless.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    version = arguments.version or arguments.tag.lstrip("v")
    notes = render(arguments.tag, version, arguments.repository)

    if arguments.output:
        arguments.output.write_text(notes, encoding="utf-8")
        print(f"wrote {arguments.output}")
    # Printed either way: the workflow log is where somebody looks to find out
    # what a release said without downloading anything.
    print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
