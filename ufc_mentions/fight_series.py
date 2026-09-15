#!/usr/bin/env python3
"""Find the Kalshi series that carries UFC announcer-mention markets.

Poll known series each cycle and scan open events for new UFC mention series.
Other sports also have announcer markets, so a matchup alone is not UFC evidence.

The matcher and the merge are pure functions so they can be tested without a
network. Persistence lives in data/processed/fight_series.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERIES_STORE = ROOT / "data" / "processed" / "fight_series.json"

# The series the recorder has always used, plus the obvious relaunch names.
SEED_SERIES = ("KXFIGHTMENTION",)

_MENTION = re.compile(r"announcer|mention|\bsay\b|\bsaid\b", re.I)
_UFC = re.compile(r"\bufc\b", re.I)


def is_fight_mention_event(event: dict) -> bool:
    """Require mention wording plus the verified legacy series or explicit UFC label."""
    blob = " ".join(str(event.get(key, "")) for key in ("title", "sub_title", "event_ticker", "series_ticker"))
    if not _MENTION.search(blob):
        return False
    series = series_of(event).upper()
    return bool(series in SEED_SERIES or series.startswith("KXUFC") or _UFC.search(blob))


def series_of(event: dict) -> str:
    series = str(event.get("series_ticker") or "").strip()
    if series:
        return series
    # Fall back to the ticker prefix, e.g. KXFIGHTMENTION-26JUL25ANKGUS.
    ticker = str(event.get("event_ticker") or "")
    return ticker.split("-", 1)[0] if "-" in ticker else ticker


def discover_series_from_events(events: list[dict]) -> list[str]:
    """Series tickers of every event that looks like a UFC mention market."""
    found: list[str] = []
    for event in events:
        if is_fight_mention_event(event):
            series = series_of(event)
            if series and series not in found:
                found.append(series)
    return found


def merge_series(known: list[str], discovered: list[str]) -> list[str]:
    """Union, seed order first, then first-seen discovery order."""
    out = list(dict.fromkeys([*SEED_SERIES, *known]))
    for series in discovered:
        if series not in out:
            out.append(series)
    return out


def load_known_series(path: Path | None = None) -> list[str]:
    # Resolve at call time so tests (and a moved store) can override the path;
    # a default argument would bind SERIES_STORE once at import.
    path = path or SERIES_STORE
    if not path.exists():
        return list(SEED_SERIES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return list(SEED_SERIES)
    stored = data.get("series") if isinstance(data, dict) else data
    return merge_series([str(s) for s in (stored or [])], [])


def save_known_series(series: list[str], path: Path | None = None) -> None:
    path = path or SERIES_STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"series": merge_series(series, [])}, indent=2) + "\n", encoding="utf-8")
