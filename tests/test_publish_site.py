import tempfile
import time
import unittest
from pathlib import Path

from scripts.live.publish_site import (
    LOADER_LINE,
    PUBLISH_MARKER,
    PUBLISH_MIN_INTERVAL_SECONDS,
    publish_due,
    stage_site,
    static_index,
)


class StageSiteTests(unittest.TestCase):
    def test_fighter_assets_are_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site.mkdir()
            stage_site(site)
            self.assertTrue((site / "app.js").exists())
            self.assertTrue((site / "assets" / "fighters" / "manifest.json").exists())


class StaticIndexTests(unittest.TestCase):
    def test_flag_is_injected_before_the_data_loader(self):
        html = f"<html><script>\n{LOADER_LINE}\n</script></html>"
        out = static_index(html)
        self.assertIn("window.STATIC_SITE = true;", out)
        self.assertLess(out.index("STATIC_SITE"), out.index("cacheBust"))

    def test_unexpected_index_shape_fails_loudly(self):
        with self.assertRaises(SystemExit):
            static_index("<html>changed</html>")


class PublishDueTests(unittest.TestCase):
    def test_due_when_no_marker(self):
        if PUBLISH_MARKER.exists():
            marker_age = time.time() - PUBLISH_MARKER.stat().st_mtime
            expected = marker_age >= PUBLISH_MIN_INTERVAL_SECONDS
            self.assertEqual(publish_due(), expected)
        else:
            self.assertTrue(publish_due())

    def test_throttle_window_respected(self):
        if not PUBLISH_MARKER.exists():
            self.skipTest("no marker on this machine yet")
        fresh = PUBLISH_MARKER.stat().st_mtime + 1
        self.assertFalse(publish_due(now=fresh))
        later = PUBLISH_MARKER.stat().st_mtime + PUBLISH_MIN_INTERVAL_SECONDS + 1
        self.assertTrue(publish_due(now=later))


if __name__ == "__main__":
    unittest.main()
