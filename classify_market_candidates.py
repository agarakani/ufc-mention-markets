#!/usr/bin/env python3
"""Classify Oddpool search results into likely market types.

This is a triage helper, not a source of truth. It helps separate:
  - actual mention markets: "Will the announcers say 'Guillotine'..."
  - fight outcome markets: "Will the fight be won by submission?"
  - unrelated UFC chatter markets: "Will Trump say 'UFC'..."

The output is still meant for human review before anything is mapped to model
targets or used for an edge table.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


OUT_DEFAULT = Path("market_data/classified_markets.csv")

STRICT_TARGETS = {
    "knockout": "mention_knockout",
    "tko": "mention_tko",
    "knocked out": "mention_knocked_out",
    "submission": "mention_submission",
    "split decision": "mention_split_decision",
    "unanimous decision": "mention_unanimous_decision",
    "doctor": "mention_doctor",
}

# Related commentary phrases we do not yet model directly but should consider adding.
RELATED_COMMENTARY_TERMS = {
    "guillotine": "submission_related",
    "choke": "submission_related",
    "triangle": "submission_related",
    "armbar": "submission_related",
    "butterfly": "grappling_related",
    "eye poke": "foul_related",
}


def read_many(paths):
    rows = []
    for path in paths:
        with Path(path).open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                row["_source_file"] = str(path)
                rows.append(row)
    return rows


def extract_quoted_terms(text):
    terms = []
    for pattern in [r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'"]:
        terms.extend(re.findall(pattern, text or ""))
    return [t.strip() for t in terms if t.strip()]


def classify(row):
    q = row.get("question", "") or ""
    event = row.get("event_title", "") or ""
    text = f"{q} {event}".lower()
    quoted = extract_quoted_terms(q)

    if "announcers say" in text or "announcer say" in text:
        market_type = "mention_announcers"
    elif "trump say" in text or "will trump say" in text:
        market_type = "mention_unrelated_speaker"
    elif "say" in text or "mentioned" in text or "be said" in text:
        market_type = "mention_other"
    elif "won by submission" in text or "win by submission" in text or "end by submission" in text:
        market_type = "fight_outcome_submission"
    elif "won by knockout" in text or "win by ko" in text or "ko/tko" in text:
        market_type = "fight_outcome_ko_tko"
    else:
        market_type = "other"

    mapped_phrase = ""
    mapped_target = ""
    related_group = ""
    for term in quoted:
        key = term.lower()
        if key in STRICT_TARGETS:
            mapped_phrase = key
            mapped_target = STRICT_TARGETS[key]
            break
        if key in RELATED_COMMENTARY_TERMS:
            mapped_phrase = key
            related_group = RELATED_COMMENTARY_TERMS[key]
            break

    # Outcome markets sometimes contain the target word but should not map to mention labels.
    if market_type.startswith("fight_outcome"):
        mapped_target = ""

    return {
        "market_type": market_type,
        "quoted_terms": "; ".join(quoted),
        "mapped_phrase": mapped_phrase,
        "mapped_target": mapped_target,
        "related_group": related_group,
        "needs_manual_review": "yes" if market_type.startswith("mention") else "no",
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    base_fields = [
        "_source_file",
        "market_type",
        "needs_manual_review",
        "mapped_phrase",
        "mapped_target",
        "related_group",
        "quoted_terms",
        "exchange",
        "status",
        "market_id",
        "question",
        "event_title",
        "volume",
        "liquidity",
        "last_yes_price",
        "slug",
        "settled_at",
    ]
    extras = sorted({k for row in rows for k in row.keys()} - set(base_fields))
    fields = base_fields + extras
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Oddpool search result CSVs")
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    rows = []
    for row in read_many(args.csvs):
        row.update(classify(row))
        rows.append(row)
    rows.sort(key=lambda r: (
        r.get("market_type") != "mention_announcers",
        r.get("market_type"),
        -(float(r.get("volume") or 0) if str(r.get("volume") or "").replace(".", "", 1).isdigit() else 0),
    ))
    write_csv(Path(args.out), rows)

    counts = {}
    for row in rows:
        counts[row["market_type"]] = counts.get(row["market_type"], 0) + 1
    print(f"Wrote {len(rows)} classified rows to {args.out}")
    for key, value in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {key}: {value}")
    print("\nLikely mention-market candidates:")
    shown = 0
    for row in rows:
        if row["market_type"].startswith("mention"):
            print(f"  [{row['market_type']}] {row.get('question')}")
            shown += 1
            if shown >= 12:
                break


if __name__ == "__main__":
    main()
