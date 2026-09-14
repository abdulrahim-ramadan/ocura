"""Put an Ocura shortcut on the Desktop, pointing at the built executable.

    .venv\\Scripts\\python.exe scripts\\make_shortcut.py

Standard library only. Creating a .lnk needs COM, and the usual answer is
pywin32 — but a shortcut helper is not worth a dependency, and pywin32 would sit
in the environment tempting someone to import it from application code, where it
has no business. WScript.Shell is present on every Windows install and is driven
here through PowerShell, so nothing is added to the project.

The Desktop path comes from the shell rather than from %USERPROFILE%\\Desktop:
OneDrive redirects it, and the literal path is then wrong on exactly the
machines where it looks most plausible.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = ROOT / "dist" / "Ocura" / "Ocura.exe"
SHORTCUT_NAME = "Ocura.lnk"

_POWERSHELL = """
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop '{name}'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = '{target}'
$shortcut.WorkingDirectory = '{working}'
$shortcut.IconLocation = '{icon}'
$shortcut.Description = 'Ocura — better screen habits'
$shortcut.Save()
Write-Output $link
"""


def make_shortcut(target: Path, icon: Path | None = None) -> Path:
    if not target.is_file():
        raise SystemExit(
            f"no executable at {target}\n"
            "Build one first:  .venv\\Scripts\\python.exe scripts\\build_release.py"
        )

    script = _POWERSHELL.format(
        name=SHORTCUT_NAME,
        target=target,
        working=target.parent,
        # The exe carries the icon already; pointing at it keeps the shortcut
        # correct if the icon is ever changed and the app rebuilt.
        icon=icon or target,
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"could not create the shortcut:\n{result.stderr.strip()}")
    return Path(result.stdout.strip())


def main() -> int:
    if sys.platform != "win32":
        raise SystemExit("Windows only: a .lnk means nothing anywhere else.")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help="the executable to point at (default: the last trial build)",
    )
    args = parser.parse_args()

    link = make_shortcut(args.target.resolve())
    print(f"shortcut created:\n\n    {link}\n\npointing at:\n\n    {args.target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
