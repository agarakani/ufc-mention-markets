import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live import refresh_dashboard as rd


def test_photo_fetch_throttled(tmp_path, monkeypatch):
    marker = tmp_path / ".photo_fetch_stamp"
    monkeypatch.setattr(rd, "PHOTO_FETCH_MARKER", marker)
    calls = []
    monkeypatch.setattr(rd, "_launch_photo_fetch", lambda: calls.append(1))

    note = rd.maybe_fetch_photos(now=1000.0)
    assert calls == [1]
    assert "photo" in note

    marker_mtime = marker.stat().st_mtime
    note = rd.maybe_fetch_photos(now=marker_mtime + 60)
    assert calls == [1]
    assert "waiting" in note

    note = rd.maybe_fetch_photos(now=marker_mtime + rd.PHOTO_FETCH_INTERVAL_SECONDS + 1)
    assert calls == [1, 1]


def test_photo_fetch_soft_on_error(tmp_path, monkeypatch):
    marker = tmp_path / ".photo_fetch_stamp"
    monkeypatch.setattr(rd, "PHOTO_FETCH_MARKER", marker)

    def boom():
        raise RuntimeError("no subprocess")

    monkeypatch.setattr(rd, "_launch_photo_fetch", boom)
    note = rd.maybe_fetch_photos(now=1000.0)
    assert "skipped" in note
