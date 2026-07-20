import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data.fetch_fighter_photos import (
    fetch_missing,
    load_manifest,
    resolve_photo,
    slugify,
)

NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)

SEARCH_HIT = {
    "query": {"search": [{
        "title": "Max Holloway",
        "snippet": "is an American professional mixed martial artist in the UFC",
    }]}
}
SEARCH_WRONG_PERSON = {
    "query": {"search": [{
        "title": "Max Holloway (politician)",
        "snippet": "is an American politician from Ohio",
    }]}
}
IMAGE_HIT = {
    "query": {"pages": {"123": {
        "title": "Max Holloway",
        "thumbnail": {"source": "https://upload.wikimedia.org/max.jpg", "width": 500, "height": 667},
    }}}
}
JPEG_BYTES = b"\xff\xd8\xff\xe0fakejpeg"


class FakeHttp:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, params=None):
        self.calls.append((url, params))
        for key, value in self.responses.items():
            blob = json.dumps(params or {}) + url
            if key in blob:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected request: {url} {params}")


def test_slugify():
    assert slugify("Max Holloway") == "max_holloway"
    assert slugify("José Aldo Jr.") == "jos_aldo_jr"


def test_resolve_photo_happy_path():
    http = FakeHttp({"list\": \"search": SEARCH_HIT, "pageimages": IMAGE_HIT, "upload.wikimedia": JPEG_BYTES})
    result = resolve_photo("Max Holloway", http)
    assert result["source_title"] == "Max Holloway"
    assert result["image_bytes"] == JPEG_BYTES


def test_rejects_wrong_person():
    http = FakeHttp({"list\": \"search": SEARCH_WRONG_PERSON})
    assert resolve_photo("Max Holloway", http) is None


def test_manifest_skips_existing_and_retries_stale_not_found(tmp_path):
    http = FakeHttp({"list\": \"search": SEARCH_HIT, "pageimages": IMAGE_HIT, "upload.wikimedia": JPEG_BYTES})
    assets = tmp_path / "fighters"
    assets.mkdir()
    fresh = (NOW - timedelta(days=2)).isoformat()
    stale = (NOW - timedelta(days=45)).isoformat()
    manifest = {
        "already ok": {"status": "ok", "file": "already_ok.jpg", "fetched_at": fresh},
        "fresh miss": {"status": "not_found", "fetched_at": fresh},
        "max holloway": {"status": "not_found", "fetched_at": stale},
    }
    (assets / "manifest.json").write_text(json.dumps(manifest))

    result = fetch_missing(["Already Ok", "Fresh Miss", "Max Holloway"], assets, http, NOW)

    assert result["already ok"]["status"] == "ok"
    assert result["fresh miss"]["status"] == "not_found"
    assert result["max holloway"]["status"] == "ok"
    assert (assets / "max_holloway.jpg").exists()
    saved = load_manifest(assets)
    assert saved["max holloway"]["status"] == "ok"


def test_network_error_is_soft_and_retried(tmp_path):
    http = FakeHttp({"list\": \"search": RuntimeError("network down")})
    assets = tmp_path / "fighters"
    assets.mkdir()
    result = fetch_missing(["Max Holloway"], assets, http, NOW)
    assert result["max holloway"]["status"] == "error"

    good = FakeHttp({"list\": \"search": SEARCH_HIT, "pageimages": IMAGE_HIT, "upload.wikimedia": JPEG_BYTES})
    retried = fetch_missing(["Max Holloway"], assets, good, NOW)
    assert retried["max holloway"]["status"] == "ok"
