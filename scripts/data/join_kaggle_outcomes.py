#!/usr/bin/env python3
"""Join transcript mention features to the Ultimate UFC Dataset.

Join rule, intentionally simple for the first pass:
  unordered {fighter_1_last, fighter_2_last} pair + event_date

The script auto-detects a fight-level CSV inside the Kaggle download by looking
for common UFC schema variants (R_fighter/B_fighter or RedFighter/BlueFighter
plus a date column), chooses the file with the most join hits, writes exact
matches to data/processed/joined_fights.csv, and prints examples of matches and failures.

Usage:
  python3 scripts/data/join_kaggle_outcomes.py
  python3 scripts/data/join_kaggle_outcomes.py KAGGLE_DATA_DIR
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ufc_mentions.mention_counts import last_name


MENTIONS_DEFAULT = PROJECT_ROOT / "data" / "processed" / "fight_mentions.csv"
KAGGLE_DEFAULT = PROJECT_ROOT / "kaggle_data" / "ultimate_ufc_dataset"
OUT_DEFAULT = PROJECT_ROOT / "data" / "processed" / "joined_fights.csv"

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%B %d, %Y",
    "%b %d, %Y",
]


@dataclass
class CsvSource:
    label: str
    rows: list[dict]


@dataclass
class Schema:
    date_col: str
    fighter_a_col: str
    fighter_b_col: str


def header_key(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def person_key(name):
    """Stable-ish surname key for a first-pass join."""
    ln = last_name(name)
    ln = unicodedata.normalize("NFKD", ln).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ln.lower())


def pair_key(name_a, name_b):
    a, b = person_key(name_a), person_key(name_b)
    if not a or not b:
        return None
    return tuple(sorted([a, b]))


def parse_date(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"\s+", " ", raw)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    # Very small fallback for strings like "2022-02-12 00:00:00".
    m = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", raw)
    if m:
        y, mo, d = map(int, m.groups())
        return datetime(y, mo, d).date().isoformat()
    return ""


def join_key_from_names_and_date(name_a, name_b, date_value):
    pk = pair_key(name_a, name_b)
    dt = parse_date(date_value)
    if not pk or not dt:
        return None
    return (pk[0], pk[1], dt)


def read_csv_file(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def read_csv_from_zip(zip_path, member):
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as raw:
            text = raw.read().decode("utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def discover_csv_sources(kaggle_dir):
    root = Path(kaggle_dir).expanduser()
    sources = []
    for csv_path in sorted(root.rglob("*.csv")):
        try:
            rows = read_csv_file(csv_path)
        except Exception as exc:
            print(f"Skipping unreadable CSV {csv_path}: {exc}")
            continue
        sources.append(CsvSource(str(csv_path.relative_to(root)), rows))

    for zip_path in sorted(root.rglob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            for member in members:
                try:
                    rows = read_csv_from_zip(zip_path, member)
                except Exception as exc:
                    print(f"Skipping unreadable CSV {zip_path}:{member}: {exc}")
                    continue
                label = f"{zip_path.relative_to(root)}:{member}"
                sources.append(CsvSource(label, rows))
        except Exception as exc:
            print(f"Skipping unreadable ZIP {zip_path}: {exc}")
    return sources


def infer_schema(rows):
    if not rows:
        return None
    headers = list(rows[0].keys())
    by_key = {header_key(h): h for h in headers}

    date_col = None
    for key in ["date", "eventdate", "fightdate"]:
        if key in by_key:
            date_col = by_key[key]
            break
    if date_col is None:
        date_like = [h for h in headers if "date" in header_key(h)]
        date_col = date_like[0] if date_like else None

    fighter_pairs = [
        ("rfighter", "bfighter"),
        ("redfighter", "bluefighter"),
        ("red", "blue"),
        ("fighter1", "fighter2"),
        ("fightera", "fighterb"),
    ]
    fighter_a_col = fighter_b_col = None
    for left, right in fighter_pairs:
        if left in by_key and right in by_key:
            fighter_a_col, fighter_b_col = by_key[left], by_key[right]
            break

    if fighter_a_col is None:
        fighter_cols = [
            h for h in headers
            if "fighter" in header_key(h) and header_key(h) not in {"winnerfighter"}
        ]
        if len(fighter_cols) >= 2:
            fighter_a_col, fighter_b_col = fighter_cols[0], fighter_cols[1]

    if not date_col or not fighter_a_col or not fighter_b_col:
        return None
    return Schema(date_col, fighter_a_col, fighter_b_col)


def load_mentions(path):
    rows = read_csv_file(path)
    for row in rows:
        row["_join_key"] = join_key_from_names_and_date(
            row.get("fighter_1"),
            row.get("fighter_2"),
            row.get("event_date"),
        )
    return rows


def build_kaggle_index(rows, schema):
    index = defaultdict(list)
    keyed = 0
    for row in rows:
        key = join_key_from_names_and_date(
            row.get(schema.fighter_a_col),
            row.get(schema.fighter_b_col),
            row.get(schema.date_col),
        )
        if key:
            row["_join_key"] = key
            index[key].append(row)
            keyed += 1
    return index, keyed


def choose_best_source(sources, mention_keys):
    best = None
    diagnostics = []
    for source in sources:
        schema = infer_schema(source.rows)
        if not schema:
            diagnostics.append((source.label, len(source.rows), "no recognizable fight schema", 0))
            continue
        index, keyed = build_kaggle_index(source.rows, schema)
        hits = sum(1 for key in mention_keys if key in index)
        diagnostics.append((source.label, len(source.rows), f"{keyed} keyed rows", hits))
        candidate = (hits, keyed, source, schema, index)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best, diagnostics


def pick(row, candidates):
    for col in candidates:
        if col in row and row[col] not in (None, ""):
            return row[col]
    return ""


def summarize_kaggle_row(row):
    left = pick(row, ["R_fighter", "RedFighter", "red_fighter", "Red Fighter"])
    right = pick(row, ["B_fighter", "BlueFighter", "blue_fighter", "Blue Fighter"])
    winner = pick(row, ["Winner", "winner"])
    method = pick(row, ["Finish", "finish", "Method", "method", "win_by", "WinBy"])
    return f"{left} vs {right} | winner={winner or '?'} | method={method or '?'}"


def print_examples(title, examples):
    print(f"\n{title}")
    print("-" * len(title))
    if not examples:
        print("  (none)")
        return
    for item in examples:
        print(f"  {item}")


def write_joined(out_path, exact_matches):
    if not exact_matches:
        return
    mention_cols = [c for c in exact_matches[0][0].keys() if not c.startswith("_")]
    kaggle_cols = [c for c in exact_matches[0][1].keys() if not c.startswith("_")]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=mention_cols + [f"kaggle_{c}" for c in kaggle_cols],
        )
        writer.writeheader()
        for mention, kaggle in exact_matches:
            row = {c: mention.get(c, "") for c in mention_cols}
            row.update({f"kaggle_{c}": kaggle.get(c, "") for c in kaggle_cols})
            writer.writerow(row)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Join transcript phrase rows with the local UFC stats CSV."
    )
    parser.add_argument("kaggle_dir", nargs="?", default=KAGGLE_DEFAULT)
    parser.add_argument("--mentions", default=MENTIONS_DEFAULT)
    parser.add_argument("-o", "--output", default=OUT_DEFAULT)
    return parser.parse_args()


def main():
    args = parse_args()
    kaggle_dir = Path(args.kaggle_dir).expanduser()
    mentions_path = Path(args.mentions).expanduser()
    out_path = Path(args.output).expanduser()

    if not mentions_path.exists():
        raise SystemExit(
            f"Missing {mentions_path}. Run: python3 scripts/data/build_match_csv.py"
        )
    if not kaggle_dir.exists():
        raise SystemExit(
            f"Missing {kaggle_dir}.\n"
            "Download the dataset first, for example:\n"
            "  kaggle datasets download mdabbert/ultimate-ufc-dataset "
            f"-p {kaggle_dir} --unzip"
        )

    mentions = load_mentions(mentions_path)
    mention_keys = {row["_join_key"] for row in mentions if row.get("_join_key")}
    sources = discover_csv_sources(kaggle_dir)
    if not sources:
        raise SystemExit(
            f"No CSVs found under {kaggle_dir}.\n"
            "Download the dataset first, for example:\n"
            "  kaggle datasets download mdabbert/ultimate-ufc-dataset "
            f"-p {kaggle_dir} --unzip"
        )

    best, diagnostics = choose_best_source(sources, mention_keys)
    print("Kaggle CSV candidates")
    print("---------------------")
    for label, row_count, schema_note, hits in sorted(diagnostics, key=lambda x: x[3], reverse=True):
        print(f"  {label}: {row_count} rows, {schema_note}, {hits} transcript-key hits")
    if not best:
        raise SystemExit("No usable fight-level CSV schema found in the Kaggle download.")

    _hits, keyed, source, schema, index = best
    exact = []
    ambiguous = []
    unmatched = []
    for row in mentions:
        key = row.get("_join_key")
        candidates = index.get(key, [])
        if len(candidates) == 1:
            exact.append((row, candidates[0]))
        elif len(candidates) > 1:
            ambiguous.append((row, candidates))
        else:
            unmatched.append(row)

    write_joined(out_path, exact)

    total = len(mentions)
    print("\nJoin results")
    print("------------")
    print(f"Mentions rows:       {total}")
    print(f"Kaggle source used:  {source.label}")
    print(f"Kaggle schema used:  {schema.fighter_a_col} / {schema.fighter_b_col} + {schema.date_col}")
    print(f"Kaggle keyed rows:   {keyed}")
    print(f"Exact matches:       {len(exact)} ({len(exact) / total * 100:.1f}%)")
    print(f"Ambiguous matches:   {len(ambiguous)} ({len(ambiguous) / total * 100:.1f}%)")
    print(f"Unmatched:           {len(unmatched)} ({len(unmatched) / total * 100:.1f}%)")
    print(f"Wrote exact matches: {out_path}")

    match_examples = []
    for mention, kaggle in exact[:8]:
        match_examples.append(
            f"{mention['event_date']} | {mention['fighter_1']} vs {mention['fighter_2']} "
            f"=> {summarize_kaggle_row(kaggle)}"
        )
    print_examples("Example exact matches", match_examples)

    miss_examples = []
    for mention in unmatched[:8]:
        miss_examples.append(
            f"{mention['event_date']} | {mention['fighter_1']} vs {mention['fighter_2']} "
            f"| key={mention.get('_join_key')}"
        )
    print_examples("Example failures to match", miss_examples)

    amb_examples = []
    for mention, candidates in ambiguous[:5]:
        amb_examples.append(
            f"{mention['event_date']} | {mention['fighter_1']} vs {mention['fighter_2']} "
            f"=> {len(candidates)} Kaggle rows"
        )
    print_examples("Example ambiguous matches", amb_examples)


if __name__ == "__main__":
    main()
