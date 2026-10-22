import os
import tempfile
import unittest
from pathlib import Path

from wcursor import pack
from tests import synthetic

INF = """\
[Version]
signature="$CHICAGO$"

[Strings]
SCHEME_NAME="Frieren Cursor ver 1.0.0"
pointer = "Frieren normal.ani"
busy    = "Frieren busy.ani"
work    = "Frieren work.ani"
unavailiable = "Frieren unavailable.ani"

[Scheme.Reg]
"""


class TestInfParsing(unittest.TestCase):
    def test_parse_inf_sections(self):
        sections = pack.parse_inf(INF)
        self.assertIn("strings", sections)
        self.assertEqual(sections["strings"]["scheme_name"], "Frieren Cursor ver 1.0.0")
        self.assertEqual(sections["strings"]["pointer"], "Frieren normal.ani")

    def test_clean_name_strips_version_and_bad_chars(self):
        self.assertEqual(pack.clean_name("Frieren Cursor ver 1.0.0"), "Frieren Cursor")
        self.assertEqual(pack.clean_name('"Chibi Chisa"'), "Chibi Chisa")
        self.assertEqual(pack.clean_name("a/b:c"), "a-b-c")
        self.assertEqual(pack.clean_name("  "), "cursor-theme")


class TestDiscovery(unittest.TestCase):
    def _write(self, directory, name, data=b"x"):
        path = Path(directory) / name
        path.write_bytes(data)
        return path

    def test_mapping_from_inf(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "install.inf", INF.encode())
            self._write(tmp, "Frieren normal.ani")
            self._write(tmp, "Frieren busy.ani")
            self._write(tmp, "Frieren work.ani")
            self._write(tmp, "Frieren unavailable.ani")
            self._write(tmp, "extra.ani")
            result = pack.load_pack(tmp)
            self.assertEqual(result.name, "Frieren Cursor")
            self.assertEqual(result.source, "inf")
            self.assertEqual(result.mapping["left_ptr"].name, "Frieren normal.ani")
            self.assertEqual(result.mapping["watch"].name, "Frieren busy.ani")
            self.assertEqual(result.mapping["left_ptr_watch"].name, "Frieren work.ani")
            self.assertEqual(result.mapping["not-allowed"].name, "Frieren unavailable.ani")

    def test_mapping_without_inf_uses_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "01-Normal.ani")
            self._write(tmp, "04-Help.ani")
            self._write(tmp, "13-Diagonal Resize 1.ani")
            result = pack.load_pack(tmp)
            self.assertEqual(result.source, "guess")
            self.assertEqual(result.mapping["left_ptr"].name, "01-Normal.ani")
            self.assertEqual(result.mapping["help"].name, "04-Help.ani")
            self.assertEqual(result.mapping["bd_double_arrow"].name, "13-Diagonal Resize 1.ani")

    def test_animated_folder_preferred_over_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            windows = Path(tmp) / "Windows"
            static = Path(tmp) / "Static"
            windows.mkdir()
            static.mkdir()
            self._write(windows, "Normal.ani")
            self._write(static, "Normal.cur")
            self.assertEqual(pack.choose_directory(Path(tmp)), windows)

    def test_ambiguous_folders_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("A", "B"):
                sub = Path(tmp) / name
                sub.mkdir()
                self._write(sub, "Normal.ani")
            with self.assertRaises(pack.PackError):
                pack.load_pack(tmp)

    def test_hand_keeps_link_and_move_keeps_arrow_when_no_palm(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "Normal.ani")
            link = self._write(tmp, "Link.ani")
            move = self._write(tmp, "Move.ani")
            result = pack.load_pack(tmp)
            self.assertEqual(result.mapping["hand2"], link)
            self.assertEqual(result.mapping["fleur"], move)

    def test_real_palm_is_preferred_for_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "Normal.ani")
            link = self._write(tmp, "Link.ani")
            self._write(tmp, "Move.ani")
            palm = self._write(tmp, "OpenHand.ani")
            result = pack.load_pack(tmp)
            self.assertEqual(result.mapping["fleur"], palm)
            self.assertEqual(result.mapping["hand2"], link)

    def test_single_file_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "Frieren busy.ani")
            result = pack.load_pack(path)
            self.assertEqual(result.source, "single")
            self.assertEqual(result.mapping, {"watch": path})

    def test_missing_path(self):
        with self.assertRaises(pack.PackError):
            pack.load_pack("/nonexistent/path/for/wcursor")


if __name__ == "__main__":
    unittest.main()
