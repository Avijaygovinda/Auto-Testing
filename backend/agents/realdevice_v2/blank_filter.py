"""
Cheap blank-PNG detection. Uses pure-stdlib PNG decoding to avoid adding
Pillow as a hard dependency. We don't need pixel-perfect analysis — just
"is this screenshot mostly one color, in which case sending it to Gemini
Vision is wasteful?".

Strategy: read the PNG, decode to RGBA, sample a grid of pixels, compute
unique-color count weighted by frequency. If a single color dominates
above threshold, mark blank.
"""
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Tuple


def _decode_png_pixels(data: bytes, sample_grid: int = 32) -> list[Tuple[int, int, int]]:
    """Return a list of RGB tuples sampled on a sample_grid x sample_grid grid.

    Lightweight pure-stdlib PNG decoder good enough for screenshots produced
    by Flutter (8-bit RGBA, no interlacing). Returns empty on parse failure.
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return []

    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 8 + length + 4  # +4 = CRC
        if ctype == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
            bit_depth = body[8]
            color_type = body[9]
        elif ctype == b"IDAT":
            idat.extend(body)
        elif ctype == b"IEND":
            break

    if not width or not height or bit_depth != 8:
        return []
    # Color type 6 = RGBA (4 bytes/pixel), 2 = RGB (3), 0 = Grayscale (1).
    bpp_map = {6: 4, 2: 3, 0: 1}
    bpp = bpp_map.get(color_type)
    if not bpp:
        return []

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return []

    stride = width * bpp + 1  # +1 for filter byte per row
    if len(raw) < stride * height:
        return []

    pixels: list[Tuple[int, int, int]] = []
    step_x = max(1, width // sample_grid)
    step_y = max(1, height // sample_grid)

    # Apply per-row PNG filtering minimally — for screenshots most rows are
    # filter type 0 (None) but we handle Sub/Up/Average/Paeth roughly.
    prev_row = bytearray(stride - 1)
    for y in range(height):
        row_start = y * stride
        filt = raw[row_start]
        row = bytearray(raw[row_start + 1:row_start + stride])
        if filt == 0:
            pass
        elif filt == 1:  # Sub
            for i in range(bpp, len(row)):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif filt == 2:  # Up
            for i in range(len(row)):
                row[i] = (row[i] + prev_row[i]) & 0xFF
        elif filt == 3:  # Average
            for i in range(len(row)):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + (left + prev_row[i]) // 2) & 0xFF
        elif filt == 4:  # Paeth
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                b = prev_row[i]
                c = prev_row[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pred) & 0xFF
        else:
            return []  # unknown filter — bail
        prev_row = row

        if y % step_y != 0:
            continue
        for x in range(0, width, step_x):
            off = x * bpp
            if bpp >= 3:
                pixels.append((row[off], row[off + 1], row[off + 2]))
            else:
                v = row[off]
                pixels.append((v, v, v))
    return pixels


def _edge_density(pixels: list[Tuple[int, int, int]], step_threshold: int = 24) -> float:
    """Fraction of adjacent sampled pixels with significant RGB delta.

    A real screen with content (text, icons, cards) has many sharp transitions
    between adjacent sampled pixels. A genuinely blank/uniform screen has
    almost none. This is a cheap proxy for "is there visible content?" that
    works regardless of theme color (light or dark).
    """
    if len(pixels) < 2:
        return 0.0
    edges = 0
    for i in range(len(pixels) - 1):
        a, b = pixels[i], pixels[i + 1]
        if max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) > step_threshold:
            edges += 1
    return edges / (len(pixels) - 1)


def is_blank(png_path: str | Path, dominant_threshold: float = 0.985,
             color_tolerance: int = 12, edge_threshold: float = 0.005) -> tuple[bool, dict]:
    """Return (is_blank, info_dict).

    Image is "blank" only when BOTH:
      - one quantized color dominates >= dominant_threshold of samples, AND
      - edge density (adjacent-pixel high-contrast transitions) < edge_threshold.

    The second check fixes the false-positive on dark-theme screens where
    the background eats most pixels but the screen still has substantial UI.
    """
    data = Path(png_path).read_bytes()
    pixels = _decode_png_pixels(data)
    if not pixels:
        return False, {"reason": "decode_failed", "sampled": 0}

    quantized = [
        (r // color_tolerance, g // color_tolerance, b // color_tolerance)
        for r, g, b in pixels
    ]
    counter = Counter(quantized)
    most_common, count = counter.most_common(1)[0]
    fraction = count / len(quantized)
    edges = _edge_density(pixels)
    blank = fraction >= dominant_threshold and edges < edge_threshold
    return blank, {
        "sampled": len(quantized),
        "dominant_color_qzd": most_common,
        "dominant_fraction": round(fraction, 3),
        "edge_density": round(edges, 4),
        "dominant_threshold": dominant_threshold,
        "edge_threshold": edge_threshold,
    }


if __name__ == "__main__":
    import sys
    p = sys.argv[1]
    blank, info = is_blank(p)
    print(f"{'BLANK' if blank else 'NOT BLANK'}: {info}")
