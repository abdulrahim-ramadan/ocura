# PyInstaller spec for a trial Windows build.
#
# Driven by scripts/build_release.py, which gates on ruff and pytest, adds the
# licence notices and the read-me, and verifies the result. Running PyInstaller
# against this spec directly produces the executable but not a complete handover
# folder — the notices are assembled by that script, so there is one definition
# of what a handover contains.
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

datas = [
    # Package data, kept at the same import path so importlib.resources finds
    # it in the bundle exactly as it does in the source tree.
    (str(SRC / "ocura" / "ui" / "style.qss"), "ocura/ui"),
    (str(SRC / "ocura" / "ui" / "assets"), "ocura/ui/assets"),
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
