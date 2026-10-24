"""Bulk actions must only touch theme files, on desktop too (other MP3s in a media folder are the user's).
Run from the repo root:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m unittest discover tests"""
import os
import tempfile
import unittest

from api_controller import remove_theme_files, theme_files_in, _media_entry
from core.safety import theme_files_only


FILES = ("theme.mp3", "theme-music/Opening 1.mp3", "Season 1/theme-music/Opening.mp3",
         "Soundtrack/ost.mp3", "song.mp3", "Season 1/ep01.mkv")


class ThemeFilesOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.show = os.path.join(self.tmp.name, "Show")
        for rel in FILES:
            path = os.path.join(self.show, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def rel(self, paths):
        return sorted(os.path.relpath(p, self.show).replace(os.sep, "/") for p in paths)

    def remaining(self):
        return self.rel(os.path.join(d, f) for d, _, files in os.walk(self.show) for f in files)

    def test_filter_keeps_only_themes(self):
        paths = [os.path.join(self.show, rel) for rel in FILES]
        self.assertEqual(self.rel(theme_files_only(paths)), sorted(FILES[:3]))
        self.assertEqual(self.rel(theme_files_in(self.show)), sorted(FILES[:3]))

    def test_remove_keeps_other_files(self):
        self.assertEqual(remove_theme_files(self.show), 3)
        self.assertEqual(self.remaining(), ["Season 1/ep01.mkv", "Soundtrack/ost.mp3", "song.mp3"])
        self.assertFalse(os.path.exists(os.path.join(self.show, "theme-music")))

    def test_media_entry_lists_main_and_season_themes(self):
        entry = _media_entry(self.show)
        self.assertEqual(entry["media_name"], "Show")
        self.assertEqual(sorted((t["location_type"], t["file_name"]) for t in entry["tracks"]), [
            ("Main Theme (Folder)", "Opening 1.mp3"), ("Main Theme (Single)", "theme.mp3"), ("Season 1", "Opening.mp3")])


if __name__ == "__main__":
    unittest.main()
