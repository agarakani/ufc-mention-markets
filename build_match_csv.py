#!/usr/bin/env python3
"""Build a per-fight CSV of STRICT phrase-mention booleans, ready to join later
against real fight outcomes (e.g. the Kaggle UFC dataset).

One row per valid fight (duration_s != 0.0). Identifier/context columns up front,
then a True/False column per strict market phrase. Booleans use the SAME verified
strict matcher as mention_counts.py (exact term + plural/possessive only), imported
directly so the CSV stays consistent with the market-resolution numbers.

Usage:
  python3 build_match_csv.py [DATA_DIR] [-o OUTPUT.csv]
  python3 build_match_csv.py --phrases market_phrases.txt
"""

import csv
import os
import sys

# Reuse the same strict matcher and helpers used by the summary script.
from mention_counts import strict_pattern, last_name, norm, iter_records
from phrase_targets import PHRASES_FILE_DEFAULT, phrase_columns

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

DATA_DIR_DEFAULT = "~/ufc-mention-markets/ufc_cleaned_export"
OUT_DEFAULT = "~/ufc-mention-markets/fight_mentions.csv"


def build(data_dir, out_path, phrase_path=PHRASES_FILE_DEFAULT):
    phrase_cols = phrase_columns(phrase_path)
    cols = [(name, strict_pattern(phrase)) for name, phrase in phrase_cols]
    header = ID_COLUMNS + [name for name, _ in phrase_cols]
    tally = {name: 0 for name, _ in phrase_cols}
    rows = skipped = errors = 0

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


def main():
    args = sys.argv[1:]
    out_path = OUT_DEFAULT
    phrase_path = PHRASES_FILE_DEFAULT
    if "-o" in args:
        i = args.index("-o")
        out_path = args[i + 1]
        del args[i:i + 2]
    if "--phrases" in args:
        i = args.index("--phrases")
        phrase_path = os.path.expanduser(args[i + 1])
        del args[i:i + 2]
    positional = [a for a in args if not a.startswith("-")]
    data_dir = os.path.expanduser(positional[0] if positional else DATA_DIR_DEFAULT)
    out_path = os.path.expanduser(out_path)

    rows, skipped, errors, header, tally, phrase_cols = build(data_dir, out_path, phrase_path)
    print(f"Wrote {rows} fight rows to {out_path}")
    print(f"  skipped {skipped} invalid (duration_s==0.0/missing), {errors} read errors")
    print(f"  {len(header)} columns: {', '.join(header)}")
    print("  True counts per phrase (should match mention_counts.py strict totals):")
    for name, _ in phrase_cols:
        print(f"    {name:<28}{tally[name]:>6}")


if __name__ == "__main__":
    main()
