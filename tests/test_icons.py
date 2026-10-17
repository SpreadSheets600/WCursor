import unittest

from wcursor import icons
from tests import synthetic


class TestIconContainers(unittest.TestCase):
    def test_cur_bmp32_roundtrip(self):
        rgba = bytes([
            255, 0, 0, 255,    0, 255, 0, 128,
            0, 0, 255, 0,      10, 20, 30, 255,
        ])
        data = synthetic.cur([(2, 2, 1, 0, rgba)])
        frames = icons.parse(data)
        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual((frame.width, frame.height), (2, 2))
        self.assertEqual((frame.xhot, frame.yhot), (1, 0))
        self.assertEqual(frame.rgba, rgba)

    def test_cur_png_roundtrip(self):
        rgba = synthetic.solid_rgba(4, 4, (200, 100, 50, 255))
        data = synthetic.cur([(4, 4, 2, 2, rgba)], use_png=True)
        frame = icons.parse(data)[0]
        self.assertEqual((frame.width, frame.height), (4, 4))
        self.assertEqual((frame.xhot, frame.yhot), (2, 2))
        self.assertEqual(frame.rgba, rgba)

    def test_bmp24_uses_and_mask_for_alpha(self):
        # 2x1: first pixel opaque black, second transparent (mask bit set)
        header = synthetic.bmp24(2, 1, bytes([0, 0, 0, 255, 255, 255]), opaque=[True, False])
        import struct
        data = (struct.pack("<HHH", 0, 2, 1)
                + struct.pack("<BBBBHHII", 2, 1, 0, 0, 0, 0, len(header), 22)
                + header)
        frame = icons.parse(data)[0]
        self.assertEqual(frame.rgba[3], 255)
        self.assertEqual(frame.rgba[7], 0)

    def test_ani_frame_count_and_default_delay(self):
        frames = [synthetic.cur([(2, 2, 0, 0, synthetic.solid_rgba(2, 2, (i, 0, 0, 255)))])
                  for i in (10, 20, 30)]
        playback = icons.parse(synthetic.ani(frames, disp_rate=5))
        self.assertEqual(len(playback), 3)
        self.assertEqual([f.delay for f in playback], [83, 83, 83])
        self.assertEqual(playback[2].rgba, icons.parse(frames[2])[0].rgba)

    def test_ani_rate_chunk(self):
        frames = [synthetic.cur([(1, 1, 0, 0, synthetic.solid_rgba(1, 1, (0, 0, 0, 255)))])
                  for _ in range(2)]
        playback = icons.parse(synthetic.ani(frames, rates=[3, 10]))
        self.assertEqual([f.delay for f in playback], [50, 167])

    def test_ani_seq_chunk_reorders_frames(self):
        frames = [synthetic.cur([(1, 1, 0, 0, synthetic.solid_rgba(1, 1, (v, 0, 0, 255)))])
                  for v in (11, 22)]
        playback = icons.parse(synthetic.ani(frames, seq=[1, 0, 1]))
        self.assertEqual([f.rgba[0] for f in playback], [22, 11, 22])

    def test_rejects_garbage(self):
        with self.assertRaises(icons.CursorFormatError):
            icons.parse(b"not a cursor at all")


if __name__ == "__main__":
    unittest.main()
