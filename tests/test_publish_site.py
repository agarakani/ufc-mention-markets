import json
import re
import shutil
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from scripts.live.publish_site import (
    DASHBOARD,
    LOADER_LINE,
    PUBLISH_LIVE_INTERVAL_SECONDS,
    PUBLISH_IDLE_INTERVAL_SECONDS,
    PUBLISH_MARKER,
    PUBLISH_MIN_INTERVAL_SECONDS,
    SITE_FILES,
    publish_due,
    publish_interval_seconds,
    stage_site,
    static_index,
)


def test_publication_waits_for_committed_page_assets(monkeypatch):
    from scripts.live import publish_site
    calls = []

    def changed(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(stdout=" M dashboard/styles.css\n")

    monkeypatch.setattr(publish_site.subprocess, "run", changed)
    assert publish_site.publish(quiet=True) == "page changes are uncommitted; keeping the published site"
    assert len(calls) == 1
    assert "dashboard/styles.css" in calls[0]
    assert "dashboard/data.js" not in calls[0]


def test_generated_snapshot_does_not_block_publication(monkeypatch):
    from scripts.live import publish_site
    monkeypatch.setattr(publish_site.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    assert publish_site.page_source_is_clean()


class PublishIntervalTests(unittest.TestCase):
    def test_live_vs_idle(self):
        today = "2026-07-19"
        self.assertEqual(
            publish_interval_seconds(today, ["2026-07-19", "2026-07-26"]),
            PUBLISH_LIVE_INTERVAL_SECONDS,
        )
        self.assertEqual(
            publish_interval_seconds(today, ["2026-07-26"]),
            PUBLISH_IDLE_INTERVAL_SECONDS,
        )
        self.assertEqual(publish_interval_seconds(today, []), PUBLISH_IDLE_INTERVAL_SECONDS)


class StageSiteTests(unittest.TestCase):
    def test_site_files_are_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "dashboard"
            source.mkdir()
            for name in ["index.html", *SITE_FILES]:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name == "data.js":
                    payload = {"tapes": [], "trades": [], "fighters": {},
                               "performance": {"equity": [], "official_trades": 0}}
                    path.write_text("window.UFC_MENTION_DASHBOARD_DATA = " + json.dumps(payload) + ";")
                else:
                    shutil.copyfile(DASHBOARD / name, path)
            site = Path(tmp) / "site"
            site.mkdir()
            with patch("scripts.live.publish_site.DASHBOARD", source):
                stage_site(site)
            self.assertTrue((site / "app.js").exists())
            self.assertTrue((site / "styles.css").exists())
            self.assertTrue((site / ".nojekyll").exists())
            # every module the page loads ships with it
            self.assertTrue((site / "src" / "board.js").exists())
            self.assertTrue((site / "src" / "palette.js").exists())

    def test_every_script_the_page_loads_is_published(self):
        html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        block = re.search(r"const files = \[(.*?)\];", html, re.S)
        self.assertIsNotNone(block, "index.html loader list changed shape")
        wanted = re.findall(r'"([^"]+\.js)"', block.group(1))
        for name in wanted:
            self.assertIn(name, SITE_FILES, f"{name} is loaded by index.html but not in SITE_FILES")
            self.assertTrue((DASHBOARD / name).is_file() or name == "data.js")

    def test_every_stylesheet_link_is_published(self):
        html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
        links = re.findall(r'<link\b[^>]*href="([^"?]+\.css)(?:\?[^"]*)?"[^>]*>', html)
        self.assertTrue(links, "No stylesheet links found in index.html")
        for name in links:
            if "://" not in name:
                self.assertIn(name, SITE_FILES)
                self.assertTrue((DASHBOARD / name).is_file())


class StaticIndexTests(unittest.TestCase):
    def test_flag_is_injected_before_the_data_loader(self):
        html = f"<html><script>\n{LOADER_LINE}\n</script></html>"
        out = static_index(html)
        self.assertIn("window.STATIC_SITE = true;", out)
        self.assertLess(out.index("STATIC_SITE"), out.index("cacheBust"))

    def test_stylesheet_link_is_version_busted(self):
        html = f'<link rel="stylesheet" href="base.css"><link rel="stylesheet" href="styles.css"><script>\n{LOADER_LINE}\n</script>'
        out = static_index(html, version=12345)
        self.assertIn('href="base.css?v=12345"', out)
        self.assertIn('href="styles.css?v=12345"', out)

    def test_unexpected_index_shape_fails_loudly(self):
        # ValueError, not SystemExit: SystemExit slips past the refresh
        # loop's `except Exception` and takes the whole service down.
        with self.assertRaises(ValueError):
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


def test_every_stylesheet_the_page_imports_is_published():
    """styles.css @imports base.css, so shipping one without the other breaks
    the live site while local dev looks fine."""
    import re
    from pathlib import Path
    from scripts.live.publish_site import SITE_FILES

    dashboard = Path(__file__).resolve().parents[1] / "dashboard"
    imported = set()
    for name in SITE_FILES:
        path = dashboard / name
        if path.suffix != ".css" or not path.exists():
            continue
        for match in re.finditer(r'@import\s+url\(["\']?([^"\')]+)', path.read_text(encoding="utf-8")):
            imported.add(match.group(1).strip())
    missing = sorted(imported - set(SITE_FILES))
    assert not missing, f"imported but never published: {missing}"
