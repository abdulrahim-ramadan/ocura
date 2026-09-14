"""Build a trial release in one command.

    .venv\\Scripts\\python.exe scripts\\build_release.py

Refuses to build if ruff or pytest fail. A build handed to someone else is the
worst possible place to discover a broken test, and the gate costs five seconds.

Assembly lives here rather than in the spec so there is one implementation of
"what a handover folder contains". PyInstaller produces the executable and its
dependencies; everything else — licences, the read-me — is added afterwards.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "ocura.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
HANDOVER = DIST / "Ocura"

PYTHON = Path(sys.executable)
SCRIPTS = PYTHON.parent

LICENCES = ("LGPL-3.0.txt", "GPL-3.0.txt", "THIRD_PARTY_NOTICES.md")

READ_ME = """Ocura — trial build

Run Ocura.exe. It lives in the system tray; closing the window hides it there,
and Quit is in the tray menu.

Windows will warn that the publisher is unknown, because this build is not
code-signed. Choose More info, then Run anyway, or delete the folder if you
would rather not.

If it does not start, open a terminal in this folder and run:
    Ocura.exe --self-check > selfcheck.txt
then send selfcheck.txt.

Licences for Ocura and for the Qt libraries it uses are in licenses\\.
"""

#: Everything a handover folder must contain. Checked after assembly, so a
#: silent packaging change cannot ship an incomplete folder.
EXPECTED = (
    "Ocura.exe",
    "READ ME FIRST.txt",
    "licenses/LICENSE",
    "licenses/LGPL-3.0.txt",
    "licenses/GPL-3.0.txt",
    "licenses/THIRD_PARTY_NOTICES.md",
    "_internal/ocura/ui/style.qss",
    "_internal/ocura/ui/assets/ocura.png",
    "_internal/ocura/ui/assets/ocura.ico",
)


def run(label: str, command: list[str]) -> None:
    print(f"\n>>> {label}")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"\n{label} failed ({result.returncode}). Nothing was built.")


def gate() -> None:
    """Lint and tests, before anything is packaged."""
    run("ruff check", [str(SCRIPTS / "ruff.exe"), "check", "."])
    run("ruff format --check", [str(SCRIPTS / "ruff.exe"), "format", "--check", "."])
    run("pytest", [str(PYTHON), "-m", "pytest", "-q"])


def build() -> None:
    for stale in (DIST, BUILD):
        shutil.rmtree(stale, ignore_errors=True)
    run(
        "pyinstaller",
        [
            str(SCRIPTS / "pyinstaller.exe"),
            str(SPEC),
            "--noconfirm",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
        ],
    )


def assemble() -> None:
    print("\n>>> assembling the handover folder")
    licences = HANDOVER / "licenses"
    licences.mkdir(parents=True, exist_ok=True)

    # Ocura's own terms travel with the binary, not only with the repository.
    shutil.copy2(ROOT / "LICENSE", licences / "LICENSE")
    for name in LICENCES:
        shutil.copy2(ROOT / "licenses" / name, licences / name)

    (HANDOVER / "READ ME FIRST.txt").write_text(READ_ME, encoding="utf-8")


def verify() -> None:
    print("\n>>> verifying the handover folder")
    missing = [name for name in EXPECTED if not (HANDOVER / name).exists()]
    if missing:
        raise SystemExit("incomplete handover folder, missing:\n  " + "\n  ".join(missing))

    check = subprocess.run(
        [str(HANDOVER / "Ocura.exe"), "--self-check"], capture_output=True, text=True, timeout=120
    )
    print(check.stdout.strip())
    if check.returncode != 0 or "MISSING" in check.stdout or "BROKEN" in check.stdout:
        raise SystemExit("the built executable could not resolve its own resources")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="build without running ruff and pytest first (not for anything handed over)",
    )
    args = parser.parse_args()

    started = time.monotonic()
    if args.skip_checks:
        print("!!! skipping ruff and pytest — do not hand this build to anyone")
    else:
        gate()

    build()
    assemble()
    verify()

    size = sum(f.stat().st_size for f in HANDOVER.rglob("*") if f.is_file())
    print(f"\nBuilt in {time.monotonic() - started:.0f}s, {size / 1_000_000:.0f} MB")
    print(f"\n    {HANDOVER}\n")
    print("Hand over the whole folder. Ocura.exe alone will not run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
