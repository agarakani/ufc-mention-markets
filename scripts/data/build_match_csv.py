#!/usr/bin/env python3
"""Build a per-fight CSV of STRICT phrase-mention booleans, ready to join later
against real fight outcomes (e.g. the Kaggle UFC dataset).

One row per valid fight (duration_s != 0.0). Identifier/context columns up front,
then a True/False column per strict market phrase. Booleans use the SAME verified
strict matcher as mention_counts.py (exact term + plural/possessive only), imported
directly so the CSV stays consistent with the market-resolution numbers.

Usage:
  python3 scripts/data/build_match_csv.py [DATA_DIR] [-o OUTPUT.csv]
  python3 scripts/data/build_match_csv.py --phrases market_phrases.txt
"""

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the same strict matcher and helpers used by the summary script.
from ufc_mentions.mention_counts import strict_pattern, last_name, norm, iter_records
from ufc_mentions.phrase_targets import PHRASES_FILE_DEFAULT, phrase_columns

# (csv column name -> strict phrase). Order = market_phrases.txt order.
PHRASE_COLUMNS = phrase_columns()

# Identifier / context columns (help the later outcome join; trim if you don't need them).
ID_COLUMNS = [
    "transcript_id",      # unique matchup key — natural primary key
    "fighter_1", "fighter_2",
    "fighter_1_last", "fighter_2_last",   # last names ease fuzzy name joins
    "event_date", "weight_class", "event_title",
    "duration_s",
]

DATA_DIR_DEFAULT = ROOT / "ufc_cleaned_export"
OUT_DEFAULT = ROOT / "data" / "processed" / "fight_mentions.csv"


def build(data_dir, out_path, phrase_path=PHRASES_FILE_DEFAULT):
    phrase_cols = phrase_columns(phrase_path)
    cols = [(name, strict_pattern(phrase)) for name, phrase in phrase_cols]
    header = ID_COLUMNS + [name for name, _ in phrase_cols]
    tally = {name: 0 for name, _ in phrase_cols}
    rows = skipped = errors = 0

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for _fn, rec in iter_records(data_dir):
            if "__error__" in rec:
                errors += 1
                continue
            dur = rec.get("duration_s")
            if dur is None or float(dur) == 0.0:
                skipped += 1
                continue
            text = norm(rec.get("plain_text"))

            id_values = [
                rec.get("transcript_id", ""),
                rec.get("fighter_1", ""),
                rec.get("fighter_2", ""),
                last_name(rec.get("fighter_1")),
                last_name(rec.get("fighter_2")),
                rec.get("event_date", ""),
                rec.get("weight_class", ""),
                rec.get("event_title", ""),
                dur,
            ]
            flags = []
            for name, pat in cols:
                hit = bool(pat.search(text))
                flags.append(hit)
                if hit:
                    tally[name] += 1
            writer.writerow(id_values + flags)
            rows += 1

    return rows, skipped, errors, header, tally, phrase_cols


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build fight_mentions.csv from UFC transcript files."
    )
    parser.add_argument("data_dir", nargs="?", default=DATA_DIR_DEFAULT)
    parser.add_argument("-o", "--output", default=OUT_DEFAULT)
    parser.add_argument("--phrases", default=PHRASES_FILE_DEFAULT)
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = os.path.expanduser(str(args.data_dir))
    out_path = os.path.expanduser(str(args.output))
    phrase_path = os.path.expanduser(str(args.phrases))

    rows, skipped, errors, header, tally, phrase_cols = build(data_dir, out_path, phrase_path)
    print(f"Wrote {rows} fight rows to {out_path}")
    print(f"  skipped {skipped} invalid (duration_s==0.0/missing), {errors} read errors")
    print(f"  {len(header)} columns: {', '.join(header)}")
    print("  True counts per phrase (should match mention_counts.py strict totals):")
    for name, _ in phrase_cols:
        print(f"    {name:<28}{tally[name]:>6}")


if __name__ == "__main__":
    main()
