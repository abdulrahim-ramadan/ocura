"""Build a trial release in one command.

    .venv\\Scripts\\python.exe scripts\\build_release.py
    .venv\\Scripts\\python.exe scripts\\build_release.py --installer

Refuses to build if ruff or pytest fail. A build handed to someone else is the
worst possible place to discover a broken test, and the gate costs five seconds.

Assembly lives here rather than in the spec so there is one implementation of
"what a handover folder contains". PyInstaller produces the executable and its
dependencies; everything else — licences, the read-me — is added afterwards.

`--installer` compiles `packaging\\ocura.iss` over the folder that was just
built and leaves `dist\\Ocura-<version>-Setup.exe` beside it. It is a flag
rather than the default because the handover folder is what a developer wants
twenty times a day and the installer is what a release wants once: the compile
costs another half-minute, and needing Inno Setup on the machine should not be
the price of building the application.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "ocura.spec"
ISS = ROOT / "packaging" / "ocura.iss"
VERSION_SOURCE = ROOT / "src" / "ocura" / "__init__.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
HANDOVER = DIST / "Ocura"

#: An installer smaller than this did not manage to pack Qt, which is most of
#: what is in it. That is the shape a compile leaves behind when it half-fails
#: and still exits zero, and the alternative to checking here is finding out
#: when somebody runs the download.
MINIMUM_INSTALLER_MB = 20

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
    "_internal/ocura/ui/assets/ocura-fallback.ico",
)

ASSETS = ROOT / "src" / "ocura" / "ui" / "assets"


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


def check_icon() -> None:
    """Refuse to ship a build whose executable icon is the drawn placeholder.

    The .ico is what Windows puts on the executable, the taskbar and every
    shortcut; the .png is what Qt puts in the window and the tray. They came
    from different files once and nobody noticed until a shortcut appeared with
    a green ring on it. This compares the artwork rather than trusting a
    filename, so regenerating the fallback over the real icon fails here.
    """
    print("\n>>> checking the executable icon is the real artwork")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage

    app = QGuiApplication.instance() or QGuiApplication([])

    def difference(first: QImage, second: QImage) -> float:
        size = 32
        pair = [
            image.convertToFormat(QImage.Format.Format_ARGB32).scaled(
                size,
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            for image in (first, second)
        ]
        total = 0
        for y in range(size):
            for x in range(size):
                left, right = (image.pixelColor(x, y) for image in pair)
                total += (
                    abs(left.red() - right.red())
                    + abs(left.green() - right.green())
                    + abs(left.blue() - right.blue())
                    + abs(left.alpha() - right.alpha())
                )
        return total / (size * size * 4)

    artwork = QImage(str(ASSETS / "ocura.png"))
    shipped = QImage(str(ASSETS / "ocura.ico"))
    placeholder = QImage(str(ASSETS / "ocura-fallback.ico"))
    for name, image in (("ocura.png", artwork), ("ocura.ico", shipped)):
        if image.isNull():
            raise SystemExit(f"cannot read {name}")

    to_artwork = difference(shipped, artwork)
    to_placeholder = difference(shipped, placeholder)
    print(f"    ocura.ico differs from the artwork by {to_artwork:.1f}")
    print(f"    ocura.ico differs from the placeholder by {to_placeholder:.1f}")

    if to_artwork >= to_placeholder:
        raise SystemExit(
            "ocura.ico looks like the drawn placeholder, not the artwork.\n"
            r"Rebuild it:  .venv\Scripts\python.exe scripts\convert_icon.py"
        )
    del app


def build() -> None:
    for stale in (DIST, BUILD):
        try:
            shutil.rmtree(stale)
        except FileNotFoundError:
            pass
        except PermissionError as error:
            # Windows will not let a running executable's folder be replaced,
            # and PyInstaller's own message for this is a bare traceback.
            raise SystemExit(
                f"cannot clear {stale}: {error}\n"
                "A previous build is still running. Quit Ocura from its tray "
                "menu, or:  taskkill /F /IM Ocura.exe"
            ) from error
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


def version() -> str:
    """The version, read out of the one file that holds it.

    Read as text rather than imported, for the reason the spec gives for doing
    the same: packaging must not depend on `ocura` being importable in
    whatever environment is doing the packaging, because that is one of the
    things the build is supposed to be testing. The number itself lives in
    src/ocura/__init__.py and nowhere else — see that file.
    """
    found = re.search(r'__version__ = "([^"]+)"', VERSION_SOURCE.read_text(encoding="utf-8"))
    if found is None:
        raise SystemExit(f"no __version__ in {VERSION_SOURCE}")
    return found.group(1)


def find_iscc() -> Path:
    """Inno Setup's command-line compiler, wherever this machine keeps it.

    Both installation roots are searched because Inno Setup 6's own installer
    picks between them: run with an administrator it lands under Program Files
    (x86), and run without one — which is how it goes on a machine where the
    person cannot elevate — it lands under %LOCALAPPDATA%\\Programs. Looking in
    only the first place finds nothing on the second kind of machine and
    reports it as "not installed", which is the wrong thing to say to somebody
    who has just installed it. PATH is tried last, for an unpacked copy.
    """
    roots = [
        # Upper case because os.environ is case-insensitive on Windows and
        # ruff's SIM112 reads the conventional spelling as the intended one.
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Inno Setup 6" / "ISCC.exe"
        if candidate.is_file():
            return candidate

    on_path = shutil.which("ISCC")
    if on_path:
        return Path(on_path)

    raise SystemExit(
        "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php\n"
        "(or: winget install JRSoftware.InnoSetup), then run this again.\n"
        "Looked in:\n  "
        + "\n  ".join(str(Path(root) / "Inno Setup 6" / "ISCC.exe") for root in roots if root)
        + "\n  PATH"
    )


def package(number: str) -> Path:
    """Compile the installer over the folder that was just built.

    The version is passed in on the command line rather than written into the
    script, which refuses to compile without it — see packaging/ocura.iss. The
    result is checked for existence and for plausible size, because ISCC can
    exit zero having produced something unusable and the next person to find
    out would be whoever downloaded it.
    """
    iscc = find_iscc()
    run(f"building the installer with {iscc}", [str(iscc), f"/DAppVersion={number}", str(ISS)])

    setup = DIST / f"Ocura-{number}-Setup.exe"
    if not setup.exists():
        raise SystemExit(f"ISCC reported success but produced no {setup.name} in {DIST}")

    megabytes = setup.stat().st_size / 1_000_000
    print(f"    {setup.name} is {megabytes:.0f} MB")
    if megabytes < MINIMUM_INSTALLER_MB:
        raise SystemExit(
            f"{setup.name} is only {megabytes:.1f} MB, which is too small to contain Qt"
        )
    return setup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="build without running ruff and pytest first (not for anything handed over)",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="also compile packaging/ocura.iss into dist/Ocura-<version>-Setup.exe",
    )
    args = parser.parse_args()

    started = time.monotonic()
    # Before anything is built, so a source with no readable version number
    # fails in a second rather than after a five-minute PyInstaller run.
    number = version()
    print(f"Ocura {number}")

    if args.skip_checks:
        print("!!! skipping ruff and pytest — do not hand this build to anyone")
    else:
        gate()

    check_icon()
    build()
    assemble()
    verify()
    setup = package(number) if args.installer else None

    size = sum(f.stat().st_size for f in HANDOVER.rglob("*") if f.is_file())
    print(f"\nBuilt in {time.monotonic() - started:.0f}s, {size / 1_000_000:.0f} MB")
    print(f"\n    {HANDOVER}\n")
    print("Hand over the whole folder. Ocura.exe alone will not run.")
    if setup is not None:
        print(f"\n    {setup}\n")
        print("Or hand over the installer, which is one file and needs no explaining.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
