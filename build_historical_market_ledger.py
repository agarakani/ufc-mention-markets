#!/usr/bin/env python3
"""Build an auditable ledger of historical UFC announcer markets.

The ledger never treats terminal price as resolution. Official token/outcome
metadata comes from fetch_polymarket_metadata.py. Transcript matching is exact
on event date and fighter pair so rematches cannot silently map to older bouts.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from join_kaggle_outcomes import pair_key


CLASSIFIED_DEFAULT = Path("market_data/classified_markets.csv")
METADATA_DEFAULT = Path("market_data/polymarket_metadata.csv")
MENTIONS_DEFAULT = Path("fight_mentions.csv")
OUT_DEFAULT = Path("market_data/historical_market_ledger.csv")

OUT_FIELDS = [
    "market_id", "exchange", "status", "scope", "phrase", "target", "question",
    "event_title", "market_open_iso", "event_start_iso", "market_close_iso",
    "settled_at", "volume", "liquidity", "terminal_yes_price", "terminal_no_price",
    "yes_asset_id", "no_asset_id", "resolved_yes", "resolution_source",
    "event_date", "transcript_id", "fighter_1", "fighter_2", "event_fight_count",
    "mapping_status", "mapping_notes", "data_ready",
]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def iso_date(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date().isoformat()


def infer_scope(question: str) -> str:
    return "fight" if re.search(r"\bduring\b.+\bvs\.?\b", question or "", re.I) else "event"


def extract_question_fighters(question: str) -> tuple[str, str] | None:
    match = re.search(r"\bduring\s+(.+?)\s+vs\.?\s+(.+?)\?*$", question or "", re.I)
    if not match:
        return None
    first = re.sub(r"\s+\d+$", "", match.group(1).strip())
    second = re.sub(r"\s+\d+$", "", match.group(2).strip())
    return first, second


def dedupe_markets(rows: list[dict]) -> list[dict]:
    unique = {}
    for row in rows:
        if row.get("market_type") != "mention_announcers":
            continue
        if row.get("market_complexity") != "simple_binary":
            continue
        market_id = (row.get("market_id") or "").strip()
        if market_id:
            unique[market_id] = row
    return list(unique.values())


def build_mention_indexes(rows: list[dict]):
    by_date = defaultdict(list)
    by_pair_date = defaultdict(list)
    for row in rows:
        date = row.get("event_date", "")
        by_date[date].append(row)
        pair = pair_key(row.get("fighter_1", ""), row.get("fighter_2", ""))
        if pair and date:
            by_pair_date[(pair, date)].append(row)
    return by_date, by_pair_date


def map_market(row: dict, meta: dict, by_date, by_pair_date) -> dict:
    scope = infer_scope(row.get("question", ""))
    event_date = iso_date(meta.get("event_start_iso", ""))
    result = {
        "scope": scope,
        "event_date": event_date,
        "transcript_id": "",
        "fighter_1": "",
        "fighter_2": "",
        "event_fight_count": len(by_date.get(event_date, [])) if event_date else 0,
        "mapping_status": "",
        "mapping_notes": "",
    }

    if not event_date:
        result["mapping_status"] = "missing_event_start"
        result["mapping_notes"] = "Official market metadata did not provide event_start_iso."
        return result

    if scope == "event":
        if by_date.get(event_date):
            result["mapping_status"] = "matched_event"
        else:
            result["mapping_status"] = "no_transcripts_on_event_date"
        return result

    fighters = extract_question_fighters(row.get("question", ""))
    if not fighters:
        result["mapping_status"] = "fighter_names_not_parsed"
        return result
    pair = pair_key(*fighters)
    matches = by_pair_date.get((pair, event_date), []) if pair else []
    if len(matches) == 1:
        fight = matches[0]
        result.update({
            "transcript_id": fight.get("transcript_id", ""),
            "fighter_1": fight.get("fighter_1", ""),
            "fighter_2": fight.get("fighter_2", ""),
            "mapping_status": "matched_fight",
        })
    elif len(matches) > 1:
        result["mapping_status"] = "ambiguous_fight_match"
        result["mapping_notes"] = f"{len(matches)} exact pair/date rows"
    else:
        result["mapping_status"] = "no_exact_fight_match"
        result["mapping_notes"] = f"Parsed fighters: {fighters[0]} vs {fighters[1]}"
    return result


def build(classified: list[dict], metadata: list[dict], mentions: list[dict]) -> list[dict]:
    meta_index = {row.get("market_id"): row for row in metadata}
    by_date, by_pair_date = build_mention_indexes(mentions)
    output = []

    for row in dedupe_markets(classified):
        market_id = row["market_id"]
        meta = meta_index.get(market_id, {})
        mapping = map_market(row, meta, by_date, by_pair_date)
        resolved = meta.get("resolved_yes", "")
        tokenized = bool(meta.get("yes_asset_id") and meta.get("no_asset_id"))
        mapped = mapping["mapping_status"] in {"matched_fight", "matched_event"}
        ready = bool(tokenized and mapped and resolved in {"True", "False"})

        output.append({
            "market_id": market_id,
            "exchange": row.get("exchange", ""),
            "status": row.get("status", ""),
            "scope": mapping["scope"],
            "phrase": row.get("mapped_phrase", ""),
            "target": row.get("mapped_target", ""),
            "question": row.get("question", ""),
            "event_title": row.get("event_title", ""),
            "market_open_iso": meta.get("market_open_iso") or row.get("discovered_at", ""),
            "event_start_iso": meta.get("event_start_iso", ""),
            "market_close_iso": meta.get("market_close_iso", ""),
            "settled_at": row.get("settled_at", ""),
            "volume": row.get("volume", ""),
            "liquidity": row.get("liquidity", ""),
            "terminal_yes_price": row.get("last_yes_price", ""),
            "terminal_no_price": row.get("last_no_price", ""),
            "yes_asset_id": meta.get("yes_asset_id", ""),
            "no_asset_id": meta.get("no_asset_id", ""),
            "resolved_yes": resolved,
            "resolution_source": meta.get("resolution_source", ""),
            **mapping,
            "data_ready": "yes" if ready else "no",
        })
    return sorted(output, key=lambda item: (item.get("event_date", ""), item["market_id"]))


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classified", default=str(CLASSIFIED_DEFAULT))
    parser.add_argument("--metadata", default=str(METADATA_DEFAULT))
    parser.add_argument("--mentions", default=str(MENTIONS_DEFAULT))
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    rows = build(
        read_csv(Path(args.classified)),
        read_csv(Path(args.metadata)),
        read_csv(Path(args.mentions)),
    )
    write_csv(Path(args.out), rows)
    print(f"Wrote {len(rows)} historical market rows to {args.out}")
    for status, count in sorted({s: sum(r['mapping_status'] == s for r in rows) for s in {r['mapping_status'] for r in rows}}.items()):
        print(f"  {status}: {count}")
    print(f"  fully data-ready: {sum(r['data_ready'] == 'yes' for r in rows)}")


if __name__ == "__main__":
    main()
