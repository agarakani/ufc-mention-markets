#!/usr/bin/env python3
"""First-pass outcome-vs-mention sanity tables.

This is deliberately not a predictive model yet. It answers the question we need
before modeling: when a real fight outcome happens, how often does the literal
market phrase get said, and when the phrase gets said, what outcome did the fight
actually have?

Input:
  joined_fights.csv, produced by join_kaggle_outcomes.py

Output:
  plain-text tables for quick review.
"""

import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
JOINED_DEFAULT = PROJECT_ROOT / "joined_fights.csv"

PHRASES = [
    ("mention_knockout", "knockout"),
    ("mention_tko", "TKO"),
    ("mention_knocked_out", "knocked out"),
    ("mention_submission", "submission"),
    ("mention_split_decision", "split decision"),
    ("mention_unanimous_decision", "unanimous decision"),
    ("mention_doctor", "doctor"),
]

OUTCOME_TARGETS = [
    ("mention_knockout", "knockout", "KO/TKO"),
    ("mention_tko", "TKO", "KO/TKO"),
    ("mention_knocked_out", "knocked out", "KO/TKO"),
    ("mention_submission", "submission", "SUB"),
    ("mention_split_decision", "split decision", "S-DEC"),
    ("mention_unanimous_decision", "unanimous decision", "U-DEC"),
]


def truthy(value):
    return str(value).strip().lower() == "true"


def pct(num, den):
    return 100.0 * num / den if den else 0.0


def finish(row):
    return (row.get("kaggle_finish") or "").strip() or "UNKNOWN"


def simple_group(f):
    if f in {"U-DEC", "S-DEC", "M-DEC"}:
        return "DEC"
    if f in {"KO/TKO", "SUB"}:
        return f
    if f == "UNKNOWN":
        return "UNKNOWN"
    return "OTHER"


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def print_table(headers, rows, aligns=None):
    aligns = aligns or ["left"] * len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt(row):
        cells = []
        for i, cell in enumerate(row):
            s = str(cell)
            cells.append(s.rjust(widths[i]) if aligns[i] == "right" else s.ljust(widths[i]))
        return "  ".join(cells)

    print(fmt(headers))
    print(fmt(["-" * w for w in widths]))
    for row in rows:
        print(fmt(row))


def main(path=JOINED_DEFAULT):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run: python3 join_kaggle_outcomes.py")

    rows = read_rows(path)
    total = len(rows)
    finish_counts = Counter(finish(r) for r in rows)
    group_counts = Counter(simple_group(finish(r)) for r in rows)

    print(f"Joined fights analyzed: {total}")
    print("\nActual outcome distribution")
    print("---------------------------")
    outcome_rows = [
        [name, count, f"{pct(count, total):.1f}%"]
        for name, count in finish_counts.most_common()
    ]
    print_table(["finish", "fights", "%"], outcome_rows, ["left", "right", "right"])

    print("\nStrict phrase base rates on matched fights")
    print("------------------------------------------")
    base_rows = []
    for col, label in PHRASES:
        hits = sum(truthy(r.get(col)) for r in rows)
        base_rows.append([label, hits, f"{pct(hits, total):.1f}%"])
    print_table(["phrase", "Yes fights", "% Yes"], base_rows, ["left", "right", "right"])

    print("\nOutcome-alignment checks")
    print("------------------------")
    align_rows = []
    for col, label, target in OUTCOME_TARGETS:
        phrase_yes = [r for r in rows if truthy(r.get(col))]
        target_rows = [r for r in rows if finish(r) == target]
        both = [r for r in phrase_yes if finish(r) == target]
        align_rows.append([
            label,
            target,
            len(phrase_yes),
            len(target_rows),
            len(both),
            f"{pct(len(both), len(target_rows)):.1f}%",
            f"{pct(len(both), len(phrase_yes)):.1f}%",
        ])
    print_table(
        [
            "phrase",
            "target outcome",
            "phrase Yes",
            "target fights",
            "overlap",
            "P(phrase | target)",
            "P(target | phrase)",
        ],
        align_rows,
        ["left", "left", "right", "right", "right", "right", "right"],
    )

    print("\nWhen phrase is said, what actually happened?")
    print("--------------------------------------------")
    comp_rows = []
    for col, label in PHRASES:
        hit_rows = [r for r in rows if truthy(r.get(col))]
        grouped = Counter(simple_group(finish(r)) for r in hit_rows)
        comp_rows.append([
            label,
            len(hit_rows),
            f"{pct(grouped['KO/TKO'], len(hit_rows)):.1f}%",
            f"{pct(grouped['SUB'], len(hit_rows)):.1f}%",
            f"{pct(grouped['DEC'], len(hit_rows)):.1f}%",
            f"{pct(grouped['OTHER'], len(hit_rows)):.1f}%",
            f"{pct(grouped['UNKNOWN'], len(hit_rows)):.1f}%",
        ])
    print_table(
        ["phrase", "Yes fights", "KO/TKO", "SUB", "DEC", "OTHER", "UNKNOWN"],
        comp_rows,
        ["left", "right", "right", "right", "right", "right", "right"],
    )

    print("\nActual outcome -> strict phrase rates")
    print("-------------------------------------")
    selected_finishes = ["KO/TKO", "SUB", "U-DEC", "S-DEC", "M-DEC"]
    rows_by_finish = defaultdict(list)
    for row in rows:
        rows_by_finish[finish(row)].append(row)

    rate_rows = []
    for f in selected_finishes:
        subset = rows_by_finish[f]
        if not subset:
            continue
        rate_rows.append([
            f,
            len(subset),
            *[
                f"{pct(sum(truthy(r.get(col)) for r in subset), len(subset)):.1f}%"
                for col, _label in PHRASES
            ],
        ])
    print_table(
        ["actual finish", "fights"] + [label for _col, label in PHRASES],
        rate_rows,
        ["left", "right"] + ["right"] * len(PHRASES),
    )

    print("\nNotes")
    print("-----")
    print("- These are literal mention outcomes, not broad synonym groups.")
    print("- Kaggle does not expose a clean current-fight doctor-stoppage outcome column here,")
    print("  so 'doctor' is reported as a standalone mention market, not aligned to an outcome target.")


if __name__ == "__main__":
    main()
