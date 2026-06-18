#!/usr/bin/env python3
"""Discover a fighter's 'announcer signature' from the transcripts ALONE.

This is the data-backed replacement for "an LLM knowing the fighter." For any
fighter, it finds the phrases announcers say DISPROPORTIONATELY in their fights
versus the league-wide baseline:

    lift = (rate in this fighter's fights) / (rate across all fights)

High-lift phrases are what's characteristic of the fighter -- nickname, origin,
style, rivals, catchphrases -- learned purely from our corpus, no external
knowledge and nothing typed by a human. The bettable number is still the grounded
historical rate ("their%"); lift only RANKS which phrases are theirs.

Usage:
  python3 fighter_signature.py ["Conor McGregor" "Max Holloway" ...]
"""

from __future__ import annotations

import os
import sys
from collections import Counter

from mention_counts import norm, iter_records
from mine_vocabulary import STOPWORDS, TOKEN_RE

DATA = os.path.expanduser("~/ufc-mention-markets/ufc_cleaned_export")
MIN_SUPPORT = 3      # phrase must appear in >= 3 of the fighter's fights
MIN_LIFT = 2.0       # and be >= 2x over-represented vs the league
TOP = 18


def ngram_set(text: str) -> set[str]:
    toks = TOKEN_RE.findall(text.lower())
    s = set(toks)
    s |= {f"{toks[i]} {toks[i + 1]}" for i in range(len(toks) - 1)}
    return s


def is_content(p: str) -> bool:
    return any(t not in STOPWORDS and len(t) >= 3 for t in p.split())


def name_tokens(name: str) -> set[str]:
    return {t.lower() for t in name.split() if len(t) > 1}


def _strip_poss(tok: str) -> str:
    if tok.endswith("'s"):
        return tok[:-2]
    return tok[:-1] if tok.endswith("'") else tok


def has_own_name(phrase: str, own: set[str]) -> bool:
    # True if any token (incl. possessive forms like "conor's") is the fighter's name.
    return any(_strip_poss(t) in own for t in phrase.split())


def main():
    names = sys.argv[1:] or ["Conor McGregor", "Max Holloway", "Khamzat Chimaev"]

    # Pass 1: collect each target's per-fight n-gram sets + total fight count.
    target_sets = {n: [] for n in names}
    total = 0
    for _fn, rec in iter_records(DATA):
        if "__error__" in rec or float(rec.get("duration_s") or 0.0) == 0.0:
            continue
        total += 1
        f1, f2 = rec.get("fighter_1", ""), rec.get("fighter_2", "")
        hit = [n for n in names if n in (f1, f2)]
        if hit:
            s = ngram_set(norm(rec.get("plain_text")))
            for n in hit:
                target_sets[n].append(s)

    # Build the union candidate set (content phrases with enough support per fighter).
    candidates = set()
    fighter_info = {}
    for n, sets in target_sets.items():
        fdf = Counter()
        for s in sets:
            fdf.update(s)
        own = name_tokens(n)
        cand = {p for p, c in fdf.items()
                if c >= MIN_SUPPORT and is_content(p) and not has_own_name(p, own)}
        fighter_info[n] = (fdf, len(sets), cand)
        candidates |= cand

    # Pass 2: league-wide document frequency for just the candidate phrases.
    gdf = Counter()
    for _fn, rec in iter_records(DATA):
        if "__error__" in rec or float(rec.get("duration_s") or 0.0) == 0.0:
            continue
        s = ngram_set(norm(rec.get("plain_text")))
        for p in candidates & s:
            gdf[p] += 1

    for n, (fdf, nf, cand) in fighter_info.items():
        if nf < MIN_SUPPORT:
            print(f"\n{n}: only {nf} fights — too few to characterize.")
            continue
        rows = []
        for p in cand:
            their = fdf[p] / nf
            league = gdf[p] / total
            lift = their / league if league else float("inf")
            if lift >= MIN_LIFT:
                rows.append((p, their, league, lift, fdf[p]))
        rows.sort(key=lambda r: -r[3])
        print(f"\n=== {n}: {nf} fights — announcer signature (discovered from data) ===")
        print(f"  {'lift':>5}  {'their%':>6}  {'league%':>7}  phrase")
        for p, their, league, lift, c in rows[:TOP]:
            print(f"  {lift:5.1f}x  {their * 100:5.0f}%  {league * 100:6.1f}%  {p}  ({c}/{nf})")


if __name__ == "__main__":
    main()
