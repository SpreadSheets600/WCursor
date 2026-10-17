import unittest

from wcursor import roles


class TestRoles(unittest.TestCase):
    def test_variants_map_to_canonical(self):
        cases = {
            "Arrow": "left_ptr",
            "pointer": "left_ptr",
            "Working": "left_ptr_watch",
            "work": "left_ptr_watch",
            "Busy": "watch",
            "Wait": "watch",
            "Precision": "crosshair",
            "cross": "crosshair",
            "Text": "xterm",
            "Handwriting": "pencil",
            "hand": "pencil",
            "Unavailable": "not-allowed",
            "unavailiable": "not-allowed",   # historical typo
            "SizeNWSE": "bd_double_arrow",
            "dgn1": "bd_double_arrow",
            "SizeNESW": "fd_double_arrow",
            "Move": "fleur",
            "Alternate": "center_ptr",
            "Link": "hand2",
            "Pin": "pin",
            "Person": "person",
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                self.assertEqual(roles.normalize_role(key), expected)

    def test_unknown_role(self):
        self.assertIsNone(roles.normalize_role("definitely-not-a-role"))

    def test_infer_role_from_filenames(self):
        cases = {
            "01-Normal.ani": "left_ptr",
            "08-Unavailable.ani": "not-allowed",
            "13-Diagonal Resize 1.ani": "bd_double_arrow",
            "14-Diagonal Resize 2.ani": "fd_double_arrow",
            "05-Text Select.ani": "xterm",
            "05-Text Select Alt.ani": "xterm",
            "03-Loading.ani": "left_ptr_watch",
            "Frieren busy.ani": "watch",
            "Frieren dgn1.ani": "bd_double_arrow",
            "11-Vertical Resize.ani": "sb_v_double_arrow",
            "16-Alternate Select.ani": "center_ptr",
            "09-Location Select.ani": "pin",
            "10-Person Select.ani": "person",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(roles.infer_role(name), expected)

    def test_aliases(self):
        self.assertIn("default", roles.aliases_for("left_ptr"))
        self.assertIn("hand", roles.aliases_for("hand2"))
        self.assertEqual(roles.aliases_for("pin"), [])

    def test_canonical_count(self):
        self.assertEqual(len(roles.CANONICAL), 17)
        self.assertEqual(len(set(roles.CANONICAL)), 17)


if __name__ == "__main__":
    unittest.main()
