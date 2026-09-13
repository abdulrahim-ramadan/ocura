"""Regenerate the fallback icon. Pure stdlib, no image library.

Not the shipped icon: ocura.png beside it is, and this only stands in if that
file is missing. A calm lens, deliberately plain — P6 owns the visual identity.
"""

from __future__ import annotations

import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "ocura" / "ui" / "assets" / "ocura.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 4  # supersampling factor for anti-aliasing

RING = (0x6E, 0xC6, 0xB8)  # muted teal, RGB
CORE = (0x2F, 0x6F, 0x67)


def coverage(size: int, cx: float, cy: float, outer: float, inner: float) -> list[list[float]]:
    """Per-pixel coverage of an annulus, by supersampling."""
    grid = [[0.0] * size for _ in range(size)]
    for py in range(size):
        for px in range(size):
            hits = 0
            for sy in range(SS):
                for sx in range(SS):
                    x = px + (sx + 0.5) / SS - cx
                    y = py + (sy + 0.5) / SS - cy
                    d = (x * x + y * y) ** 0.5
                    if inner <= d <= outer:
                        hits += 1
            grid[py][px] = hits / (SS * SS)
    return grid


def render(size: int) -> bytes:
    """32-bit BGRA, bottom-up, as a BMP inside an ICO expects."""
    c = size / 2
    outer = size * 0.46
    inner = size * 0.26
    ring = coverage(size, c, c, outer, inner)
    core = coverage(size, c, c, size * 0.13, 0.0)

    rows = []
    for py in reversed(range(size)):
        row = bytearray()
        for px in range(size):
            a_ring, a_core = ring[py][px], core[py][px]
            alpha = min(1.0, a_ring + a_core)
            if alpha <= 0:
                row += b"\x00\x00\x00\x00"
                continue
            # Core sits on top of the ring colour where they overlap.
            r, g, b = CORE if a_core > a_ring else RING
            row += bytes((b, g, r, round(alpha * 255)))
        rows.append(bytes(row))
    return b"".join(rows)


def bmp(size: int, pixels: bytes) -> bytes:
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        size,  # biWidth
        size * 2,  # biHeight: doubled, XOR image plus AND mask
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression
        len(pixels),
        0,
        0,
        0,
        0,
    )
    # The AND mask is unused for 32-bit icons but the structure still requires it.
    mask_row = ((size + 31) // 32) * 4
    return header + pixels + b"\x00" * (mask_row * size)


def main() -> None:
    images = [bmp(size, render(size)) for size in SIZES]
    offset = 6 + 16 * len(SIZES)
    out = bytearray(struct.pack("<HHH", 0, 1, len(SIZES)))
    for size, image in zip(SIZES, images, strict=True):
        out += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(image),
            offset,
        )
        offset += len(image)
    for image in images:
        out += image

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(out))
    print(f"wrote {OUT} ({len(out)} bytes, sizes {SIZES})")


if __name__ == "__main__":
    main()
