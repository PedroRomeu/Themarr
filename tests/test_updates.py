"""Update check: version comparison and how a GitHub release is read.
Run from the repo root:
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -m unittest discover tests"""
import unittest
from unittest import mock

from core import updates


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updates.parse_version("v1.14.0"), (1, 14, 0))
        self.assertEqual(updates.parse_version("1.15.0-beta"), (1, 15, 0))
        self.assertEqual(updates.parse_version(""), (0,))

    def test_order_is_numeric(self):
        self.assertLess(updates.parse_version("1.9.0"), updates.parse_version("1.14.0"))
        self.assertLess(updates.parse_version("v1.14.0"), updates.parse_version("1.14.1"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        updates._cache.update(time=0, result=None)

    def release(self, tag):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "tag_name": tag, "name": f"Themarr {tag}", "body": "## Notes", "html_url": "https://example.test/r",
            "assets": [{"name": f"Themarr_{tag}.zip", "browser_download_url": "https://example.test/z.zip", "size": 10}],
        }
        return response

    def test_newer_release(self):
        with mock.patch.object(updates, "APP_VERSION", "1.14.0"), \
             mock.patch.object(updates.requests, "get", return_value=self.release("v1.15.0")):
            result = updates.check_for_update(force=True)
        self.assertTrue(result["success"])
        self.assertTrue(result["newer"])
        self.assertEqual(result["latest"], "1.15.0")
        self.assertEqual(result["asset_url"], "https://example.test/z.zip")

    def test_same_release_is_not_newer(self):
        with mock.patch.object(updates, "APP_VERSION", "1.14.0"), \
             mock.patch.object(updates.requests, "get", return_value=self.release("v1.14.0")):
            self.assertFalse(updates.check_for_update(force=True)["newer"])

    def test_offline(self):
        with mock.patch.object(updates.requests, "get", side_effect=OSError("offline")):
            result = updates.check_for_update(force=True)
        self.assertFalse(result["success"])
        self.assertIn("offline", result["message"])

    def test_source_checkout_cannot_self_update(self):
        self.assertFalse(updates.can_self_update())
        self.assertFalse(updates.install_update()["success"])


if __name__ == "__main__":
    unittest.main()
