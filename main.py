#!/usr/bin/env python3
"""Velmara — a travel poster for a place that isn't there.

Pure-stdlib Python 3.13. Draws a 1024x1024 sunset poster for the invented
island of Velmara, whose landmark is a giant golden ring standing in the
lagoon, and writes it to /output/entry.png (or $OUTPUT_PATH).

No network, no external files, no third-party packages: the PNG encoder,
the 5x7 bitmap type and every brush stroke are written here from scratch,
so the program runs identically in the grading sandbox.
"""

import math
import os
import struct
import sys
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------------------
# 5x7 bitmap font (glyphs needed for the poster's type only).
# Each glyph is 7 rows of 5 characters; '#' is ink, ' ' is empty.
# ---------------------------------------------------------------------------
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def lerp(a, b, t):
    return int(a + (b - a) * t + 0.5)


def mix(c1, c2, t):
    """Blend two RGB triples; t=0 gives c1, t=1 gives c2."""
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


class Canvas:
    """A 1024x1024 RGB canvas stored as one bytearray per row."""

    def __init__(self, w=W, h=H):
        self.w = w
        self.h = h
        self.rows = [bytearray(w * 3) for _ in range(h)]

    # -- primitive fills ----------------------------------------------------
    def fill_row(self, y, color):
        if 0 <= y < self.h:
            self.rows[y][:] = bytes(color) * self.w

    def fill_rect(self, x, y, rw, rh, color):
        """Solid rectangle, clipped to the canvas."""
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + rw)
        y1 = min(self.h, y + rh)
        if x1 <= x0 or y1 <= y0:
            return
        span = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            row = self.rows[yy]
            row[x0 * 3:x1 * 3] = span

    def hline(self, y, x0, x1, color, alpha=1.0):
        """Horizontal span [x0, x1) on row y, optionally translucent."""
        if not (0 <= y < self.h):
            return
        x0 = max(0, x0)
        x1 = min(self.w, x1)
        if x1 <= x0:
            return
        row = self.rows[y]
        if alpha >= 1.0:
            row[x0 * 3:x1 * 3] = bytes(color) * (x1 - x0)
            return
        r, g, b = color
        for x in range(x0, x1):
            i = x * 3
            row[i] = int(row[i] + (r - row[i]) * alpha + 0.5)
            row[i + 1] = int(row[i + 1] + (g - row[i + 1]) * alpha + 0.5)
            row[i + 2] = int(row[i + 2] + (b - row[i + 2]) * alpha + 0.5)

    def line(self, x0, y0, x1, y1, color, width=1, alpha=1.0):
        """Bresenham line with a square brush of the given width."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = width // 2
        while True:
            self.fill_rect_alpha(x0 - half, y0 - half, width, width, color, alpha)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_rect_alpha(self, x, y, rw, rh, color, alpha):
        if alpha >= 1.0:
            self.fill_rect(x, y, rw, rh, color)
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + rw)
        y1 = min(self.h, y + rh)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b = color
        for yy in range(y0, y1):
            row = self.rows[yy]
            for xx in range(x0, x1):
                i = xx * 3
                row[i] = int(row[i] + (r - row[i]) * alpha + 0.5)
                row[i + 1] = int(row[i + 1] + (g - row[i + 1]) * alpha + 0.5)
                row[i + 2] = int(row[i + 2] + (b - row[i + 2]) * alpha + 0.5)

    # -- discs and rings, drawn as per-row intervals (fast, no per-pixel loop)
    def disc(self, cx, cy, radius, color, alpha=1.0):
        for y in range(max(0, cy - radius), min(self.h, cy + radius + 1)):
            dy = y - cy
            half = int(math.sqrt(max(0, radius * radius - dy * dy)))
            self.hline(y, cx - half, cx + half + 1, color, alpha)

    def annulus(self, cx, cy, r_out, r_in, color, alpha=1.0):
        for y in range(max(0, cy - r_out), min(self.h, cy + r_out + 1)):
            dy = y - cy
            ho = int(math.sqrt(max(0, r_out * r_out - dy * dy)))
            if abs(dy) < r_in:
                hi = int(math.sqrt(max(0, r_in * r_in - dy * dy)))
                self.hline(y, cx - ho, cx - hi, color, alpha)
                self.hline(y, cx + hi + 1, cx + ho + 1, color, alpha)
            else:
                self.hline(y, cx - ho, cx + ho + 1, color, alpha)

    def ellipse_top(self, cx, base_y, rx, height, color, alpha=1.0):
        """Upper half of an ellipse: a hill whose base sits at base_y."""
        for y in range(max(0, base_y - height), min(self.h, base_y + 1)):
            t = (base_y - y) / float(height)
            half = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            self.hline(y, cx - half, cx + half + 1, color, alpha)

    # -- bitmap type ---------------------------------------------------------
    def text(self, text, x, y, scale, color):
        """Draw text with the 5x7 font; returns the pixel width drawn."""
        cx = x
        for ch in text:
            glyph = FONT.get(ch, FONT[" "])
            for gy, bits in enumerate(glyph):
                for gx, bit in enumerate(bits):
                    if bit == "1":
                        self.fill_rect(cx + gx * scale, y + gy * scale,
                                       scale, scale, color)
            cx += 6 * scale
        return cx - x - scale

    def text_centered(self, text, y, scale, color, cx=W // 2):
        width = len(text) * 6 * scale - scale
        return self.text(text, cx - width // 2, y, scale, color)


# ---------------------------------------------------------------------------
# PNG encoding (pure stdlib: signature, IHDR, IDAT, IEND).
# ---------------------------------------------------------------------------
def write_png(canvas, path):
    raw = bytearray()
    for row in canvas.rows:
        raw.append(0)  # filter: None
        raw.extend(row)
    data = zlib.compress(bytes(raw), 9)
    if len(data) + 8 + 25 + 12 + 12 > 1_048_576:
        # Fall back to the Sub filter, which compresses gradients better.
        raw = bytearray()
        for row in canvas.rows:
            raw.append(1)  # filter: Sub
            raw.extend(row[0:3])
            for i in range(3, len(row)):
                raw.append((row[i] - row[i - 3]) & 0xFF)
        data = zlib.compress(bytes(raw), 9)

    def chunk(kind, payload):
        out = struct.pack(">I", len(payload)) + kind + payload
        out += struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        return out

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", data)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------------------
# The poster: Velmara, the island where a golden ring stands in the lagoon.
# ---------------------------------------------------------------------------
SKY_TOP = (27, 30, 75)
SKY_MID = (88, 52, 110)
SKY_LOW = (178, 84, 110)
SKY_HORIZON = (240, 138, 75)
SEA_TOP = (44, 110, 124)
SEA_BOTTOM = (16, 54, 88)
SAND_TOP = (232, 200, 143)
SAND_BOTTOM = (198, 150, 92)
GOLD = (255, 196, 110)
GOLD_BRIGHT = (255, 230, 170)
CREAM = (255, 243, 214)
DARK = (28, 24, 54)
HORIZON = 620
BEACH_TOP = 860


def draw_sky(c):
    stops = [(0.0, SKY_TOP), (0.35, SKY_MID), (0.55, SKY_LOW),
             (1.0, SKY_HORIZON)]
    for y in range(HORIZON):
        t = y / float(HORIZON)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                c.fill_row(y, mix(c0, c1, (t - t0) / (t1 - t0)))
                break


def draw_clouds(c):
    # Soft warm bands drifting across the upper sky.
    for cx, cy, rx, ry, alpha in [
            (205, 180, 150, 16, 0.20),
            (775, 140, 185, 15, 0.18),
            (640, 265, 120, 13, 0.15),
            (330, 320, 95, 11, 0.12)]:
        for y in range(cy - ry, cy + ry + 1):
            t = (y - cy) / float(ry)
            half = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            c.hline(y, cx - half, cx + half + 1, (255, 190, 150), alpha)


def draw_sun(c):
    cx, cy = 512, 565
    # Layered glow, widest and faintest first.
    for radius, alpha in [(260, 0.10), (200, 0.16), (150, 0.24), (110, 0.35)]:
        c.disc(cx, cy, radius, (255, 170, 90), alpha)
    c.disc(cx, cy, 64, (255, 214, 130))
    c.disc(cx, cy, 40, (255, 232, 170))


def draw_ring(c):
    cx, cy = 512, 468
    # The Ring of Velmara: a halo of light standing in the lagoon.
    c.annulus(cx, cy, 228, 148, GOLD, 0.18)          # outer glow
    c.annulus(cx, cy, 208, 168, GOLD)                # the band itself
    c.annulus(cx, cy, 172, 168, GOLD_BRIGHT)         # bright inner edge
    c.annulus(cx, cy, 208, 204, (255, 220, 150))     # bright outer edge


def draw_sea(c):
    for y in range(HORIZON, BEACH_TOP):
        t = (y - HORIZON) / float(BEACH_TOP - HORIZON)
        c.fill_row(y, mix(SEA_TOP, SEA_BOTTOM, t))
    # Sunlight shattered on the water: a shimmering column under the sun.
    for y in range(HORIZON + 6, BEACH_TOP - 8):
        span = 26 + int(46 * (y - HORIZON) / float(BEACH_TOP - HORIZON))
        wobble = int(14 * math.sin(y * 0.11))
        seed = (y * 2654435761) % 100
        if seed < 62:
            x0 = 512 - span // 2 + wobble
            c.hline(y, x0, x0 + span, (255, 200, 120), 0.45)
        if seed > 55:
            x1 = 512 - span // 4 - wobble
            c.hline(y, x1, x1 + span // 2, (255, 220, 150), 0.30)


def draw_island(c, cx, base_y, rx, height, palms):
    c.ellipse_top(cx, base_y, rx, height, DARK)
    for px, lean in palms:
        px = cx + px
        top_x = px + lean
        top_y = base_y - height - 8
        c.line(px, base_y - 6, top_x, top_y, DARK, width=3)
        for dx, dy in [(-26, 6), (-18, -8), (0, -16), (18, -8), (26, 6)]:
            c.line(top_x, top_y, top_x + dx, top_y + dy, DARK, width=2)
        c.disc(top_x - 4, top_y + 2, 3, DARK)
        c.disc(top_x + 4, top_y + 2, 3, DARK)


def draw_boat(c, x, y, scale=1):
    # A small sailboat: dark hull, cream sail, thin mast.
    c.line(x, y - 34 * scale, x, y, DARK, width=2)
    for row in range(14 * scale):
        half = int(row * 0.9) + 1
        c.hline(y - 22 * scale + row, x + 2, x + 2 + half, CREAM)
    for row in range(9):
        half = int(9 - row)
        c.hline(y + row, x - half - 2, x + half + 3, DARK)


def draw_birds(c):
    for bx, by, s in [(150, 330, 12), (200, 298, 9), (852, 322, 11),
                      (896, 290, 8), (820, 268, 9)]:
        c.line(bx - s, by, bx, by + 4, DARK, width=2, alpha=0.85)
        c.line(bx, by + 4, bx + s, by, DARK, width=2, alpha=0.85)


def draw_beach(c):
    for y in range(BEACH_TOP, H):
        t = (y - BEACH_TOP) / float(H - BEACH_TOP)
        c.fill_row(y, mix(SAND_TOP, SAND_BOTTOM, t))
    # A soft shadow where the sand meets the sea.
    for y in range(BEACH_TOP, BEACH_TOP + 22):
        c.hline(y, 0, W, (120, 84, 48), 0.25 * (1 - (y - BEACH_TOP) / 22.0))
    # Scattered pebbles and shells, placed by a fixed pattern.
    for i in range(26):
        px = (97 * i * 37 + 61) % 980 + 22
        py = BEACH_TOP + 34 + (53 * i * 29 + 17) % 130
        pr = 3 + (i * 7) % 5
        c.disc(px, py, pr, (120, 84, 48) if i % 3 else (90, 60, 40), 0.55)


def draw_frame(c):
    c.fill_rect(20, 20, W - 40, 5, CREAM)
    c.fill_rect(20, H - 25, W - 40, 5, CREAM)
    c.fill_rect(20, 20, 5, H - 40, CREAM)
    c.fill_rect(W - 25, 20, 5, H - 40, CREAM)
    c.fill_rect(32, 32, W - 64, 2, CREAM)
    c.fill_rect(32, H - 34, W - 64, 2, CREAM)
    c.fill_rect(32, 32, 2, H - 64, CREAM)
    c.fill_rect(W - 34, 32, 2, H - 64, CREAM)


def render():
    c = Canvas()
    draw_sky(c)
    draw_clouds(c)
    draw_sun(c)
    draw_ring(c)
    draw_sea(c)
    draw_island(c, 185, 642, 120, 42, [(-52, -6), (18, 8), (64, -4)])
    draw_island(c, 845, 640, 105, 36, [(-38, 6), (30, -8)])
    draw_boat(c, 352, 716)
    draw_boat(c, 688, 748, scale=1)
    draw_birds(c)
    draw_beach(c)
    draw_frame(c)
    # The name is the promise: big, cream, legible, set into the sky.
    c.text_centered("VELMARA", 108, 13, (40, 20, 60))
    c.text_centered("VELMARA", 104, 13, CREAM)
    c.text_centered("WHERE THE SEA MEETS THE SKY", 228, 4, CREAM)
    c.text_centered("EST. NOWHERE", 966, 3, (90, 58, 34))
    return c


def main():
    out = os.environ.get("OUTPUT_PATH", "/output/entry.png")
    canvas = render()
    try:
        size = write_png(canvas, out)
    except OSError:
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "entry.png")
        size = write_png(canvas, out)
    print("wrote %s (%dx%d, %d bytes)" % (out, W, H, size))
    if size > 1_048_576:
        print("ERROR: entry.png exceeds the 1 MiB cap", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
