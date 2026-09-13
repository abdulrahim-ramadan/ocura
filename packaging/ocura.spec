# PyInstaller spec for a trial Windows build.
#
#   .venv\Scripts\pyinstaller.exe packaging\ocura.spec --noconfirm
#
# Not P7. There is no installer, no signing and no updater here; this exists so
# a few people can run Ocura without installing Python.
#
# --onedir, never --onefile. PySide6 ships Qt under the LGPL v3, which requires
# that the user can replace the Qt libraries with their own build. A one-file
# bundle unpacks to a temporary directory at every launch and there is nothing
# durable to replace, so onefile would put the build out of compliance. The Qt
# DLLs stay as separate, replaceable files in _internal/ for that reason, not
# for convenience.

from pathlib import Path

SRC = Path("src").resolve()
ROOT = SRC.parent

datas = [
    # Package data, kept at the same import path so importlib.resources finds
    # it in the bundle exactly as it does in the source tree.
    (str(SRC / "ocura" / "ui" / "style.qss"), "ocura/ui"),
    (str(SRC / "ocura" / "ui" / "assets"), "ocura/ui/assets"),
    # LGPL obligations travel with the binary, not with the repository.
    (str(ROOT / "licenses" / "LGPL-3.0.txt"), "licenses"),
    (str(ROOT / "licenses" / "GPL-3.0.txt"), "licenses"),
    (str(ROOT / "licenses" / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(ROOT / "LICENSE"), "licenses"),
]

analysis = Analysis(
    [str(SRC / "ocura" / "ui" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Nothing here is used, and each one drags in more to audit for licensing.
    excludes=["tkinter", "unittest", "pydoc", "pytest", "PySide6.QtWebEngineCore"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Ocura",
    debug=False,
    strip=False,
    upx=False,
    # No console window: Ocura is a tray application. Diagnostics come from
    # `Ocura.exe --self-check > out.txt`, which works without one.
    console=False,
    icon=str(SRC / "ocura" / "ui" / "assets" / "ocura.ico"),
)

COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Ocura",
)

# PyInstaller 6 puts every data file under _internal/. Licence notices belong
# where someone handed the folder will see them, so they are lifted back up
# beside the executable. The copies under _internal/ are left alone: harmless,
# and removing them would mean reaching into COLLECT's output.
import shutil  # noqa: E402 - a spec file is a script, not a module

_dist = Path(DISTPATH) / "Ocura"
shutil.copytree(_dist / "_internal" / "licenses", _dist / "licenses", dirs_exist_ok=True)
(_dist / "READ ME FIRST.txt").write_text(
    "Ocura — trial build\n"
    "\n"
    "Run Ocura.exe. It lives in the system tray; closing the window hides it there.\n"
    "\n"
    "Windows will warn that the publisher is unknown, because this build is not\n"
    "code-signed. Choose More info, then Run anyway, or delete the folder if you\n"
    "would rather not.\n"
    "\n"
    "If it does not start, open a terminal here and run:\n"
    "    Ocura.exe --self-check > selfcheck.txt\n"
    "then send selfcheck.txt.\n"
    "\n"
    "Licences for Ocura and for the Qt libraries it uses are in licenses\\.\n",
    encoding="utf-8",
)
