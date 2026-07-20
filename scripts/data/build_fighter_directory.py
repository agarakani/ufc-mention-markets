#!/usr/bin/env python3
"""Build a per-fighter directory (identity + style + marquee) from fight data."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIGHT_MENTIONS = ROOT / "data" / "processed" / "fight_mentions.csv"
JOINED_FIGHTS = ROOT / "data" / "processed" / "joined_fights.csv"
OUT_DEFAULT = ROOT / "data" / "processed" / "fighter_directory.csv"

KNOCKOUT_FAMILY = ["mention_knockout", "mention_ko", "mention_tko", "mention_knocked_out"]
DECISION_FAMILY = ["mention_split_decision", "mention_unanimous_decision"]

RATE_FIELDS = ["rate_submission", "rate_knockout_family", "rate_decision_family", "rate_choke"]

TAG_RULES = [
    ("rate_submission", "GRAPPLER"),
    ("rate_knockout_family", "FINISHER"),
    ("rate_decision_family", "DISTANCE FIGHTER"),
]
TAG_LIFT = 0.15

OUT_FIELDS = [
    "name", "name_lower", "nickname", "n_fights", "last_event_date",
    "record_wins", "record_losses", "stance", "height_cms", "reach_cms",
    "rate_submission", "rate_knockout_family", "rate_decision_family", "rate_choke",
    "style_tags", "marquee_score",
]


def as_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fight_flags(row: dict) -> dict:
    return {
        "rate_submission": as_bool(row.get("mention_submission")),
        "rate_knockout_family": any(as_bool(row.get(col)) for col in KNOCKOUT_FAMILY),
        "rate_decision_family": any(as_bool(row.get(col)) for col in DECISION_FAMILY),
        "rate_choke": as_bool(row.get("mention_choke")),
    }


def league_rates(fight_rows: list[dict]) -> dict:
    totals = {field: 0 for field in RATE_FIELDS}
    for row in fight_rows:
        flags = fight_flags(row)
        for field in RATE_FIELDS:
            totals[field] += flags[field]
    count = max(len(fight_rows), 1)
    return {field: totals[field] / count for field in RATE_FIELDS}


def style_tags(rates: dict, league: dict) -> list[str]:
    lifts = []
    for field, tag in TAG_RULES:
        rate = rates.get(field)
        base = league.get(field)
        if rate is None or base is None:
            continue
        lift = rate - base
        if lift >= TAG_LIFT:
            lifts.append((lift, tag))
    lifts.sort(reverse=True)
    return [tag for _, tag in lifts[:2]]


def marquee_score(n_fights: int, title_bouts: int) -> int:
    return min(n_fights, 15) + 10 * title_bouts


def _corner_stats(row: dict, corner: str) -> dict:
    return {
        "record_wins": as_float(row.get(f"kaggle_{corner}_wins")),
        "record_losses": as_float(row.get(f"kaggle_{corner}_losses")),
        "stance": str(row.get(f"kaggle_{corner}_Stance", "")).strip(),
        "height_cms": as_float(row.get(f"kaggle_{corner}_Height_cms")),
        "reach_cms": as_float(row.get(f"kaggle_{corner}_Reach_cms")),
    }


def _joined_lookup(joined_rows: list[dict]) -> dict:
    """name_lower -> latest (event_date, stats, title_bout_count accumulator)."""
    latest: dict[str, dict] = {}
    titles: dict[str, int] = {}
    for row in joined_rows:
        date = str(row.get("event_date", ""))
        title_bout = as_bool(row.get("kaggle_title_bout"))
        for corner in ("R", "B"):
            name = str(row.get(f"kaggle_{corner}_fighter", "")).strip()
            if not name:
                continue
            key = name.lower()
            if title_bout:
                titles[key] = titles.get(key, 0) + 1
            current = latest.get(key)
            if current is None or date > current["date"]:
                latest[key] = {"date": date, "stats": _corner_stats(row, corner)}
    return {"latest": latest, "titles": titles}


def build_directory(fight_rows: list[dict], joined_rows: list[dict]) -> list[dict]:
    league = league_rates(fight_rows)
    joined = _joined_lookup(joined_rows)

    fighters: dict[str, dict] = {}
    for row in fight_rows:
        flags = fight_flags(row)
        date = str(row.get("event_date", ""))
        for slot in ("1", "2"):
            name = str(row.get(f"fighter_{slot}", "")).strip()
            if not name:
                continue
            key = name.lower()
            item = fighters.setdefault(key, {
                "name": name,
                "name_lower": key,
                "nickname": "",
                "nickname_date": "",
                "n_fights": 0,
                "last_event_date": "",
                "counts": {field: 0 for field in RATE_FIELDS},
            })
            item["n_fights"] += 1
            if date > item["last_event_date"]:
                item["last_event_date"] = date
            nickname = str(row.get(f"fighter_{slot}_nickname", "")).strip()
            if nickname and date >= item["nickname_date"]:
                item["nickname"] = nickname
                item["nickname_date"] = date
            for field in RATE_FIELDS:
                item["counts"][field] += flags[field]

    out = []
    for key, item in fighters.items():
        rates = {field: item["counts"][field] / item["n_fights"] for field in RATE_FIELDS}
        stats_entry = joined["latest"].get(key, {})
        stats = stats_entry.get("stats", {})
        title_bouts = joined["titles"].get(key, 0)
        record_wins = stats.get("record_wins")
        record_losses = stats.get("record_losses")
        out.append({
            "name": item["name"],
            "name_lower": key,
            "nickname": item["nickname"],
            "n_fights": item["n_fights"],
            "last_event_date": item["last_event_date"],
            "record_wins": int(record_wins) if record_wins is not None else "",
            "record_losses": int(record_losses) if record_losses is not None else "",
            "stance": stats.get("stance", "") or "",
            "height_cms": stats.get("height_cms") if stats.get("height_cms") is not None else "",
            "reach_cms": stats.get("reach_cms") if stats.get("reach_cms") is not None else "",
            **{field: round(rates[field], 4) for field in RATE_FIELDS},
            "style_tags": "|".join(style_tags(rates, league)),
            "marquee_score": marquee_score(item["n_fights"], title_bouts),
        })
    out.sort(key=lambda row: row["name_lower"])
    return out


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    fight_rows = read_csv(FIGHT_MENTIONS)
    joined_rows = read_csv(JOINED_FIGHTS)
    directory = build_directory(fight_rows, joined_rows)
    OUT_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    with OUT_DEFAULT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(directory)
    tagged = sum(1 for row in directory if row["style_tags"])
    with_stats = sum(1 for row in directory if row["record_wins"] != "")
    print(f"Wrote {len(directory)} fighters to {OUT_DEFAULT.relative_to(ROOT)}")
    print(f"  {tagged} with style tags, {with_stats} with Kaggle stats")


if __name__ == "__main__":
    main()
