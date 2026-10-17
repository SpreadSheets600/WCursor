import tempfile
import unittest
from pathlib import Path

from wcursor import pack, theme, xcursor
from tests import synthetic


def _make_pack(directory: Path) -> pack.Pack:
    """A minimal two-cursor animated pack on disk."""
    directory.mkdir(parents=True, exist_ok=True)
    normal = synthetic.cur([(32, 32, 0, 0, synthetic.solid_rgba(32, 32, (255, 0, 0, 255)))])
    normal_frames = synthetic.ani([normal, normal], disp_rate=5)
    link = synthetic.cur([(32, 32, 4, 4, synthetic.solid_rgba(32, 32, (0, 255, 0, 255)))])
    link_frames = synthetic.ani([link], disp_rate=5)

    (directory / "Normal.ani").write_bytes(normal_frames)
    (directory / "Link.ani").write_bytes(link_frames)
    (directory / "install.inf").write_text(
        '[Strings]\nSCHEME_NAME="Test Cursor"\npointer = "Normal.ani"\nlink = "Link.ani"\n'
    )
    return pack.load_pack(directory)


class TestThemeBuild(unittest.TestCase):
    def test_build_creates_cursors_aliases_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_pack(Path(tmp) / "pack")
            out = Path(tmp) / "theme"
            built = theme.build(source, out, sizes=[32, 64], verbose=False)

            self.assertEqual(set(built), {"left_ptr", "hand2"})
            self.assertEqual(built["left_ptr"].frames, 2)
            self.assertEqual(built["left_ptr"].sizes, [32, 64])

            self.assertTrue((out / "index.theme").is_file())
            self.assertIn("Name=Test Cursor", (out / "index.theme").read_text())

            # canonical files carry the requested sizes
            self.assertEqual(xcursor.probe(out / "cursors" / "left_ptr"), [32, 64])

            # aliases are symlinks pointing at the canonical name
            alias = out / "cursors" / "default"
            self.assertTrue(alias.is_symlink())
            self.assertEqual(alias.readlink().name, "left_ptr")
            self.assertTrue((out / "cursors" / "pointer").is_symlink())

            # animation delays survive the round trip
            images = [i for i in xcursor.read(out / "cursors" / "left_ptr") if i.size == 32]
            self.assertEqual([i.delay for i in images], [83, 83])

    def test_default_ladder_includes_24_32_48_64(self):
        self.assertEqual(theme.resolve_sizes(None, 32), [24, 32, 48, 64])

    def test_parse_sizes(self):
        self.assertEqual(theme.parse_sizes("48, 24 ,32"), [24, 32, 48])
        self.assertEqual(theme.parse_sizes([64, 32]), [32, 64])
        with self.assertRaises(theme.ThemeError):
            theme.parse_sizes("0")
        with self.assertRaises(theme.ThemeError):
            theme.parse_sizes("9999")

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_pack(Path(tmp) / "pack")
            out = Path(tmp) / "theme"
            theme.build(source, out, sizes=[32], verbose=False)
            first = (out / "cursors" / "left_ptr").read_bytes()
            theme.build(source, out, sizes=[32], verbose=False)
            self.assertEqual((out / "cursors" / "left_ptr").read_bytes(), first)


class TestUpscale(unittest.TestCase):
    def test_add_sizes_from_best_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_pack(Path(tmp) / "pack")
            out = Path(tmp) / "theme"
            theme.build(source, out, sizes=[32], verbose=False)
            self.assertEqual(theme.read_theme_sizes(out), [32])

            theme.add_sizes(out, [48, 64], verbose=False)
            self.assertEqual(theme.read_theme_sizes(out), [32, 48, 64])
            # frames are preserved per size
            for size in (32, 48, 64):
                images = [i for i in xcursor.read(out / "cursors" / "left_ptr") if i.size == size]
                self.assertEqual(len(images), 2)

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_pack(Path(tmp) / "pack")
            out = Path(tmp) / "theme"
            theme.build(source, out, sizes=[32], verbose=False)
            before = (out / "cursors" / "left_ptr").read_bytes()
            theme.add_sizes(out, [64], dry_run=True, verbose=False)
            self.assertEqual((out / "cursors" / "left_ptr").read_bytes(), before)

    def test_non_square_source_is_normalised_then_upscaled_crisply(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "pack"
            pack_dir.mkdir(parents=True)
            # 32x33 art: one row too tall
            frame = synthetic.cur([(32, 33, 0, 0, synthetic.solid_rgba(32, 33, (9, 9, 9, 255)))])
            (pack_dir / "Normal.ani").write_bytes(synthetic.ani([frame]))
            (pack_dir / "install.inf").write_text('[Strings]\npointer = "Normal.ani"\n')
            source = pack.load_pack(pack_dir)

            out = Path(tmp) / "theme"
            theme.build(source, out, sizes=[32, 64], verbose=False)
            groups = theme.group_by_size(xcursor.read(out / "cursors" / "left_ptr"))
            self.assertEqual((groups[32][0].width, groups[32][0].height), (32, 32))
            # 64 must be an exact 2x of the normalised 32
            self.assertEqual(groups[64][0].pixels, xcursor.scale_nearest(groups[32][0], 64).pixels)

    def test_choose_source_size_prefers_largest_below(self):
        self.assertEqual(theme.choose_source_size([24, 32, 48], 64), 48)
        self.assertEqual(theme.choose_source_size([24, 32, 48], 40), 32)
        self.assertEqual(theme.choose_source_size([48, 64], 32), 48)

    def test_upscale_uses_recorded_native_for_exact_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _make_pack(Path(tmp) / "pack")
            out = Path(tmp) / "theme"
            theme.build(source, out, sizes=[24, 32], verbose=False)
            # the sidecar remembers the artwork's native size
            self.assertEqual(theme.native_sizes(out)["left_ptr"], 32)

            theme.add_sizes(out, [64], verbose=False)
            groups = theme.group_by_size(xcursor.read(out / "cursors" / "left_ptr"))
            # 64 must be an exact 2x of the native 32, not a resample of the 24
            expected = xcursor.scale_nearest(groups[32][0], 64)
            self.assertEqual(groups[64][0].pixels, expected.pixels)
            self.assertEqual(len(groups[64]), len(groups[32]))

            # and the sidecar is kept up to date
            self.assertEqual(theme.read_meta(out)["cursors"]["left_ptr"]["sizes"], [24, 32, 64])


if __name__ == "__main__":
    unittest.main()
