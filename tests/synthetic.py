"""Build tiny synthetic Windows cursor files for the test-suite (no deps)."""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def solid_rgba(width: int, height: int, colour) -> bytes:
    """Row-major straight RGBA for a solid image."""
    return bytes(colour) * (width * height)


def bmp32(width: int, height: int, rgba: bytes, top_down: bool = False) -> bytes:
    """A BITMAPINFOHEADER + 32bpp BGRA + AND mask (as used inside .cur)."""
    xor = bytearray()
    rows = range(height) if top_down else range(height - 1, -1, -1)
    for y in rows:
        for x in range(width):
            o = (y * width + x) * 4
            r, g, b, a = rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]
            xor += bytes((b, g, r, a))
    and_stride = ((width + 31) // 32) * 4
    and_mask = bytes(and_stride * height)          # no bits set = fully opaque
    bi_height = -height if top_down else height * 2
    header = struct.pack(
        "<IiiHHIIiiII", 40, width, bi_height, 1, 32, 0,
        len(xor) + len(and_mask), 0, 0, 0, 0,
    )
    return bytes(header) + bytes(xor) + and_mask


def bmp24(width: int, height: int, rgb: bytes, opaque=None) -> bytes:
    """A 24bpp BMP whose transparency comes from the AND mask."""
    xor = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            o = (y * width + x) * 3
            xor += bytes((rgb[o + 2], rgb[o + 1], rgb[o]))
        xor += b"\x00" * ((-width * 3) % 4)
    and_stride = ((width + 31) // 32) * 4
    and_mask = bytearray(and_stride * height)
    if opaque is not None:
        for y in range(height):
            for x in range(width):
                if not opaque[y * width + x]:
                    row = height - 1 - y
                    and_mask[row * and_stride + (x >> 3)] |= 0x80 >> (x & 7)
    header = struct.pack(
        "<IiiHHIIiiII", 40, width, height * 2, 1, 24, 0,
        len(xor) + len(and_mask), 0, 0, 0, 0,
    )
    return bytes(header) + bytes(xor) + bytes(and_mask)


def png(width: int, height: int, rgba: bytes) -> bytes:
    """A minimal non-interlaced 8-bit RGBA PNG."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw += b"\x00"
        raw += rgba[y * width * 4:(y + 1) * width * 4]
    return (PNG_SIGNATURE + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def cur(images, use_png: bool = False) -> bytes:
    """ICONDIR + ICONDIRENTRY*: ``images`` is (w, h, xhot, yhot, rgba)."""
    blobs = []
    for width, height, xhot, yhot, rgba in images:
        data = png(width, height, rgba) if use_png else bmp32(width, height, rgba)
        blobs.append((width, height, xhot, yhot, data))
    offset = 6 + 16 * len(blobs)
    entries = b""
    body = b""
    for width, height, xhot, yhot, data in blobs:
        entries += struct.pack("<BBBBHHII", width % 256, height % 256, 0, 0,
                               xhot, yhot, len(data), offset)
        offset += len(data)
        body += data
    return struct.pack("<HHH", 0, 2, len(blobs)) + entries + body


def ani(frame_blobs, rates=None, disp_rate: int = 5, seq=None) -> bytes:
    """RIFF/ACON wrapping ``frame_blobs`` (each already a .cur) as ``icon`` chunks."""
    icons = b""
    for blob in frame_blobs:
        icons += b"icon" + struct.pack("<I", len(blob)) + blob
        if len(blob) % 2:
            icons += b"\x00"
    fram = b"fram" + icons
    list_chunk = b"LIST" + struct.pack("<I", len(fram)) + fram

    n = len(frame_blobs)
    n_steps = len(seq) if seq is not None else n
    anih = struct.pack("<9I", 36, n, n_steps, 32, 32, 32, 1, disp_rate, 1)
    body = b"ACON" + b"anih" + struct.pack("<I", len(anih)) + anih
    if rates is not None:
        raw = struct.pack("<%dI" % len(rates), *rates)
        body += b"rate" + struct.pack("<I", len(raw)) + raw
    if seq is not None:
        raw = struct.pack("<%dI" % len(seq), *seq)
        body += b"seq " + struct.pack("<I", len(raw)) + raw
    body += list_chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body
