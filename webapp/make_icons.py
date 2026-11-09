#!/usr/bin/env python3
"""Generate the CitiNav PWA icons (no dependencies — writes PNG directly).

    python3 make_icons.py

Draws a green arrow on the app's dark-grey background at 192 and 512 px.
"""
import os
import struct
import zlib

BG = (32, 32, 32)       # matches --bg
GREEN = (0, 220, 80)    # matches --green


def arrow_pixel(x, y, s):
    """Right-pointing arrow inside a 0..s box (with margin for maskable icons)."""
    cy = s / 2.0
    # shaft / bar
    if 0.20 * s <= x <= 0.50 * s and 0.44 * s <= y <= 0.56 * s:
        return True
    # head triangle: base at x=0.50s spanning y 0.27..0.73, tip at (0.80s, 0.5s)
    xb, xt = 0.50 * s, 0.80 * s
    if xb <= x <= xt:
        half = 0.23 * s * (xt - x) / (xt - xb)
        if abs(y - cy) <= half:
            return True
    return False


def write_png(path, s):
    raw = bytearray()
    for y in range(s):
        raw.append(0)                       # filter type 0 (None)
        for x in range(s):
            r, g, b = GREEN if arrow_pixel(x, y, s) else BG
            raw += bytes((r, g, b))

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    print("wrote", path, "(%dx%d, %d bytes)" % (s, s, len(png)))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for size in (192, 512):
        write_png(os.path.join(here, "icon-%d.png" % size), size)
