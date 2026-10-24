"""Bulk actions must only touch theme files, on desktop too (other MP3s in a media folder are the user's).
Run from the repo root:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m unittest discover tests"""
import os
import tempfile
import unittest

from api_controller import Api
from core.safety import theme_files_only


FILES = ("theme.mp3", "theme-music/Opening 1.mp3", "Season 1/theme-music/Opening.mp3",
         "Soundtrack/ost.mp3", "song.mp3", "Season 1/ep01.mkv")


class ThemeFilesOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = self.tmp.name
        self.show = os.path.join(self.library, "Show")
        for rel in FILES:
            path = os.path.join(self.show, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def remaining(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.show).replace(os.sep, "/")
                      for d, _, files in os.walk(self.show) for f in files)

    def test_filter_keeps_only_themes(self):
        paths = [os.path.join(self.show, rel) for rel in FILES]
        kept = [os.path.relpath(p, self.show).replace(os.sep, "/") for p in theme_files_only(paths)]
        self.assertEqual(kept, list(FILES[:3]))

    def test_clear_folder_keeps_other_files(self):
        result = Api().delete_music_folder(self.library, "all")
        self.assertEqual(result["status"], "success")
        self.assertEqual(self.remaining(), ["Season 1/ep01.mkv", "Soundtrack/ost.mp3", "song.mp3"])
        self.assertFalse(os.path.exists(os.path.join(self.show, "theme-music")))


if __name__ == "__main__":
    unittest.main()
