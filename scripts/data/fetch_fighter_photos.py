#!/usr/bin/env python3
"""Fetch fighter headshots from Wikipedia into a local cached asset folder."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ufc-mention-markets/1.0 (local research dashboard)"
ASSETS_DEFAULT = ROOT / "dashboard" / "assets" / "fighters"
LIVE_EDGES = ROOT / "market_data" / "kalshi_live_edges.csv"
TRACKING_ROOT = ROOT / "data" / "tracking"
DIRECTORY = ROOT / "data" / "processed" / "fighter_directory.csv"

NOT_FOUND_RETRY_DAYS = 30
EVIDENCE = re.compile(r"martial|fighter|ufc", re.IGNORECASE)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text or ""))


def resolve_photo(name: str, http_get) -> dict | None:
    search = http_get(API, params={
        "action": "query", "list": "search", "format": "json",
        "srsearch": f"{name} mixed martial artist", "srlimit": 3,
    })
    hits = ((search or {}).get("query") or {}).get("search") or []
    title = None
    for hit in hits:
        hit_title = str(hit.get("title", ""))
        snippet = _strip_tags(hit.get("snippet", ""))
        if name.lower() not in hit_title.lower():
            continue
        if not EVIDENCE.search(f"{hit_title} {snippet}"):
            continue
        title = hit_title
        break
    if not title:
        return None

    images = http_get(API, params={
        "action": "query", "titles": title, "format": "json",
        "prop": "pageimages", "pithumbsize": 500,
    })
    pages = ((images or {}).get("query") or {}).get("pages") or {}
    thumb = None
    for page in pages.values():
        thumb = ((page or {}).get("thumbnail") or {}).get("source")
        if thumb:
            break
    if not thumb:
        return None

    image_bytes = http_get(thumb)
    if not image_bytes:
        return None
    return {"source_title": title, "image_url": thumb, "image_bytes": image_bytes}


def manifest_path(assets_root: Path) -> Path:
    return Path(assets_root) / "manifest.json"


def load_manifest(assets_root: Path) -> dict:
    path = manifest_path(assets_root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_manifest(assets_root: Path, manifest: dict) -> None:
    manifest_path(assets_root).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def _needs_fetch(entry: dict | None, now: datetime) -> bool:
    if not entry:
        return True
    if entry.get("status") == "ok":
        return False
    if entry.get("status") == "error":
        return True
    fetched_at = entry.get("fetched_at", "")
    try:
        stamp = datetime.fromisoformat(fetched_at)
    except ValueError:
        return True
    return now - stamp >= timedelta(days=NOT_FOUND_RETRY_DAYS)


def fetch_missing(names, assets_root: Path, http_get, now: datetime, pause_s: float = 0.0) -> dict:
    assets_root = Path(assets_root)
    assets_root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(assets_root)
    for name in names:
        name = str(name or "").strip()
        if not name:
            continue
        key = name.lower()
        if not _needs_fetch(manifest.get(key), now):
            continue
        try:
            result = resolve_photo(name, http_get)
        except Exception:
            manifest[key] = {"status": "error", "fetched_at": now.isoformat()}
            if pause_s:
                time.sleep(pause_s)
            continue
        if result:
            filename = f"{slugify(name)}.jpg"
            (assets_root / filename).write_bytes(result["image_bytes"])
            manifest[key] = {
                "status": "ok",
                "file": filename,
                "source_title": result["source_title"],
                "image_url": result["image_url"],
                "fetched_at": now.isoformat(),
            }
        else:
            manifest[key] = {"status": "not_found", "fetched_at": now.isoformat()}
        if pause_s:
            time.sleep(pause_s)
    save_manifest(assets_root, manifest)
    return manifest


def default_http_get(url, params=None):
    import requests

    response = requests.get(url, params=params, timeout=10, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    if url == API:
        return response.json()
    return response.content


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def names_from_live(marquee_top: int = 100) -> list[str]:
    names: list[str] = []
    seen = set()

    def add(name):
        name = str(name or "").strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)

    for row in read_csv(LIVE_EDGES):
        add(row.get("fighter_1"))
        add(row.get("fighter_2"))
    if TRACKING_ROOT.exists():
        for card_dir in sorted(p for p in TRACKING_ROOT.iterdir() if p.is_dir()):
            for row in read_csv(card_dir / "paper_positions.csv"):
                add(row.get("fighter_1"))
                add(row.get("fighter_2"))
    directory = read_csv(DIRECTORY)
    directory.sort(key=lambda row: -float(row.get("marquee_score") or 0))
    for row in directory[:marquee_top]:
        add(row.get("name"))
    return names


def main():
    parser = argparse.ArgumentParser(description="Fetch fighter photos from Wikipedia.")
    parser.add_argument("--names", nargs="*", default=None)
    parser.add_argument("--from-live", action="store_true")
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--assets", default=ASSETS_DEFAULT)
    args = parser.parse_args()

    names = list(args.names or [])
    if args.from_live or not names:
        names.extend(names_from_live())
    names = names[: args.limit]

    now = datetime.now(timezone.utc)
    manifest = fetch_missing(names, Path(args.assets), default_http_get, now, pause_s=0.4)
    ok = sum(1 for entry in manifest.values() if entry.get("status") == "ok")
    print(f"Photo manifest: {ok}/{len(manifest)} fighters with photos")


if __name__ == "__main__":
    main()
