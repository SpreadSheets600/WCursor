"""Parse Windows cursor containers: ``.ico``, ``.cur`` and ``.ani``.

Everything is decoded to *straight* (non-premultiplied) ``R, G, B, A`` bytes;
:mod:`wcursor.xcursor` premultiplies when writing the Xcursor theme.

Supported image encodings inside the containers:

* PNG (colour types 0/2/3/4/6, bit depth 1-16, non-interlaced)
* BMP / DIB (1, 4, 8, 16, 24 and 32 bits per pixel, with AND mask)
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from os import PathLike
from typing import List, Optional, Sequence

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JIFFY_MS = 1000.0 / 60.0
BI_BITFIELDS = 3


class CursorFormatError(Exception):
    """Raised when a Windows cursor file cannot be decoded."""


@dataclass
class Frame:
    """One decoded frame, straight ``R, G, B, A``."""

    width: int
    height: int
    xhot: int
    yhot: int
    rgba: bytes
    delay: int = 0          # milliseconds to the next frame (animated only)

    @property
    def area(self) -> int:
        return self.width * self.height


# --- public API --------------------------------------------------------------

def load(path: str | PathLike) -> List[Frame]:
    """Load any supported cursor file into a playback list of frames."""
    with open(path, "rb") as fh:
        data = fh.read()
    return parse(data)


def parse(data: bytes) -> List[Frame]:
    if data[:4] == b"RIFF":
        return parse_ani(data)
    return static_frames(data)


def static_frames(data: bytes) -> List[Frame]:
    """A ``.ico``/``.cur`` -> a single frame (its largest embedded image)."""
    images = parse_icon(data)
    if not images:
        raise CursorFormatError("no images in icon/cursor file")
    best = max(images, key=lambda f: f.area)
    best.delay = 0
    return [best]


def parse_icon(data: bytes) -> List[Frame]:
    """Return every embedded image of a ``.ico`` or ``.cur`` file."""
    if len(data) < 6:
        raise CursorFormatError("file too short")
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or kind not in (1, 2) or count == 0:
        raise CursorFormatError("not an ICO/CUR file")
    frames: List[Frame] = []
    for i in range(count):
        off = 6 + i * 16
        if off + 16 > len(data):
            break
        width, height, _colors, _res, planes, bpp, size, offset = struct.unpack_from(
            "<BBBBHHII", data, off
        )
        blob = data[offset:offset + size]
        if not blob:
            continue
        if kind == 2:                      # .cur stores the hotspot in these fields
            xhot, yhot = planes, bpp
        else:                              # .ico: real planes/bitcount
            xhot = yhot = 0
        frame = _decode_image(blob, width or 256, height or 256)
        frame.xhot = min(frame.xhot or xhot, frame.width - 1)
        frame.yhot = min(frame.yhot or yhot, frame.height - 1)
        frames.append(frame)
    if not frames:
        raise CursorFormatError("no decodable images")
    return frames


def parse_ani(data: bytes) -> List[Frame]:
    """Parse a RIFF ``ACON`` animated cursor into a playback frame list."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"ACON":
        raise CursorFormatError("not an ANI file")
    pos = 12
    anih = None
    rates: Optional[List[int]] = None
    seq: Optional[List[int]] = None
    frames: List[Frame] = []

    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"anih" and len(body) >= 36:
            (cb, n_frames, n_steps, _cx, _cy, _bc, _pl,
             disp_rate, _attrs) = struct.unpack_from("<9I", body, 0)
            anih = dict(n_frames=n_frames, n_steps=n_steps, disp_rate=disp_rate)
        elif cid == b"rate":
            rates = list(struct.unpack_from("<%dI" % (size // 4), body, 0))
        elif cid == b"seq ":
            seq = list(struct.unpack_from("<%dI" % (size // 4), body, 0))
        elif cid == b"LIST" and body[:4] == b"fram":
            frames = _parse_fram(body[4:])
        pos += 8 + size + (size & 1)

    if anih is None:
        raise CursorFormatError("ANI missing 'anih' header")
    if not frames:
        raise CursorFormatError("ANI has no frames")

    n_frames = anih["n_frames"] or len(frames)
    n_steps = anih["n_steps"] or n_frames
    steps = list(seq) if seq else list(range(n_steps))
    if len(steps) < n_steps:
        steps += list(range(len(steps), n_steps))

    delays = _resolve_delays(rates, n_steps, n_frames, anih["disp_rate"], steps)

    playback: List[Frame] = []
    for i in range(n_steps):
        idx = steps[i] % len(frames)
        src = frames[idx]
        playback.append(
            Frame(src.width, src.height, src.xhot, src.yhot, src.rgba, delays[i])
        )
    return playback


def _resolve_delays(rates, n_steps, n_frames, disp_rate, steps) -> List[int]:
    default = max(1, int(round(disp_rate * JIFFY_MS))) if disp_rate else int(round(5 * JIFFY_MS))
    out = [default] * n_steps
    if not rates:
        return out
    if len(rates) >= n_steps:
        for i in range(n_steps):
            out[i] = max(1, int(round(rates[i] * JIFFY_MS))) or default
    elif len(rates) == n_frames:
        for i in range(n_steps):
            r = rates[steps[i] % len(rates)]
            out[i] = max(1, int(round(r * JIFFY_MS))) or default
    else:
        for i in range(min(n_steps, len(rates))):
            out[i] = max(1, int(round(rates[i] * JIFFY_MS))) or default
    return out


def _parse_fram(body: bytes) -> List[Frame]:
    frames: List[Frame] = []
    pos = 0
    while pos + 8 <= len(body):
        cid = body[pos:pos + 4]
        size = struct.unpack_from("<I", body, pos + 4)[0]
        chunk = body[pos + 8:pos + 8 + size]
        if cid in (b"icon", b"\x00\x00\x00\x00") and chunk:
            try:
                images = parse_icon(chunk)
            except CursorFormatError:
                images = []
            if images:
                frames.append(max(images, key=lambda f: f.area))
        pos += 8 + size + (size & 1)
    return frames


# --- single image decoding ---------------------------------------------------

def _decode_image(blob: bytes, fallback_w: int, fallback_h: int) -> Frame:
    if blob[:8] == PNG_SIGNATURE:
        w, h, rgba = _decode_png(blob)
        return Frame(w, h, 0, 0, rgba)
    return _decode_bmp(blob, fallback_w, fallback_h)


def _decode_bmp(blob: bytes, fallback_w: int, fallback_h: int) -> Frame:
    if len(blob) < 40:
        raise CursorFormatError("BMP payload too short")
    bi_size = struct.unpack_from("<I", blob, 0)[0]
    if bi_size < 40 or len(blob) < bi_size:
        raise CursorFormatError("bad BITMAPINFOHEADER")
    width, height2, _planes, bpp, compression = struct.unpack_from("<iiHHI", blob, 4)
    if compression not in (0, BI_BITFIELDS):
        raise CursorFormatError(f"unsupported BMP compression {compression}")
    height = abs(height2) // 2 or fallback_h
    width = width or fallback_w
    top_down = height2 < 0

    masks = None
    alpha_mask = 0
    pal_off = bi_size
    if bi_size == 40 and compression == BI_BITFIELDS:
        masks = struct.unpack_from("<III", blob, 40)
        pal_off = 52
    elif bi_size >= 52:
        rmask, gmask, bmask, alpha_mask = struct.unpack_from("<IIII", blob, 40)
        masks = (rmask, gmask, bmask)

    colors_used = struct.unpack_from("<I", blob, 32)[0]
    n_colors = 0
    if bpp <= 8:
        n_colors = colors_used or (1 << bpp)
    palette = []
    for i in range(n_colors):
        o = pal_off + i * 4
        if o + 3 > len(blob):
            break
        b, g, r, _ = struct.unpack_from("<BBBB", blob, o)
        palette.append((r, g, b))

    xor_off = pal_off + n_colors * 4
    xor_stride = ((width * bpp + 31) // 32) * 4
    and_off = xor_off + xor_stride * height
    and_stride = ((width + 31) // 32) * 4
    has_mask = and_off + and_stride * height <= len(blob)

    rgba = bytearray(width * height * 4)
    all_alpha_zero = True
    for y in range(height):
        row = (height - 1 - y) if not top_down else y
        base = xor_off + row * xor_stride
        mbase = and_off + row * and_stride
        for x in range(width):
            r = g = b = 0
            a = 255
            if bpp == 32:
                o = base + x * 4
                b, g, r, a = blob[o], blob[o + 1], blob[o + 2], blob[o + 3]
                if a:
                    all_alpha_zero = False
            elif bpp == 24:
                o = base + x * 3
                b, g, r = blob[o], blob[o + 1], blob[o + 2]
                a = 0 if _mask_bit(blob, mbase, x, has_mask) else 255
            elif bpp == 16:
                o = base + x * 2
                val = blob[o] | (blob[o + 1] << 8)
                r, g, b = _unpack16(val, masks)
                a = 0 if _mask_bit(blob, mbase, x, has_mask) else 255
            elif bpp in (8, 4, 2, 1):
                idx = _palette_index(blob, base, x, bpp)
                if idx < len(palette):
                    r, g, b = palette[idx]
                a = 0 if _mask_bit(blob, mbase, x, has_mask) else 255
            else:
                raise CursorFormatError(f"unsupported bit depth {bpp}")
            o = (y * width + x) * 4
            rgba[o] = r
            rgba[o + 1] = g
            rgba[o + 2] = b
            rgba[o + 3] = a

    # Old 32bpp icons sometimes carry an all-zero alpha channel; the AND mask
    # is then the real transparency.  Re-apply it in that case.
    if bpp == 32 and all_alpha_zero and has_mask:
        for y in range(height):
            row = (height - 1 - y) if not top_down else y
            mbase = and_off + row * and_stride
            for x in range(width):
                if _mask_bit(blob, mbase, x, has_mask):
                    rgba[(y * width + x) * 4 + 3] = 0

    return Frame(width, height, 0, 0, bytes(rgba))


def _mask_bit(blob: bytes, mbase: int, x: int, has_mask: bool) -> int:
    if not has_mask:
        return 0
    byte = blob[mbase + (x >> 3)]
    return (byte >> (7 - (x & 7))) & 1


def _palette_index(blob: bytes, base: int, x: int, bpp: int) -> int:
    if bpp == 8:
        return blob[base + x]
    per_byte = 8 // bpp
    byte = blob[base + x // per_byte]
    shift = 8 - bpp * (x % per_byte + 1)
    return (byte >> shift) & ((1 << bpp) - 1)


def _unpack16(value: int, masks):
    if masks:
        rmask, gmask, bmask = masks
    else:
        rmask, gmask, bmask = 0x7C00, 0x03E0, 0x001F
    return (_extract(value, rmask), _extract(value, gmask), _extract(value, bmask))


def _extract(value: int, mask: int) -> int:
    if not mask:
        return 0
    shift = (mask & -mask).bit_length() - 1
    field = (value & mask) >> shift
    top = mask >> shift
    return (field * 255 + top // 2) // top


# --- PNG ---------------------------------------------------------------------

def _decode_png(blob: bytes):
    if blob[:8] != PNG_SIGNATURE:
        raise CursorFormatError("not a PNG")
    pos = 8
    width = height = bitdepth = colortype = None
    interlace = 0
    idat = bytearray()
    palette = None
    trns = None
    while pos + 8 <= len(blob):
        length, ctype = struct.unpack_from(">I4s", blob, pos)
        pos += 8
        chunk = blob[pos:pos + length]
        pos += length + 4
        if ctype == b"IHDR":
            (width, height, bitdepth, colortype, _comp,
             _filt, interlace) = struct.unpack_from(">IIBBBBB", chunk, 0)
        elif ctype == b"PLTE":
            palette = chunk
        elif ctype == b"tRNS":
            trns = chunk
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    if width is None:
        raise CursorFormatError("PNG missing IHDR")
    if interlace:
        raise CursorFormatError("interlaced PNG is not supported")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colortype]
    raw = zlib.decompress(bytes(idat))
    stride = (width * channels * bitdepth + 7) // 8
    bpp = max(1, (channels * bitdepth) // 8)
    pixels = _unfilter(raw, height, stride, bpp)
    return width, height, _png_to_rgba(pixels, width, height, bitdepth,
                                       colortype, channels, palette, trns)


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytearray:
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        if pos >= len(raw):
            break
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(bpp, len(line)):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(len(line)):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(len(line)):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(len(line)):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def _png_to_rgba(pixels, width, height, bitdepth, colortype, channels,
                 palette, trns) -> bytes:
    rgba = bytearray(width * height * 4)
    stride = (width * channels * bitdepth + 7) // 8
    maxval = (1 << bitdepth) - 1 if bitdepth < 16 else 0xFFFF

    def sample(row: int, x: int, c: int) -> int:
        """Return one channel of one pixel as an 8-bit value."""
        bitpos = (x * channels + c) * bitdepth
        if bitdepth == 8:
            return pixels[row + bitpos // 8]
        if bitdepth == 16:
            return pixels[row + bitpos // 8]          # high byte ~= /257
        byte = pixels[row + bitpos // 8]
        shift = 8 - bitdepth - (bitpos % 8)
        return ((byte >> shift) & maxval) * 255 // maxval

    for y in range(height):
        row = y * stride
        for x in range(width):
            if colortype == 3:                          # palette
                idx = pixels[row + x * 2] if bitdepth == 16 else sample(row, x, 0)
                if palette and idx * 3 + 2 < len(palette):
                    r, g, b = palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]
                else:
                    r = g = b = 0
                a = trns[idx] if (trns and idx < len(trns)) else 255
            elif colortype in (0, 4):                   # greyscale (+alpha)
                v = sample(row, x, 0)
                r = g = b = v
                a = sample(row, x, 1) if colortype == 4 else 255
            else:                                       # RGB / RGBA
                r = sample(row, x, 0)
                g = sample(row, x, 1)
                b = sample(row, x, 2)
                a = sample(row, x, 3) if colortype == 6 else 255
            o = (y * width + x) * 4
            rgba[o] = r
            rgba[o + 1] = g
            rgba[o + 2] = b
            rgba[o + 3] = a
    return bytes(rgba)
