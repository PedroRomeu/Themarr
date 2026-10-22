"""Checks for the parts of server mode that depend on how each server is set up.
Run from the repo root (UTF-8 output for the emoji logs):
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m unittest discover tests"""
import os
import re
import tempfile
import unittest
from unittest import mock

from core.config import _parse_path_map
from core import jellyfin
from core.jellyfin import local_media_folder, install_jellyfin_buttons, JS_INJECTOR_ID, BUTTONS_SCRIPT_NAME


class PathMapTests(unittest.TestCase):
    def test_parse(self):
        pairs = _parse_path_map(" /media=/data ; /media/tv=/data/TV\n bad ;=x;")
        self.assertEqual(pairs, [("/media/tv", "/data/TV"), ("/media", "/data")])

    def test_empty(self):
        self.assertEqual(_parse_path_map(None), [])


class LocalMediaFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        for rel in ("Animes/Frieren", "TV/Dark", "TV/Shared", "Movies/Shared", "Movies/Up (2009)"):
            os.makedirs(os.path.join(self.root, rel))

    def tearDown(self):
        self.tmp.cleanup()

    def local(self, *parts):
        return os.path.join(self.root, *parts)

    def test_same_path(self):
        self.assertEqual(local_media_folder(self.local("Animes", "Frieren"), self.root), self.local("Animes", "Frieren"))

    def test_other_mount_point_same_library_names(self):
        # Jellyfin: /media/Animes/Frieren, Themarr: <root>/Animes/Frieren
        self.assertEqual(local_media_folder("/media/Animes/Frieren", self.root), self.local("Animes", "Frieren"))

    def test_windows_style_path(self):
        self.assertEqual(local_media_folder(r"D:\Medias\TV\Dark", self.root), self.local("TV", "Dark"))

    def test_other_library_name_unique_media(self):
        # Jellyfin: /tvshows/Dark, Themarr mounted it as <root>/TV
        self.assertEqual(local_media_folder("/tvshows/Dark", self.root), self.local("TV", "Dark"))

    def test_ambiguous_media_name_needs_map(self):
        self.assertIsNone(local_media_folder("/tvshows/Shared", self.root))
        mapped = local_media_folder("/tvshows/Shared", self.root, [("/tvshows", self.local("TV"))])
        self.assertEqual(mapped, self.local("TV", "Shared"))

    def test_map_wins_over_tail(self):
        path_map = [("/srv/films", self.local("Movies"))]
        self.assertEqual(local_media_folder("/srv/films/Up (2009)", self.root, path_map), self.local("Movies", "Up (2009)"))

    def test_map_prefix_is_whole_folder(self):
        # /srv/tv must not map /srv/tvshows/...
        path_map = [("/srv/tv", self.local("Movies"))]
        self.assertEqual(local_media_folder("/srv/tvshows/Dark", self.root, path_map), self.local("TV", "Dark"))

    def test_never_the_root_or_outside(self):
        self.assertIsNone(local_media_folder(self.root, self.root))
        outside = tempfile.mkdtemp()
        try:
            self.assertIsNone(local_media_folder(outside, self.root))
        finally:
            os.rmdir(outside)

    def test_missing(self):
        self.assertIsNone(local_media_folder("/media/Animes/Nope", self.root))
        self.assertIsNone(local_media_folder("", self.root))

    def test_desktop_no_root(self):
        self.assertEqual(local_media_folder(self.local("TV", "Dark")), self.local("TV", "Dark"))
        self.assertIsNone(local_media_folder("/media/TV/Dark"))


class ButtonsScriptTests(unittest.TestCase):
    def script(self, public_url):
        import api_controller
        with mock.patch.object(api_controller, 'PUBLIC_URL', public_url):
            return api_controller.Api.jellyfin_buttons_script(None)

    def test_default_is_auto(self):
        self.assertIn("const THEMARR_URL_SETTING = \"\";", self.script(""))

    def test_public_url_is_quoted(self):
        script = self.script("https://themarr.example.com/x'y")
        self.assertIn('const THEMARR_URL_SETTING = "https://themarr.example.com/x\'y";', script)
        self.assertEqual(len(re.findall(r"THEMARR_URL_SETTING =", script)), 1)

    def test_no_server_specific_address(self):
        script = self.script("")
        self.assertNotRegex(script, r"192\.168\.\d|ts\.net")


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


class InstallButtonsTests(unittest.TestCase):
    def run_install(self, plugins, config, post_status=204):
        posted = {}

        def fake_get(url, **kwargs):
            if url.endswith('/Plugins'):
                return FakeResponse(200, plugins)
            return FakeResponse(200, config)

        def fake_post(url, **kwargs):
            posted['url'] = url
            posted['json'] = kwargs['json']
            return FakeResponse(post_status)

        with mock.patch.object(jellyfin.requests, 'get', fake_get), mock.patch.object(jellyfin.requests, 'post', fake_post):
            result = install_jellyfin_buttons('http://jf:8096/', 'key', 'SCRIPT')
        return result, posted

    def test_missing_plugin(self):
        result, posted = self.run_install([{"Id": "other", "Name": "x"}], {})
        self.assertFalse(result["success"])
        self.assertEqual(posted, {})

    def test_adds_and_keeps_other_scripts(self):
        other = {"Name": "Mine", "Script": "x", "Enabled": False, "RequiresAuthentication": False}
        config = {"CustomJavaScripts": [other], "PluginJavaScripts": [{"Id": "p"}], "AllowExternalScriptUrls": True}
        result, posted = self.run_install([{"Id": JS_INJECTOR_ID, "Version": "3.5.0.0"}], config)
        self.assertTrue(result["success"])
        self.assertEqual(posted['url'], f"http://jf:8096/Plugins/{JS_INJECTOR_ID}/Configuration")
        saved = posted['json']
        self.assertEqual(saved["CustomJavaScripts"][0], other)
        self.assertEqual(saved["CustomJavaScripts"][1],
                         {"Name": BUTTONS_SCRIPT_NAME, "Script": "SCRIPT", "Enabled": True, "RequiresAuthentication": True})
        self.assertEqual(saved["PluginJavaScripts"], [{"Id": "p"}])
        self.assertTrue(saved["AllowExternalScriptUrls"])

    def test_updates_existing_entry(self):
        config = {"CustomJavaScripts": [{"Name": BUTTONS_SCRIPT_NAME, "Script": "OLD", "Enabled": False, "Module": False}]}
        dashed = f"{JS_INJECTOR_ID[:8]}-{JS_INJECTOR_ID[8:12]}-{JS_INJECTOR_ID[12:16]}-{JS_INJECTOR_ID[16:20]}-{JS_INJECTOR_ID[20:]}"
        result, posted = self.run_install([{"Id": dashed}], config)
        self.assertTrue(result["success"])
        self.assertIn("updated", result["message"])
        scripts = posted['json']["CustomJavaScripts"]
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0]["Script"], "SCRIPT")
        self.assertTrue(scripts[0]["Enabled"])
        self.assertFalse(scripts[0]["Module"])

    def test_save_rejected(self):
        result, _ = self.run_install([{"Id": JS_INJECTOR_ID}], {"CustomJavaScripts": []}, post_status=400)
        self.assertFalse(result["success"])


if __name__ == '__main__':
    unittest.main()
