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

import re
from pathlib import Path

SRC = Path("src").resolve()
BUILD = Path("build").resolve()

# The version, read from the one file that holds it rather than repeated here.
# The spec is not imported as a module, so it reads the literal out of the
# source instead of importing the package — a spec that imported ocura would
# make packaging depend on the package being importable in the build
# environment, which is the thing being tested.
VERSION = re.search(
    r'__version__ = "([^"]+)"', (SRC / "ocura" / "__init__.py").read_text(encoding="utf-8")
).group(1)

#: Windows wants four numbers. Ocura has three, and the fourth is the build
#: field, which nothing here uses — a release is identified by its tag.
FILE_VERSION = tuple(int(part) for part in VERSION.split(".")) + (0,)

#: The properties Explorer shows on right-click → Details, and the ones an IT
#: department reads before allowing an unsigned executable onto a machine. An
#: executable with none of this looks like something that was thrown together,
#: which for an unsigned build is the opposite of the impression to give.
VERSION_RESOURCE = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={FILE_VERSION},
    prodvers={FILE_VERSION},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        "040904B0",
        [
          StringStruct("CompanyName", "Abdulrahim Ramadan"),
          StringStruct("FileDescription", "Ocura - calm break reminders for Windows"),
          StringStruct("FileVersion", "{VERSION}"),
          StringStruct("InternalName", "Ocura"),
          StringStruct("LegalCopyright", "Copyright (c) 2026 Abdulrahim Ramadan"),
          StringStruct("OriginalFilename", "Ocura.exe"),
          StringStruct("ProductName", "Ocura"),
          StringStruct("ProductVersion", "{VERSION}"),
        ],
      )
    ]),
    VarFileInfo([VarStruct("Translation", [1033, 1200])]),
  ],
)
"""

BUILD.mkdir(parents=True, exist_ok=True)
VERSION_FILE = BUILD / "version_info.txt"
VERSION_FILE.write_text(VERSION_RESOURCE, encoding="utf-8")

datas = [
    # Package data, kept at the same import path so importlib.resources finds
    # it in the bundle exactly as it does in the source tree.
    (str(SRC / "ocura" / "ui" / "style.qss"), "ocura/ui"),
    (str(SRC / "ocura" / "ui" / "assets"), "ocura/ui/assets"),
    # The compiled catalogues. A build without them does not fail: it runs in
    # English and says nothing, on a machine whose owner chose Arabic. That is
    # why --self-check reports each one and the release verify greps its
    # output for MISSING.
    (str(SRC / "ocura" / "ui" / "i18n"), "ocura/ui/i18n"),
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
    version=str(VERSION_FILE),
)

COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Ocura",
)
