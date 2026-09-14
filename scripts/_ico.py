"""Write a multi-size Windows .ico. Shared by the two scripts that make one.

Qt can write a single-image .ico, but Windows picks a frame by size and a
one-frame file is scaled badly at 16px. This assembles the container by hand so
every size is a real, separately-scaled image.
"""

from __future__ import annotations

import struct
from pathlib import Path

#: The sizes Windows asks for: taskbar, tray, Explorer, Alt-Tab, and the large
#: preview.
SIZES = (16, 24, 32, 48, 64, 128, 256)


def bmp_frame(size: int, bgra_rows_bottom_up: bytes) -> bytes:
    """One ICO frame: a BMP info header, the pixels, and an unused AND mask."""
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size,  # biWidth
        size * 2,  # biHeight: doubled, XOR image plus AND mask
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression
        len(bgra_rows_bottom_up),
        0,
        0,
        0,
        0,
    )
    mask_row = ((size + 31) // 32) * 4
    return header + bgra_rows_bottom_up + b"\x00" * (mask_row * size)


def write_ico(path: Path, frames: dict[int, bytes]) -> Path:
    """frames maps a pixel size to its bottom-up BGRA rows."""
    images = [bmp_frame(size, frames[size]) for size in sorted(frames)]
    offset = 6 + 16 * len(images)

    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, image in zip(sorted(frames), images, strict=True):
        out += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # 0 means 256 in the ICO header
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(image),
            offset,
        )
        offset += len(image)
    out += b"".join(images)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path
