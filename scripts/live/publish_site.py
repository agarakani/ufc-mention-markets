#!/usr/bin/env python3
"""Publish the dashboard as a public static site on GitHub Pages.

The dashboard is plain HTML/JS/CSS fed by one data file, so the shareable
version is just those four files pushed to the gh-pages branch. The public
page cannot refresh Kalshi itself; it shows the latest snapshot this Mac
published and re-reads the data file every minute. The Update button is
hidden there, and nothing on the public site can place trades — it is the
same read-only research board.

Publishing replaces the gh-pages branch with a single fresh commit each
time, so the branch never accumulates history.

Usage:
  python3 scripts/live/publish_site.py            # publish once
  python3 scripts/live/publish_site.py --if-due   # skip unless the throttle allows
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DASHBOARD = ROOT / "dashboard"
PUBLISH_MARKER = ROOT / "model_outputs" / ".site_publish_stamp"
PUBLISH_MIN_INTERVAL_SECONDS = 5 * 60
PUBLISH_LIVE_INTERVAL_SECONDS = 60
PUBLISH_IDLE_INTERVAL_SECONDS = 10 * 60
SITE_FILES = ["app.js", "styles.css", "data.js"]
LOADER_LINE = "      const cacheBust = Date.now().toString();"


def publish_interval_seconds(today: str, live_event_dates: list[str]) -> int:
    """1-minute publishing while a listed card is on today's date; 10 minutes idle."""
    if today and any(date == today for date in live_event_dates):
        return PUBLISH_LIVE_INTERVAL_SECONDS
    return PUBLISH_IDLE_INTERVAL_SECONDS


def static_index(index_html: str, version: int | None = None) -> str:
    """Mark the published copy as a static site so the page behaves right.

    The stylesheet link gets a version query so browsers and the Pages CDN
    can never pair fresh markup with a stale cached stylesheet."""
    flag = "      window.STATIC_SITE = true;\n"
    if LOADER_LINE not in index_html:
        raise SystemExit("dashboard/index.html changed shape; update publish_site.py")
    out = index_html.replace(LOADER_LINE, flag + LOADER_LINE, 1)
    stamp = int(time.time()) if version is None else version
    return out.replace('href="styles.css"', f'href="styles.css?v={stamp}"', 1)


def publish_due(now: float | None = None, interval_seconds: int | None = None) -> bool:
    now = time.time() if now is None else now
    interval = PUBLISH_MIN_INTERVAL_SECONDS if interval_seconds is None else interval_seconds
    if not PUBLISH_MARKER.exists():
        return True
    return (now - PUBLISH_MARKER.stat().st_mtime) >= interval


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def stage_site(site: Path) -> None:
    (site / "index.html").write_text(
        static_index((DASHBOARD / "index.html").read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    for name in SITE_FILES:
        shutil.copyfile(DASHBOARD / name, site / name)
    (site / ".nojekyll").write_text("", encoding="utf-8")


def publish(quiet: bool = False) -> str:
    data_file = DASHBOARD / "data.js"
    if not data_file.exists():
        return "no data.js yet; nothing to publish"
    remote = subprocess.run(
        ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp)
        stage_site(site)

        run(["git", "init", "-q", "-b", "gh-pages"], site)
        run(["git", "config", "user.name", "agarakani"], site)
        run(["git", "config", "user.email", "236674347+agarakani@users.noreply.github.com"], site)
        # the photo assets push several MB at once; the default 1MB buffer hangs up
        run(["git", "config", "http.postBuffer", "157286400"], site)
        run(["git", "add", "-A"], site)
        run(["git", "commit", "-q", "-m", "Publish dashboard snapshot"], site)
        run(["git", "push", "--force", "-q", remote, "gh-pages"], site)

    PUBLISH_MARKER.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_MARKER.touch()
    note = "published dashboard snapshot to gh-pages"
    if not quiet:
        print(note)
    return note


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-due", action="store_true",
                        help="respect the publish throttle instead of forcing")
    args = parser.parse_args()
    if args.if_due and not publish_due():
        print("published recently; skipping")
        return
    publish()


if __name__ == "__main__":
    main()
