#!/usr/bin/env python3
"""Per-fighter historical mention rates -- the engine for ENTITY-driven fight markets.

The valuable mention markets are fight-specific and entity-driven, e.g.
  "Will announcers say 'Suga'?"        (O'Malley's nickname)
  "Will they mention 'Khabib'?"        (Makhachev's mentor)
  "Will they say 'leg kicks'?"         (Gaethje's signature)

None of these come from a stats model -- they come from WHO is fighting. But our
transcript corpus can measure them directly: pull all of a fighter's past fights
and count how often a phrase actually got said. That historical rate IS the
prediction for the next fight.

This first module does the cleanest, highest-signal case we already have data for:
a fighter's own NICKNAME (stored on every transcript). It produces, per fighter,
the share of their fights in which announcers said their nickname -- the base rate
for a "Will they say '<nickname>'?" market.

The same per-fighter-history primitive generalizes to rivals, gym, origin, style,
and arena (see ENTITY ROADMAP at the bottom).

Usage:
  python3 fighter_mention_rates.py [DATA_DIR] [--min-fights 4] [--top 30]
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict

from mention_counts import strict_pattern, norm, iter_records

DATA_DIR_DEFAULT = "~/ufc-mention-markets/ufc_cleaned_export"
# Stars from the example markets, to look up by name substring.
SPOTLIGHT = ["O'Malley", "Gaethje", "Topuria", "Chimaev", "Pereira",
             "Makhachev", "Sandhagen", "Adesanya", "Holloway", "Poirier"]


def collect(data_dir):
    """name -> {nick, said, fights}; said = fights whose transcript said the nickname."""
    stats = defaultdict(lambda: {"nick": "", "said": 0, "fights": 0})
    overall_said = overall_fights = 0
    pat_cache = {}
    for _fn, rec in iter_records(data_dir):
        if "__error__" in rec:
            continue
        if float(rec.get("duration_s") or 0.0) == 0.0:
            continue
        text = norm(rec.get("plain_text"))
        for who in ("1", "2"):
            name = (rec.get(f"fighter_{who}") or "").strip()
            nick = (rec.get(f"fighter_{who}_nickname") or "").strip()
            if not name or len(nick) < 2:
                continue
            pat = pat_cache.get(nick) or pat_cache.setdefault(nick, strict_pattern(nick))
            said = bool(pat.search(text))
            s = stats[name]
            s["nick"], s["fights"] = nick, s["fights"] + 1
            s["said"] += said
            overall_said += said
            overall_fights += 1
    return stats, overall_said, overall_fights


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", default=DATA_DIR_DEFAULT)
    ap.add_argument("--min-fights", type=int, default=4)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    stats, said, fights = collect(os.path.expanduser(args.data_dir))
    print(f"Nickname-mention base rate: {said / fights * 100:.1f}% "
          f"of {fights} fighter-fights (fighters with a listed nickname).\n"
          f"=> a blind 'Will they say <nickname>?' market is ~{said / fights:.2f} on average,\n"
          f"   but it varies a lot by fighter -- which is where the edge is:")

    rows = [(n, s["nick"], s["said"], s["fights"], s["said"] / s["fights"])
            for n, s in stats.items() if s["fights"] >= args.min_fights]
    rows.sort(key=lambda r: (-r[4], -r[3]))

    def show(title, items):
        print(f"\n=== {title} ===")
        print(f"  {'rate':>5}  {'n':>3}  fighter  ->  nickname")
        for name, nick, sd, ft, rate in items:
            print(f"  {rate * 100:4.0f}%  {ft:>3}  {name}  ->  “{nick}”  ({sd}/{ft})")

    show(f"Highest nickname-mention rate (>= {args.min_fights} fights)", rows[:args.top])
    show("Lowest nickname-mention rate", list(reversed(rows[-12:])))

    spot = []
    for name, nick, sd, ft, rate in rows:
        if any(s.lower() in name.lower() for s in SPOTLIGHT):
            spot.append((name, nick, sd, ft, rate))
    if spot:
        show("Spotlight fighters (from the example markets)", spot)


if __name__ == "__main__":
    main()
