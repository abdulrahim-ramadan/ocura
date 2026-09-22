"""The version number has one home, and this is what keeps it there.

`src/ocura/__init__.py` promises that the number is written once and read by
everything that needs it: the wheel metadata through hatchling, the
executable's file properties through the PyInstaller spec, the installer
through a command-line define, the Settings page through an import, and the
release workflow, which refuses to build if the tag disagrees.

A promise like that decays quietly. The second copy is always added in good
faith — in a usage line, a default, an example — and it is not wrong on the
day it is written. It is wrong on the day the first copy is bumped and nobody
remembers the second, and by then the executable, the download page and the
about-line are three different numbers.

So the rule here is blunt on purpose: **the current version, as a literal, may
appear in exactly one file in the repository.** Documentation that has to show
a version writes `vX.Y.Z` instead of a real one, which is why the usage lines
in `scripts/changelog.py` and the comment at the head of
`.github/workflows/release.yml` read the way they do. They are placeholders
deliberately; replacing one with a real number is what this test is for.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

import ocura

ROOT = Path(__file__).resolve().parents[2]
VERSION_SOURCE = ROOT / "src" / "ocura" / "__init__.py"

#: The expression every text-reading consumer of the version uses: the
#: PyInstaller spec, `scripts/build_release.py` and the tag check in the
#: release workflow all extract the number with this rather than importing the
#: package. Written out once here so that a change to the assignment's shape —
#: single quotes, a computed value, a tuple — fails in the suite instead of
#: during a release.
ASSIGNMENT = re.compile(r'__version__ = "([^"]+)"')

#: Read by suffix rather than sniffed, because the question is not "does this
#: decode" but "is a version number in here something a person wrote".
BINARY_SUFFIXES = frozenset({".db", ".ico", ".png", ".qm"})


def repository_files() -> list[Path]:
    """Every file in the repository, including ones not committed yet.

    `--others --exclude-standard` is what makes this test worth running before
    a commit rather than after one: work in progress is exactly where a second
    copy of the version gets written, and a check that only saw tracked files
    would start passing again at the moment it stopped mattering.
    """
    found = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if found.returncode != 0:
        # Not skipped. This test is a claim about the repository, and a
        # repository it cannot read is a claim it cannot make.
        pytest.fail(f"git ls-files failed in {ROOT}:\n{found.stderr.strip()}")
    return [ROOT / name for name in found.stdout.split("\0") if name]


def test_the_version_is_three_whole_numbers() -> None:
    """Windows wants integers, and the spec turns this string into four.

    `packaging/ocura.spec` builds `FILE_VERSION` by calling `int()` on each
    part. A release-candidate suffix is legal to PyPI and fatal here: it fails
    inside PyInstaller, several minutes into a release, with a ValueError
    about a string.
    """
    assert re.fullmatch(r"\d+\.\d+\.\d+", ocura.__version__), (
        f"__version__ is {ocura.__version__!r}; the packaging path needs three"
        " whole numbers, because Windows file properties are integers"
    )


def test_reading_the_file_and_importing_the_package_agree() -> None:
    """The two routes to the number must not be able to disagree.

    Everything inside the application imports it; everything that packages the
    application greps for it, because packaging must not depend on `ocura`
    being importable in the environment doing the packaging. This is the test
    that the two answers are the same answer.
    """
    source = VERSION_SOURCE.read_text(encoding="utf-8")
    found = ASSIGNMENT.search(source)
    assert found is not None, f"nothing matching {ASSIGNMENT.pattern} in {VERSION_SOURCE}"
    assert found.group(1) == ocura.__version__
    assert len(ASSIGNMENT.findall(source)) == 1, "two assignments in the one file that holds it"


def test_the_number_is_written_in_exactly_one_file() -> None:
    """No second copy anywhere in the repository. See this module's docstring."""
    # Bounded by digits and dots on both sides, so the number is not found
    # inside a longer one that merely contains it — a build number with a
    # fourth part, or a major version that starts with the same digits. A
    # leading `v` is deliberately not excluded: a tag written out in a
    # document is exactly the kind of copy this is looking for.
    literal = re.compile(rf"(?<![\d.]){re.escape(ocura.__version__)}(?![\d.])")

    holders = []
    for path in repository_files():
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if literal.search(text):
            holders.append(path.relative_to(ROOT).as_posix())

    expected = [VERSION_SOURCE.relative_to(ROOT).as_posix()]
    assert sorted(holders) == expected, (
        f"the version {ocura.__version__} is written in more than one place:\n  "
        + "\n  ".join(sorted(holders))
        + f"\n\nIt belongs only in {expected[0]}. Anything that needs it at run time"
        " imports it; anything that needs it while packaging reads it out of that"
        " file; anything documenting it writes vX.Y.Z."
    )


def test_the_wheel_takes_its_version_from_that_file() -> None:
    """hatchling is told where the number lives instead of being handed it."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in project["project"].get("dynamic", []), (
        "pyproject declares a static version; it should declare dynamic = ['version']"
    )
    assert "version" not in project["project"]
    assert project["tool"]["hatch"]["version"]["path"] == "src/ocura/__init__.py"


def test_the_packaging_path_reads_the_version_rather_than_repeating_it() -> None:
    """Each step of a release gets the number from the source, or refuses to run.

    Stated as four separate expectations rather than one, because a release
    that fails should say which link in the chain stopped reading and started
    remembering.
    """

    def read(*parts: str) -> str:
        return ROOT.joinpath(*parts).read_text(encoding="utf-8")

    assert ASSIGNMENT.pattern in read("packaging", "ocura.spec"), (
        "the PyInstaller spec no longer reads the version out of the source"
    )
    assert ASSIGNMENT.pattern in read("scripts", "build_release.py"), (
        "the build script no longer reads the version out of the source"
    )
    assert ASSIGNMENT.pattern in read(".github", "workflows", "release.yml"), (
        "the release workflow no longer checks the tag against the source"
    )

    # The installer is the one that cannot read the file itself: ISCC is given
    # the number on its command line. So its guarantee is the opposite shape —
    # it refuses to compile at all if nobody supplied one, which is what keeps
    # a default from being quietly added to the script later.
    installer = read("packaging", "ocura.iss")
    assert "#ifndef AppVersion" in installer and "#error" in installer, (
        "ocura.iss must refuse to compile without /DAppVersion rather than"
        " carrying a version of its own"
    )
