import time
from scripts.live import refresh_dashboard as rd


class FakeClient:
    def __init__(self, by_series, scan):
        self.by_series = by_series
        self.scan = scan
        self.scanned = 0
    def get_events(self, *, series_ticker, status=None):
        return self.by_series.get(series_ticker, [])
    def scan_events(self, *, status="open", max_pages=60):
        self.scanned += 1
        return self.scan


def test_polls_configured_series(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "SERIES_SCAN_MARKER", tmp_path / ".scan")
    from ufc_mentions import fight_series
    monkeypatch.setattr(fight_series, "SERIES_STORE", tmp_path / "series.json")
    client = FakeClient(
        {"KXFIGHTMENTION": [{"event_ticker": "KXFIGHTMENTION-26AUG15X", "title": "announcers say Makhachev vs Garry"}]},
        scan=[],
    )
    events = rd.discover_open_fight_events(client, configured_series="KXFIGHTMENTION", now=1000)
    assert [e["event_ticker"] for e in events] == ["KXFIGHTMENTION-26AUG15X"]


def test_relaunch_under_new_series_is_discovered_and_polled(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "SERIES_SCAN_MARKER", tmp_path / ".scan")
    from ufc_mentions import fight_series
    store = tmp_path / "series.json"
    monkeypatch.setattr(fight_series, "SERIES_STORE", store)
    # Old series is empty; the new one only shows up in the site-wide scan.
    new_ev = {"series_ticker": "KXUFCMENTION", "event_ticker": "KXUFCMENTION-26AUG15MG",
              "title": "What will announcers say during Makhachev vs. Garry"}
    client = FakeClient({"KXFIGHTMENTION": [], "KXUFCMENTION": [new_ev]}, scan=[new_ev])
    events = rd.discover_open_fight_events(client, configured_series="KXFIGHTMENTION", now=2000)
    assert any(e["event_ticker"] == "KXUFCMENTION-26AUG15MG" for e in events)
    # It remembered the new series for next time.
    assert "KXUFCMENTION" in fight_series.load_known_series(store)


def test_scan_is_throttled(tmp_path, monkeypatch):
    marker = tmp_path / ".scan"
    monkeypatch.setattr(rd, "SERIES_SCAN_MARKER", marker)
    from ufc_mentions import fight_series
    monkeypatch.setattr(fight_series, "SERIES_STORE", tmp_path / "series.json")
    client = FakeClient({"KXFIGHTMENTION": []}, scan=[])
    rd.discover_open_fight_events(client, configured_series="KXFIGHTMENTION", now=5000)
    rd.discover_open_fight_events(client, configured_series="KXFIGHTMENTION", now=5000 + 60)
    assert client.scanned == 1  # second call within the window did not rescan
