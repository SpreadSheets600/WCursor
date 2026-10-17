import os
import tempfile
import unittest

from wcursor import xcursor


def _img(size=2, **kw):
    width = height = size
    defaults = dict(
        size=size,
        width=width,
        height=height,
        xhot=0,
        yhot=0,
        delay=0,
        pixels=bytes([10, 20, 30, 255]) * (width * height),
    )
    defaults.update(kw)
    return xcursor.Image(**defaults)


class TestReadWrite(unittest.TestCase):
    def test_roundtrip_is_byte_identical(self):
        images = [_img(2, delay=0), _img(2, delay=83), _img(4, xhot=2, yhot=1)]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "left_ptr")
            xcursor.write(path, images)
            back = xcursor.read(path)
        self.assertEqual(len(back), 3)
        for a, b in zip(images, back):
            self.assertEqual(
                (a.size, a.width, a.height, a.xhot, a.yhot, a.delay, a.pixels),
                (b.size, b.width, b.height, b.xhot, b.yhot, b.delay, b.pixels),
            )

    def test_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c")
            xcursor.write(path, [_img(24), _img(32), _img(64)])
            self.assertEqual(xcursor.probe(path), [24, 32, 64])

    def test_write_rejects_bad_buffer(self):
        bad = _img(2, pixels=b"\x00")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(xcursor.XcursorError):
                xcursor.write(os.path.join(tmp, "x"), [bad])

    def test_read_rejects_non_xcursor(self):
        with self.assertRaises(xcursor.XcursorError):
            xcursor.parse(b"nope")


class TestColour(unittest.TestCase):
    def test_premultiply_is_bgra(self):
        # straight R,G,B,A = 255,128,0,128 -> B,G,R,A premultiplied
        self.assertEqual(list(xcursor.premultiply(bytes([255, 128, 0, 128]))), [0, 64, 128, 128])

    def test_premultiply_unpremultiply_roundtrip(self):
        straight = bytes([255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 0, 12, 34, 56, 200])
        back = xcursor.unpremultiply(xcursor.premultiply(straight))
        for i in range(0, len(straight), 4):
            if straight[i + 3] == 0:
                self.assertEqual(back[i + 3], 0)
                continue
            for c in range(3):
                self.assertLessEqual(abs(straight[i + c] - back[i + c]), 2)


class TestRescale(unittest.TestCase):
    def _checker(self, size=2):
        px = bytearray()
        for y in range(size):
            for x in range(size):
                v = 255 if (x + y) % 2 else 0
                px += bytes([v, v, v, 255])
        return _img(size, pixels=bytes(px))

    def test_nearest_2x_is_exact_block_replication(self):
        src = self._checker(2)
        out = xcursor.rescale(src, 4, "nearest")
        self.assertEqual((out.width, out.height), (4, 4))
        for y in range(4):
            for x in range(4):
                o = (y * 4 + x) * 4
                self.assertEqual(
                    out.pixels[o:o + 4],
                    src.pixels[((y // 2) * 2 + (x // 2)) * 4:((y // 2) * 2 + (x // 2)) * 4 + 4],
                )

    def test_auto_uses_pixel_for_fractional_upscale(self):
        src = self._checker(4)
        auto = xcursor.rescale(src, 6, "auto")
        pixel = xcursor.rescale(src, 6, "pixel")
        self.assertEqual(auto.pixels, pixel.pixels)
        self.assertEqual(auto.size, 6)

    def test_hotspot_scales(self):
        src = _img(32, xhot=16, yhot=8)
        self.assertEqual((xcursor.rescale(src, 64).xhot, xcursor.rescale(src, 64).yhot), (32, 16))
        self.assertEqual((xcursor.rescale(src, 24).xhot, xcursor.rescale(src, 24).yhot), (12, 6))

    def test_hotspot_stays_in_bounds(self):
        src = _img(32, xhot=31, yhot=31)
        out = xcursor.rescale(src, 24)
        self.assertLess(out.xhot, 24)
        self.assertLess(out.yhot, 24)

    def test_unknown_method(self):
        with self.assertRaises(xcursor.XcursorError):
            xcursor.rescale(_img(2), 4, "bicubic")


if __name__ == "__main__":
    unittest.main()
