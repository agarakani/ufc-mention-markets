#!/usr/bin/env python3
"""Mine the actual vocabulary of UFC broadcasts from the transcripts.

Why this exists:
  The baseline mention model uses only pre-fight fighter/event stats, so it can
  only predict phrases mechanically tied to fight style (grappling terms, title
  bouts). The biggest missing signal is the transcripts themselves -- what
  announcers actually say, and how often. This scans every valid transcript and
  builds document-frequency tables for 1-, 2-, and 3-word phrases (how many
  fights each phrase appears in), which gives us:

    * base rate of any phrase  (fights_with_phrase / n_fights)  -> the anchor a
      richer model should start from instead of a flat intercept
    * discovery of candidate mention-market phrases we never hard-coded
    * a plain description of UFC-broadcast vocabulary

  Document frequency = number of fights whose plain_text contains the phrase at
  least once (this is how a mention market resolves). Matching here is *loose*
  (lowercased word tokens) because the job is DISCOVERY; exact market resolution
  still uses the strict matcher in mention_counts.py. Keeping the two separate is
  deliberate (loose = "what's in the data", strict = "what resolves a market").

Exactness:
  To bound memory, phrases seen in < PRUNE_FLOOR fights are dropped mid-scan.
  PRUNE_FLOOR (3) is far below the reporting cutoff (min-df, ~28 fights), and a
  phrase is pruned at most while it is still below the floor, so any reported
  phrase is exact to within < PRUNE_FLOOR counts (base-rate error < 0.05%).

Usage:
  python3 mine_vocabulary.py [DATA_DIR] [--min-df-frac 0.005] [--top 40] [-o vocabulary.csv]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from collections import Counter
from pathlib import Path

from mention_counts import norm, iter_records
from phrase_targets import load_phrase_targets

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR_DEFAULT = "~/ufc-mention-markets/ufc_cleaned_export"
OUT_DEFAULT = PROJECT_ROOT / "vocabulary.csv"

MAX_N = 3
PRUNE_EVERY = 400          # docs between memory prunes
PRUNE_FLOOR = 3            # drop phrases seen in < 3 fights during the scan
PRUNE_CAP = 1_200_000      # only prune an n-gram counter once it exceeds this size

TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")

STOPWORDS = set("""
a an and the of to in is it on at by for from with as he she they we you i me my
his her him them their our your this that these those there here be been being am
are was were do does did has have had will would can could should may might must
not no nor so if then than too very just now out up down over under again about
into onto off only own same s t re ll ve m o get got go going one two it's that's
he's she's i'm you're we're they're don't didn't doesn't can't won't what's
""".split())


def doc_ngram_sets(tokens: list[str]) -> dict[int, set[str]]:
    sets = {1: set(tokens)}
    for n in (2, 3):
        sets[n] = (
            {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}
            if len(tokens) >= n else set()
        )
    return sets


def prune(counter: Counter, floor: int) -> None:
    for key in [k for k, v in counter.items() if v < floor]:
        del counter[key]


def mine(data_dir: str):
    dfs = {n: Counter() for n in range(1, MAX_N + 1)}
    n_fights = skipped = 0
    for _fn, rec in iter_records(data_dir):
        if "__error__" in rec:
            continue
        dur = rec.get("duration_s")
        if dur is None or float(dur) == 0.0:
            skipped += 1
            continue
        n_fights += 1
        tokens = TOKEN_RE.findall(norm(rec.get("plain_text")).lower())
        sets = doc_ngram_sets(tokens)
        for n in range(1, MAX_N + 1):
            dfs[n].update(sets[n])
        if n_fights % PRUNE_EVERY == 0:
            for n in (2, 3):
                if len(dfs[n]) > PRUNE_CAP:
                    prune(dfs[n], PRUNE_FLOOR)
    for n in (2, 3):
        prune(dfs[n], PRUNE_FLOOR)
    return dfs, n_fights, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default=DATA_DIR_DEFAULT)
    ap.add_argument("--min-df-frac", type=float, default=0.005,
                    help="report phrases appearing in at least this fraction of fights")
    ap.add_argument("--top", type=int, default=35)
    ap.add_argument("-o", "--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    dfs, n_fights, skipped = mine(os.path.expanduser(args.data_dir))
    min_df = max(2, int(round(args.min_df_frac * n_fights)))

    rows = []
    for n in range(1, MAX_N + 1):
        for phrase, df in dfs[n].items():
            if df >= min_df:
                rows.append((phrase, n, df, df / n_fights))
    rows.sort(key=lambda r: -r[2])

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["phrase", "n_words", "fights", "base_rate"])
        for phrase, n, df, br in rows:
            w.writerow([phrase, n, df, round(br, 5)])

    print(f"Mined {n_fights} valid fights (skipped {skipped}). "
          f"min-df={min_df} (>= {args.min_df_frac:.1%}). "
          f"Reported phrases: {len(rows)} -> {args.out}")

    def show(title, n, exclude_stop=False):
        items = [(p, df, br) for (p, nn, df, br) in rows
                 if nn == n and not (exclude_stop and p in STOPWORDS)]
        print(f"\n=== {title} ===")
        for p, df, br in items[:args.top]:
            print(f"  {br * 100:5.1f}%  {df:6d}  {p}")

    show("Top single words (content; stopwords removed)", 1, exclude_stop=True)
    show("Top 2-word phrases", 2)
    show("Top 3-word phrases", 3)

    # Where do the current hard-coded market phrases land? (loose base rate)
    lookup = {}
    for phrase, n, df, br in rows:
        lookup[phrase] = (df, br)
    print("\n=== Loose base rate of current market phrases (for reference) ===")
    for phrase in load_phrase_targets():
        key = phrase.lower()
        if key in lookup:
            df, br = lookup[key]
            print(f"  {br * 100:5.1f}%  {df:6d}  {phrase}")
        else:
            print(f"   (<{args.min_df_frac:.1%})        {phrase}")


if __name__ == "__main__":
    main()
