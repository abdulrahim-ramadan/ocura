"""Build ocura.ico from ocura.png, so every surface shows the same artwork.

    .venv\\Scripts\\python.exe scripts\\convert_icon.py

Windows needs an .ico for the executable and for shortcuts; Qt is happy with the
PNG for the window and the tray. Before this script the two came from different
files — the PNG was the real icon and the .ico was the placeholder from
make_icon.py — so the taskbar and the desktop shortcut showed a green ring that
appeared nowhere else in the application. The .ico is now derived from the PNG
and nothing else.

Run it after changing the artwork. scripts/build_release.py checks that the two
still match and refuses to package a build where they do not.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _ico import SIZES, write_ico

ASSETS = Path(__file__).resolve().parent.parent / "src" / "ocura" / "ui" / "assets"
SOURCE = ASSETS / "ocura.png"
TARGET = ASSETS / "ocura.ico"


def bgra_bottom_up(image: QImage) -> bytes:
    """The row order and channel order an ICO frame expects."""
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)
    rows = []
    for y in reversed(range(converted.height())):
        row = bytearray()
        for x in range(converted.width()):
            colour = converted.pixelColor(x, y)
            row += bytes((colour.blue(), colour.green(), colour.red(), colour.alpha()))
        rows.append(bytes(row))
    return b"".join(rows)


def convert(source: Path = SOURCE, target: Path = TARGET) -> Path:
    if not source.is_file():
        raise SystemExit(f"no source artwork at {source}")

    # A QGuiApplication is needed before QImage can do anything useful.
    app = QGuiApplication.instance() or QGuiApplication([])
    image = QImage(str(source))
    if image.isNull():
        raise SystemExit(f"could not read {source}")

    frames = {
        size: bgra_bottom_up(
            image.scaled(
                size,
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        for size in SIZES
    }
    written = write_ico(target, frames)
    del app
    return written


def main() -> int:
    written = convert()
    print(f"wrote {written} ({written.stat().st_size:,} bytes) from {SOURCE.name}, sizes {SIZES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
