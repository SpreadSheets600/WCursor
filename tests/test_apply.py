import unittest

from wcursor import apply


class TestTextHelpers(unittest.TestCase):
    def test_set_ini_key_replaces(self):
        text = "[Settings]\ngtk-cursor-theme-size=64\n"
        self.assertEqual(apply._set_ini_key(text, "gtk-cursor-theme-size", "48"),
                         "[Settings]\ngtk-cursor-theme-size=48\n")

    def test_set_ini_key_appends(self):
        self.assertEqual(apply._set_ini_key("[Settings]\n", "gtk-cursor-theme-name", "X"),
                         "[Settings]\ngtk-cursor-theme-name=X\n")

    def test_set_ini_key_matches_existing_spacing(self):
        text = "  gtk-cursor-theme-name = Old\n"
        self.assertEqual(apply._set_ini_key(text, "gtk-cursor-theme-name", "Chisa"),
                         "  gtk-cursor-theme-name =Chisa\n")

    def test_set_colon_key(self):
        text = "Xcursor.theme: Old\nXcursor.size: 24\n"
        self.assertEqual(apply._set_colon_key(text, "Xcursor.theme", "Chisa"),
                         "Xcursor.theme: Chisa\nXcursor.size: 24\n")


class TestDmsKdl(unittest.TestCase):
    def test_template_renders_dms_format(self):
        text = apply.DMS_CURSOR_KDL_TEMPLATE.replace("{theme}", "Chisa").replace("{size}", "64")
        self.assertIn('xcursor-theme "Chisa"', text)
        self.assertIn("xcursor-size 64", text)
        self.assertTrue(text.startswith("// ! DO NOT EDIT !"))


class TestApplyDryRun(unittest.TestCase):
    def test_dry_run_reports_without_writing(self):
        before = {}
        for path in (apply.DMS_SETTINGS, apply.XRDB, apply.ICONS_DEFAULT,
                     apply.GTK3, apply.GTK4, apply.DMS_CURSOR_KDL):
            backup = path.with_name(path.name + apply.BACKUP_SUFFIX)
            before[path] = (path.stat().st_mtime_ns if path.exists() else None, backup.exists())

        steps = apply.apply_cursor("Chisa", 64, dry_run=True)

        self.assertTrue(steps)
        allowed = {"updated", "unchanged", "would update", "skipped", "error"}
        for step in steps:
            self.assertIn(step.status, allowed)
        # nothing on disk moved, and no backups were created
        for path, (mtime, backup_existed) in before.items():
            now = path.stat().st_mtime_ns if path.exists() else None
            self.assertEqual(now, mtime, f"{path} was modified during a dry run")
            backup = path.with_name(path.name + apply.BACKUP_SUFFIX)
            self.assertEqual(backup.exists(), backup_existed)
        self.assertTrue(any(s.status == "would update" for s in steps))


if __name__ == "__main__":
    unittest.main()
