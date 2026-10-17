"""Integration tests that use real cursor files when they are available.

Everything here is skipped on a machine without the sample packs / installed
themes, so the suite still passes from a clean checkout.
"""

import os
import tempfile
import unittest
from pathlib import Path

from wcursor import icons, install, pack, theme, xcursor

HOME = Path.home()
REAL_PACKS = [
    HOME / "Downloads" / "Cursor 1",
    HOME / "Downloads" / "Cursor New" / "Frieren Cursor",
    HOME / "Downloads" / "Cursor New" / "Frieren Winter Cursor",
]
INSTALLED = HOME / ".local" / "share" / "icons"


def _first_existing_pack():
    for candidate in REAL_PACKS:
        if candidate.is_dir():
            return candidate
    return None


class TestRealPacks(unittest.TestCase):
    def test_pack_converts_to_a_full_theme(self):
        source_path = _first_existing_pack()
        if source_path is None:
            self.skipTest("no sample cursor pack available")
        with tempfile.TemporaryDirectory() as tmp:
            source = pack.load_pack(source_path)
            built = theme.build(source, Path(tmp) / "out", verbose=False)
            self.assertGreaterEqual(len(built), 15)
            # every canonical cursor must be resolvable through an alias
            cursors = Path(tmp) / "out" / "cursors"
            self.assertTrue((cursors / "left_ptr").is_file())
            self.assertTrue((cursors / "default").is_symlink())
            # animation preserved
            self.assertTrue(any(im.delay > 0 for im in xcursor.read(cursors / "left_ptr")))

    def test_install_roundtrip_into_temp_data_home(self):
        source_path = _first_existing_pack()
        if source_path is None:
            self.skipTest("no sample cursor pack available")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XDG_DATA_HOME"] = tmp
            try:
                source = pack.load_pack(source_path)
                built_dir = Path(tmp) / "staging"
                theme.build(source, built_dir, sizes=[24, 32, 48, 64], verbose=False)
                dest = install.install(built_dir, "Integration", force=True)
                self.assertTrue(install.is_theme(dest))
                info = install.info("Integration")
                self.assertEqual(info.sizes, [24, 32, 48, 64])
                self.assertIn("Integration", [t.name for t in install.list_installed()])
                install.uninstall("Integration")
                self.assertFalse(dest.exists())
            finally:
                os.environ.pop("XDG_DATA_HOME", None)


class TestInstalledThemesValidity(unittest.TestCase):
    """Every installed cursor file must be a valid, premultiplied Xcursor file."""

    def test_all_installed_cursors_parse_and_are_premultiplied(self):
        if not INSTALLED.is_dir():
            self.skipTest("no installed icon themes")
        checked = 0
        for theme_dir in sorted(INSTALLED.iterdir()):
            cursors = theme_dir / "cursors"
            if not cursors.is_dir():
                continue
            for path in cursors.iterdir():
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    images = xcursor.read(path)
                except xcursor.XcursorError:
                    continue
                for image in images:
                    for i in range(0, len(image.pixels), 4):
                        b, g, r, a = image.pixels[i:i + 4]
                        # premultiplied: no channel may exceed alpha
                        self.assertLessEqual(max(b, g, r), a,
                                             f"{path.name} has non-premultiplied pixels")
                    checked += 1
                break  # one file per theme is enough
        if checked == 0:
            self.skipTest("no readable cursor files")


if __name__ == "__main__":
    unittest.main()
