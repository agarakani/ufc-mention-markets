#!/usr/bin/env python3
"""Count candidate "mention" phrase frequencies across UFC transcripts — TWO tracks.

Real Polymarket "mention" markets resolve on the EXACT literal term plus only its
plural/possessive forms (e.g. 'knockout' -> matches 'knockout', 'knockouts',
"knockout's", "knockouts'"). They do NOT match synonyms or other word forms:
'knocked out', 'KO', 'TKO' would each be separate terms/markets.

So we report two SEPARATE, deliberately un-merged views:

  TRACK 1 — BROAD (commentary patterns): synonym / word-form groups OR'd together.
            Shows how often a *concept* appears in commentary. NOT how a market resolves.

  TRACK 2 — STRICT (market resolution): each individual literal phrase, matched on the
            exact term + plural/possessive ONLY. This is the Yes/No base rate a real
            market would actually settle on.

Both are document-frequency: a fight counts once if the term appears >= 1 time in
plain_text. Valid fights = duration_s != 0.0. Matching is case-insensitive and
whitespace-tolerant; curly apostrophes are normalized to straight ones.

Usage:
  python3 mention_counts.py [DATA_DIR]
  python3 mention_counts.py --selftest     # verify the STRICT matcher's behavior
"""

import gzip
import json
import os
import re
import sys
from collections import Counter

DATA_DIR_DEFAULT = "~/ufc-mention-markets/ufc_cleaned_export"

# ---- TRACK 2: STRICT literal market phrases (exact term + plural/possessive ONLY) ----
STRICT_PHRASES = [
    "TKO",
    "submission",
    "doctor",
    "split decision",
    "unanimous decision",
    "knockout",
    "knocked out",
    "KO",
]

# ---- TRACK 1: BROAD synonym / word-form groups (commentary concepts; editable) ----
# A fight counts for a group if ANY listed form appears. These are intentionally loose.
BROAD_GROUPS = {
    "knockout (concept)": [
        "knockout", "knocked out", "knocks out", "knock out", "knocking out",
        "KO", "KO'd", "TKO", "technical knockout", "out cold", "lights out",
    ],
    "submission (concept)": [
        "submission", "submit", "submits", "submitted", "submitting",
        "tap", "taps", "tapped", "tapout", "tap out", "tapped out", "taps out",
        "choke", "chokes", "choked", "choking",
    ],
    "decision (concept)": [
        "decision", "split decision", "unanimous decision", "majority decision",
        "scorecard", "scorecards", "judge", "judges", "the cards",
    ],
    "doctor stoppage (concept)": [
        "doctor", "doctor stoppage", "physician", "ringside doctor", "cageside doctor",
    ],
}

# Name suffixes stripped when picking a fighter's last name.
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Strict suffix = plural/possessive only: 's, s', ' (trailing), or s. Nothing else.
_SUFFIX = r"(?:'s|s'|'|s)?"
_START = r"(?<![A-Za-z])"          # not preceded by a letter
_END = r"(?![A-Za-z'])"            # not followed by a letter or apostrophe (rejects "KO'd")


def norm(s):
    """Normalize curly apostrophe to straight so one matcher handles both."""
    return (s or "").replace("’", "'")


def strict_pattern(phrase):
    """Whole 'word', case-insensitive: exact term + (plural/possessive) ONLY."""
    base = r"\s+".join(re.escape(w) for w in norm(phrase).split())
    return re.compile(_START + base + _SUFFIX + _END, re.IGNORECASE)


def last_name(full_name):
    toks = [t for t in re.split(r"\s+", norm(full_name).strip()) if t]
    while toks and toks[-1].lower().strip(".") in NAME_SUFFIXES:
        toks.pop()
    return toks[-1] if toks else ""


def iter_records(data_dir):
    for fn in sorted(os.listdir(data_dir)):
        if not fn.endswith(".json.gz"):
            continue
        path = os.path.join(data_dir, fn)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                yield fn, json.load(fh)
        except Exception as e:
            yield fn, {"__error__": str(e)}


def pct(n, d):
    return (100.0 * n / d) if d else 0.0


def selftest():
    """Verify STRICT matching == 'exact term + plural/possessive, nothing else'."""
    cases = [
        # (phrase, text, expected)
        ("knockout", "a brutal knockout ends it", True),
        ("knockout", "two knockouts tonight", True),
        ("knockout", "the knockout’s impact", True),   # curly possessive
        ("knockout", "he knocked out his foe", False),       # different word form
        ("knockout", "wins by KO", False),                   # synonym
        ("knockout", "a knockoutish blow", False),           # longer word
        ("doctor", "the doctor waved it off", True),
        ("doctor", "two doctors checked him", True),
        ("doctor", "the doctor's call", True),
        ("doctor", "a doctoral thesis", False),
        ("doctor", "he doctored the cut", False),
        ("submission", "looking for the submission", True),
        ("submission", "two submissions tonight", True),
        ("submission", "a resubmission of the form", False),  # embedded
        ("KO", "it is a KO", True),
        ("KO", "three KOs this card", True),
        ("KO", "the KO's replay", True),
        ("KO", "he got KO'd", False),                         # contraction/verb form
        ("KO", "a TKO finish", False),                        # embedded in TKO
        ("TKO", "wins by TKO", True),
        ("split decision", "wins by split decision", True),
        ("split decision", "two split decisions", True),
        ("split decision", "a unanimous decision", False),
        ("Silva", "Silva lands a jab", True),
        ("Silva", "Silva's corner", True),
        ("Silva", "the Silvas of MMA", True),
        ("Silva", "Silvana waves", False),                    # longer word
    ]
    ok = True
    for phrase, text, expected in cases:
        got = bool(strict_pattern(phrase).search(norm(text)))
        if got != expected:
            ok = False
        print(f"  [{'ok ' if got == expected else 'FAIL'}] "
              f"strict({phrase!r}) in {text!r} -> {got} (expected {expected})")
    print("\nSELFTEST:", "PASS" if ok else "FAIL")
    return ok


def main(data_dir):
    strict_pats = {p: strict_pattern(p) for p in STRICT_PHRASES}
    broad_pats = {g: [strict_pattern(m) for m in members]
                  for g, members in BROAD_GROUPS.items()}

    total = valid = skipped = errors = 0
    strict_hits = Counter({p: 0 for p in STRICT_PHRASES})
    broad_hits = Counter({g: 0 for g in BROAD_GROUPS})
    f1_hits = f2_hits = either_hits = both_hits = 0
    name_hits = Counter()

    for fn, rec in iter_records(data_dir):
        total += 1
        if "__error__" in rec:
            errors += 1
            continue
        dur = rec.get("duration_s")
        if dur is None or float(dur) == 0.0:
            skipped += 1
            continue
        valid += 1
        text = norm(rec.get("plain_text"))

        for p, pat in strict_pats.items():
            if pat.search(text):
                strict_hits[p] += 1
        for g, pats in broad_pats.items():
            if any(pat.search(text) for pat in pats):
                broad_hits[g] += 1

        ln1, ln2 = last_name(rec.get("fighter_1")), last_name(rec.get("fighter_2"))
        m1 = bool(ln1) and bool(strict_pattern(ln1).search(text))
        m2 = bool(ln2) and bool(strict_pattern(ln2).search(text))
        f1_hits += m1
        f2_hits += m2
        either_hits += (m1 or m2)
        both_hits += (m1 and m2)
        if m1:
            name_hits[ln1] += 1
        if m2:
            name_hits[ln2] += 1

    # ---------------- report ----------------
    print(f"Scanned {total} files: {valid} valid, "
          f"{skipped} skipped (duration_s==0.0/missing), {errors} read errors")
    print(f"Base = {valid} valid fights")

    print("\n" + "=" * 60)
    print("TRACK 1 — BROAD (commentary patterns; synonym groups OR'd)")
    print("   NOT how a real market resolves — concept prevalence only.")
    print("=" * 60)
    print(f"{'concept group':<26}{'fights':>8}{'% of fights':>14}")
    print("-" * 48)
    for g, n in sorted(broad_hits.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{g:<26}{n:>8}{pct(n, valid):>12.1f}%")

    print("\n" + "=" * 60)
    print("TRACK 2 — STRICT (market resolution; exact term + plural/possessive ONLY)")
    print("   This is the Yes/No base rate a literal Polymarket market settles on.")
    print("=" * 60)
    print(f"{'literal phrase':<22}{'fights':>8}{'% of fights':>14}")
    print("-" * 44)
    for p, n in sorted(strict_hits.items(), key=lambda kv: kv[1], reverse=True):
        print(f"{p:<22}{n:>8}{pct(n, valid):>12.1f}%")

    print("\nfighter last name — STRICT (exact surname + plural/possessive):")
    for label, n in [
        ("  fighter_1 last name", f1_hits),
        ("  fighter_2 last name", f2_hits),
        ("  either fighter", either_hits),
        ("  both fighters", both_hits),
    ]:
        print(f"{label:<26}{n:>8}{pct(n, valid):>12.1f}%")
    print("  top mentioned surnames:",
          ", ".join(f"{nm} ({c})" for nm, c in name_hits.most_common(10)))

    # The user's worked example, quantified.
    ks, kb = strict_hits["knockout"], broad_hits["knockout (concept)"]
    print(f"\nStrict-vs-broad gap (knockout): strict 'knockout' = {ks} fights "
          f"({pct(ks, valid):.1f}%); broad knockout concept = {kb} fights "
          f"({pct(kb, valid):.1f}%).")
    print(f"  -> ~{kb - ks} fights use KO/TKO/'knocked out' etc. and would NOT "
          f"resolve a literal 'knockout' market Yes.")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(0 if selftest() else 1)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(os.path.expanduser(args[0] if args else DATA_DIR_DEFAULT))
