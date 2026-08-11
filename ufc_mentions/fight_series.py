#!/usr/bin/env python3
"""Find the Kalshi series that carries UFC announcer-mention markets.

The recorder used to hardcode a single series, KXFIGHTMENTION. Kalshi
restructures series (its old KXFIGHTMENTION events vanished after Jul 2026,
and a March Madness version, KXMMMENTION, runs under a different ticker). If
Kalshi relists UFC mention markets under a new name, a hardcoded ticker goes
blind forever. So discovery works two ways: poll a known set of series every
cycle, and periodically scan every open event for the mention pattern to catch
a relaunch under any name, remembering what it finds.

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
_UFC = re.compile(r"\bufc\b|fight night|\bmma\b|octagon", re.I)
# a title like "Ankalaev vs. Guskov" without the UFC word still reads as a bout
_VS = re.compile(r"\bvs\.?\b|\bv\.\b", re.I)


def is_fight_mention_event(event: dict) -> bool:
    """True when an event looks like a UFC announcer-mention market.

    Deliberately strict on the mention half (must mention announcers/saying)
    and lenient on the sport half (UFC keyword OR a versus-style matchup) so a
    renamed series is still caught, while TV-season and IPO 'announcement'
    markets are not."""
    blob = " ".join(str(event.get(key, "")) for key in ("title", "sub_title", "event_ticker"))
    if not _MENTION.search(blob):
        return False
    if _UFC.search(blob):
        return True
    # Guard the versus fallback: an "announcement" market about two companies
    # should not qualify, so require the mention word to be about speech.
    return bool(_VS.search(blob) and re.search(r"announcer|\bsay\b|\bsaid\b", blob, re.I))


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
