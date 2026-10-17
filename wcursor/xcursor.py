"""Read/write Xcursor theme files and resample cursor bitmaps.

File layout (all little-endian)::

    header : "Xcur" | header_size(16) | version(1) | ntoc
    toc    : (type=0xfffd0002, subtype=nominal_size, position) * ntoc
    chunk  : header_size(36) | type | subtype(nominal_size) | version(1)
             | width | height | xhot | yhot | delay | pixels(width*height*4)

Pixels are 32-bit **premultiplied** ARGB; as stored little-endian the four
bytes per pixel are ``B, G, R, A``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from os import PathLike
from typing import Iterable, List, Sequence

XCURSOR_IMAGE_TYPE = 0xFFFD0002
FILE_HEADER_SIZE = 16
CHUNK_HEADER_SIZE = 36
_MAX_DIM = 0x7FFF


class XcursorError(Exception):
    """Raised when a file is not a valid Xcursor image file."""


@dataclass
class Image:
    """A single Xcursor image (one frame at one nominal size)."""

    size: int              # nominal size the compositor matches against
    width: int
    height: int
    xhot: int
    yhot: int
    delay: int             # milliseconds until the next frame (0 = static)
    pixels: bytes          # premultiplied ARGB, bytes are B, G, R, A
    type: int = XCURSOR_IMAGE_TYPE

    def resized(self, size: int, **kw) -> "Image":
        return replace(self, size=size, **kw)


# --- file IO -----------------------------------------------------------------

def read(path: str | PathLike) -> List[Image]:
    with open(path, "rb") as fh:
        data = fh.read()
    return parse(data)


def parse(data: bytes) -> List[Image]:
    if len(data) < FILE_HEADER_SIZE or data[:4] != b"Xcur":
        raise XcursorError("not an Xcursor file (bad magic)")
    header_size, _version, ntoc = _unpack("<III", data, 4)
    if header_size < FILE_HEADER_SIZE:
        raise XcursorError(f"bad header size {header_size}")

    images: List[Image] = []
    off = FILE_HEADER_SIZE
    for _ in range(ntoc):
        ctype, subtype, pos = _unpack("<III", data, off)
        off += 12
        if ctype != XCURSOR_IMAGE_TYPE:
            continue
        if pos + CHUNK_HEADER_SIZE > len(data):
            continue
        _hsz, _t, _sub, _ver, w, h, xh, yh, delay = _unpack("<9I", data, pos)
        if w <= 0 or h <= 0 or w > _MAX_DIM or h > _MAX_DIM:
            continue
        need = w * h * 4
        px = data[pos + CHUNK_HEADER_SIZE: pos + CHUNK_HEADER_SIZE + need]
        if len(px) != need:
            continue
        images.append(Image(subtype, w, h, xh, yh, delay, px, ctype))
    if not images:
        raise XcursorError("no image chunks found")
    return images


def write(path: str | PathLike, images: Iterable[Image]) -> None:
    images = list(images)
    ntoc = len(images)
    header = _pack("<4sIII", b"Xcur", FILE_HEADER_SIZE, 1, ntoc)
    pos = FILE_HEADER_SIZE + ntoc * 12
    toc = bytearray()
    body = bytearray()
    for im in images:
        if im.width <= 0 or im.height <= 0:
            raise XcursorError("image has non-positive dimensions")
        expected = im.width * im.height * 4
        if len(im.pixels) != expected:
            raise XcursorError(
                f"pixel buffer is {len(im.pixels)} bytes, expected {expected}"
            )
        toc += _pack("<III", im.type, im.size, pos)
        chunk = _pack("<9I", CHUNK_HEADER_SIZE, im.type, im.size, 1,
                      im.width, im.height, im.xhot, im.yhot, im.delay)
        body += chunk
        body += im.pixels
        pos += len(chunk) + len(im.pixels)
    with open(path, "wb") as fh:
        fh.write(header + bytes(toc) + bytes(body))


def probe(path: str | PathLike) -> List[int]:
    """Return the sorted, unique nominal sizes stored in a cursor file."""
    return sorted({im.size for im in read(path)})


# --- colour helpers ----------------------------------------------------------

def premultiply(rgba: bytes) -> bytes:
    """Straight ``R,G,B,A`` bytes -> premultiplied ``B,G,R,A`` Xcursor pixels."""
    if len(rgba) % 4:
        raise ValueError("pixel buffer length must be a multiple of 4")
    out = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        r = rgba[i]
        g = rgba[i + 1]
        b = rgba[i + 2]
        a = rgba[i + 3]
        out[i] = (b * a + 127) // 255
        out[i + 1] = (g * a + 127) // 255
        out[i + 2] = (r * a + 127) // 255
        out[i + 3] = a
    return bytes(out)


def unpremultiply(argb: bytes) -> bytes:
    """Premultiplied ``B,G,R,A`` Xcursor pixels -> straight ``R,G,B,A`` bytes."""
    if len(argb) % 4:
        raise ValueError("pixel buffer length must be a multiple of 4")
    out = bytearray(len(argb))
    for i in range(0, len(argb), 4):
        b = argb[i]
        g = argb[i + 1]
        r = argb[i + 2]
        a = argb[i + 3]
        if a:
            out[i] = min(255, (r * 255 + a // 2) // a)
            out[i + 1] = min(255, (g * 255 + a // 2) // a)
            out[i + 2] = min(255, (b * 255 + a // 2) // a)
        out[i + 3] = a
    return bytes(out)


# --- resampling --------------------------------------------------------------

def _kcubic(t: float) -> float:
    t = abs(t)
    if t < 1.0:
        return 1.5 * t * t * t - 2.5 * t * t + 1.0
    if t < 2.0:
        return -0.5 * t * t * t + 2.5 * t * t - 4.0 * t + 2.0
    return 0.0


def _kbox(t: float) -> float:
    return 1.0 if -0.5 <= t < 0.5 else 0.0


def _resample_line(src: Sequence[float], dst_len: int, kernel, support: float):
    n = len(src)
    if n == 0 or dst_len <= 0:
        return [0.0] * max(dst_len, 0)
    scale = dst_len / n
    fscale = 1.0 if scale >= 1.0 else scale
    radius = support / fscale
    out = [0.0] * dst_len
    for i in range(dst_len):
        center = (i + 0.5) / scale - 0.5
        lo = max(0, int(math.floor(center - radius + 0.5)))
        hi = min(n - 1, int(math.ceil(center + radius - 0.5)))
        acc = 0.0
        total = 0.0
        for j in range(lo, hi + 1):
            w = kernel((j - center) * fscale)
            if w:
                acc += src[j] * w
                total += w
        out[i] = acc / total if total else 0.0
    return out


def _scale_hotspot(value: int, src: int, dst: int, limit: int) -> int:
    if src <= 0:
        return 0
    v = int(round(value * dst / src))
    return max(0, min(limit - 1, v)) if limit > 0 else 0


def scale_nearest(img: Image, size: int) -> Image:
    """Exact integer-ish nearest-neighbour scale (keeps pixel art crisp)."""
    tw = th = size
    w, h = img.width, img.height
    out = bytearray(tw * th * 4)
    for y in range(th):
        sy = min(h - 1, y * h // th)
        srow = sy * w * 4
        drow = y * tw * 4
        for x in range(tw):
            sx = min(w - 1, x * w // tw)
            si = srow + sx * 4
            out[drow + x * 4: drow + x * 4 + 4] = img.pixels[si:si + 4]
    return img.resized(
        size,
        width=tw,
        height=th,
        xhot=_scale_hotspot(img.xhot, w, tw, tw),
        yhot=_scale_hotspot(img.yhot, h, th, th),
        pixels=bytes(out),
    )


def scale_smooth(img: Image, size: int) -> Image:
    """High quality separable resample (area down / bicubic up)."""
    tw = th = size
    w, h = img.width, img.height
    if (tw, th) == (w, h):
        return img.resized(size, width=tw, height=th)
    up = tw >= w and th >= h
    kernel, support = (_kcubic, 2.0) if up else (_kbox, 0.5)

    px = img.pixels
    # horizontal pass -> tmp (tw x h)
    tmp = [0.0] * (tw * h * 4)
    for c in range(4):
        for y in range(h):
            base = y * w * 4 + c
            line = [px[base + x * 4] for x in range(w)]
            for x, v in enumerate(_resample_line(line, tw, kernel, support)):
                tmp[(y * tw + x) * 4 + c] = v
    # vertical pass -> out (tw x th)
    out = bytearray(tw * th * 4)
    for c in range(4):
        for x in range(tw):
            line = [tmp[(y * tw + x) * 4 + c] for y in range(h)]
            for y, v in enumerate(_resample_line(line, th, kernel, support)):
                out[(y * tw + x) * 4 + c] = 0 if v < 0 else 255 if v > 255 else int(v + 0.5)

    return img.resized(
        size,
        width=tw,
        height=th,
        xhot=_scale_hotspot(img.xhot, w, tw, tw),
        yhot=_scale_hotspot(img.yhot, h, th, th),
        pixels=bytes(out),
    )


def rescale(img: Image, size: int, method: str = "auto") -> Image:
    """Rescale an image to ``size``.

    ``method`` is one of ``auto`` (nearest for exact integer upscales, smooth
    otherwise), ``nearest`` or ``smooth``.
    """
    if not 0 < size <= _MAX_DIM:
        raise XcursorError(f"size out of range: {size}")
    w = img.width
    if method == "auto":
        integer_up = size > w and size % w == 0 and img.height == img.width
        method = "nearest" if integer_up else "smooth"
    if method == "nearest":
        return scale_nearest(img, size)
    if method == "smooth":
        return scale_smooth(img, size)
    raise XcursorError(f"unknown method: {method}")


def integer_multiples(width: int, up_to: int) -> List[int]:
    """Every exact multiple of ``width`` in ``(width, up_to]``."""
    return [width * k for k in range(2, up_to // width + 1)] if width else []


# --- small helpers -----------------------------------------------------------

def _unpack(fmt: str, data: bytes, off: int):
    import struct

    return struct.unpack_from(fmt, data, off)


def _pack(fmt: str, *values) -> bytes:
    import struct

    return struct.pack(fmt, *values)
