#!/usr/bin/env python3
"""Walk-forward audit for exact grouped Kalshi mention rules.

This audits the same grouped rule forms used by the live Kalshi pricer. Each
historical fight is scored using only transcripts from earlier event dates, so
same-card and future fights cannot leak into the estimate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.kalshi_mentions import (
    GENERIC_FORMS,
    TranscriptCorpus,
    _parsed_date,
    grouped_matcher,
    normalized_name,
    wilson_lower_bound,
)


DATA_DEFAULT = ROOT / "ufc_cleaned_export"
RULES_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
OUT_DEFAULT = ROOT / "model_outputs" / "kalshi_grouped_rule_audit.csv"
CALIBRATION_DEFAULT = ROOT / "model_outputs" / "kalshi_grouped_rule_calibration.csv"
SUMMARY_DEFAULT = ROOT / "model_outputs" / "kalshi_grouped_rule_audit_summary.json"

AUDIT_FIELDS = [
    "phrase", "forms", "scored_fights", "positives", "actual_rate",
    "mean_probability", "mean_conservative_probability", "log_loss", "brier",
    "calibration_ece", "confidence_ok_rate", "old_rows", "old_actual_rate",
    "recent_rows", "recent_actual_rate", "recent_minus_old_actual_rate",
    "final_league_hits", "final_league_fights", "final_league_rate",
    "final_wilson_lower_95", "first_scored_date", "last_scored_date", "status",
]

CALIBRATION_FIELDS = [
    "phrase", "forms", "bin", "rows", "mean_predicted", "actual_rate",
    "min_predicted", "max_predicted",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_forms(row: dict) -> tuple[str, ...]:
    forms = str(row.get("forms") or "").strip()
    if forms:
        separator = r"\s*\|\s*" if "|" in forms else r"\s*/\s*"
        parts = re.split(separator, forms)
    else:
        parts = re.split(r"\s*/\s*", str(row.get("phrase") or ""))
    return tuple(part.strip() for part in parts if part.strip())


def load_rule_groups(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run scripts/live/refresh_dashboard.py once to discover Kalshi rules.")
    groups = {}
    for row in read_csv(path):
        forms = parse_forms(row)
        if not forms:
            continue
        key = tuple(form.casefold() for form in forms)
        groups.setdefault(key, {
            "phrase": " / ".join(forms),
            "forms": forms,
        })
    if not groups:
        raise SystemExit(f"No grouped rule forms found in {path}.")
    return sorted(groups.values(), key=lambda item: item["phrase"].casefold())


def grouped_indices(corpus: TranscriptCorpus) -> list[tuple[object, list[int]]]:
    by_date = defaultdict(list)
    for index, fight in enumerate(corpus.fights):
        parsed = _parsed_date(fight.event_date)
        if parsed is not None:
            by_date[parsed].append(index)
    return sorted(by_date.items(), key=lambda item: item[0])


def entity_terms(corpus: TranscriptCorpus, indices: set[int]) -> set[str]:
    terms = set()
    for index in indices:
        fight = corpus.fights[index]
        for value in (fight.fighter_1, fight.fighter_2, fight.nickname_1, fight.nickname_2):
            value = str(value or "").strip().casefold()
            if value:
                terms.add(value)
                terms.update(token for token in re.findall(r"[a-z0-9']+", value) if len(token) >= 3)
    return terms


def estimate_from_prior(
    *,
    corpus: TranscriptCorpus,
    forms: tuple[str, ...],
    labels: dict[int, bool],
    eligible: set[int],
    league_hits: int,
    league_fights: int,
    fight_index: int,
    min_fighter_fights: int,
    fighter_specific_k: float = 4.0,
    contextual_k: float = 25.0,
) -> dict | None:
    if league_fights <= 0:
        return None

    fight = corpus.fights[fight_index]
    keys = [
        key for key in (normalized_name(fight.fighter_1), normalized_name(fight.fighter_2))
        if key in corpus.by_fighter
    ]
    relevant = set()
    for key in keys:
        relevant.update(corpus.by_fighter[key])
    relevant &= eligible

    fighter_hits = sum(1 for index in relevant if labels[index])
    fighter_n = len(relevant)
    league_rate = league_hits / league_fights
    normalized_forms = {re.sub(r"\s+", " ", form.casefold()).strip() for form in forms}

    if league_rate >= 0.30 or normalized_forms & GENERIC_FORMS:
        probability = league_rate
        conservative_probability = wilson_lower_bound(league_hits, league_fights)
        word_type = "generic"
    elif normalized_forms & entity_terms(corpus, relevant):
        probability = (fighter_hits + fighter_specific_k * league_rate) / (fighter_n + fighter_specific_k)
        conservative_probability = wilson_lower_bound(fighter_hits, fighter_n) if fighter_n else None
        word_type = "fighter_specific"
    else:
        probability = (fighter_hits + contextual_k * league_rate) / (fighter_n + contextual_k)
        conservative_probability = wilson_lower_bound(fighter_hits, fighter_n) if fighter_n else None
        word_type = "contextual"

    return {
        "probability": probability,
        "conservative_probability": conservative_probability,
        "word_type": word_type,
        "league_hits": league_hits,
        "league_fights": league_fights,
        "fighter_hits": fighter_hits,
        "fighter_fights": fighter_n,
        "confidence_ok": fighter_n >= min_fighter_fights,
    }


def clipped(probability: float) -> float:
    return min(1.0 - 1e-6, max(1e-6, probability))


def metric_rows(records: list[dict], *, phrase: str, forms: tuple[str, ...], min_audit_rows: int) -> dict:
    actuals = [int(record["actual"]) for record in records]
    probs = [clipped(float(record["probability"])) for record in records]
    conservative = [
        record["conservative_probability"]
        for record in records
        if record.get("conservative_probability") is not None
    ]
    positives = sum(actuals)
    log_loss = -sum(
        actual * math.log(prob) + (1 - actual) * math.log(1 - prob)
        for actual, prob in zip(actuals, probs)
    ) / len(records)
    brier = sum((prob - actual) ** 2 for actual, prob in zip(actuals, probs)) / len(records)

    split = max(1, min(len(records) - 1, int(len(records) * 0.80))) if len(records) > 1 else len(records)
    old = records[:split]
    recent = records[split:]

    def actual_rate(rows: list[dict]) -> float | None:
        return sum(int(row["actual"]) for row in rows) / len(rows) if rows else None

    final = records[-1]
    old_rate = actual_rate(old)
    recent_rate = actual_rate(recent)
    status = "measured" if len(records) >= min_audit_rows and positives > 0 else "insufficient_sample"
    return {
        "phrase": phrase,
        "forms": " | ".join(forms),
        "scored_fights": len(records),
        "positives": positives,
        "actual_rate": positives / len(records),
        "mean_probability": sum(probs) / len(probs),
        "mean_conservative_probability": (
            sum(conservative) / len(conservative) if conservative else None
        ),
        "log_loss": log_loss,
        "brier": brier,
        "calibration_ece": calibration_ece(records),
        "confidence_ok_rate": sum(bool(row["confidence_ok"]) for row in records) / len(records),
        "old_rows": len(old),
        "old_actual_rate": old_rate,
        "recent_rows": len(recent),
        "recent_actual_rate": recent_rate,
        "recent_minus_old_actual_rate": (
            recent_rate - old_rate if recent_rate is not None and old_rate is not None else None
        ),
        "final_league_hits": final["league_hits"],
        "final_league_fights": final["league_fights"],
        "final_league_rate": final["league_hits"] / final["league_fights"] if final["league_fights"] else None,
        "final_wilson_lower_95": wilson_lower_bound(final["league_hits"], final["league_fights"]),
        "first_scored_date": records[0]["event_date"],
        "last_scored_date": records[-1]["event_date"],
        "status": status,
    }


def calibration_ece(records: list[dict], bins: int = 5) -> float:
    rows = calibration_rows(records, bins=bins)
    total = len(records)
    return sum(
        row["rows"] / total * abs(row["mean_predicted"] - row["actual_rate"])
        for row in rows
        if total
    )


def calibration_rows(records: list[dict], bins: int = 5) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        probability = max(0.0, min(1.0, float(record["probability"])))
        bin_index = min(bins, int(probability * bins) + 1)
        grouped[bin_index].append(record)
    rows = []
    for bin_index in range(1, bins + 1):
        part = grouped.get(bin_index, [])
        if not part:
            continue
        probs = [float(row["probability"]) for row in part]
        actuals = [int(row["actual"]) for row in part]
        rows.append({
            "bin": bin_index,
            "rows": len(part),
            "mean_predicted": sum(probs) / len(probs),
            "actual_rate": sum(actuals) / len(actuals),
            "min_predicted": min(probs),
            "max_predicted": max(probs),
        })
    return rows


def score_group(
    corpus: TranscriptCorpus,
    date_groups: list[tuple[object, list[int]]],
    group: dict,
    *,
    min_fighter_fights: int,
    min_audit_rows: int,
    bins: int,
) -> tuple[dict, list[dict]]:
    forms = group["forms"]
    matcher = grouped_matcher(forms)
    labels = {index: bool(matcher(fight.text)) for index, fight in enumerate(corpus.fights)}
    eligible: set[int] = set()
    league_hits = 0
    league_fights = 0
    records = []

    for event_date, indices in date_groups:
        for index in indices:
            estimate = estimate_from_prior(
                corpus=corpus,
                forms=forms,
                labels=labels,
                eligible=eligible,
                league_hits=league_hits,
                league_fights=league_fights,
                fight_index=index,
                min_fighter_fights=min_fighter_fights,
            )
            if estimate is None:
                continue
            records.append({
                **estimate,
                "event_date": event_date.isoformat(),
                "actual": int(labels[index]),
            })
        for index in indices:
            eligible.add(index)
            league_fights += 1
            league_hits += int(labels[index])

    if not records:
        raise SystemExit(f"No walk-forward rows generated for {group['phrase']}.")

    summary = metric_rows(
        records,
        phrase=group["phrase"],
        forms=forms,
        min_audit_rows=min_audit_rows,
    )
    calibration = []
    for row in calibration_rows(records, bins=bins):
        calibration.append({
            "phrase": group["phrase"],
            "forms": " | ".join(forms),
            **row,
        })
    return summary, calibration


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}"
    return str(value)


def format_rows(rows: list[dict], fields: list[str]) -> list[dict]:
    return [{field: format_value(row.get(field)) for field in fields} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit exact grouped Kalshi mention rules with walk-forward estimates.")
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--rules-csv", default=str(RULES_DEFAULT))
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--calibration-out", default=str(CALIBRATION_DEFAULT))
    parser.add_argument("--summary-out", default=str(SUMMARY_DEFAULT))
    parser.add_argument("--min-fighter-fights", type=int, default=15)
    parser.add_argument("--min-audit-rows", type=int, default=500)
    parser.add_argument("--bins", type=int, default=5)
    args = parser.parse_args()

    corpus = TranscriptCorpus.load(args.data_dir)
    date_groups = grouped_indices(corpus)
    groups = load_rule_groups(Path(args.rules_csv))

    audit_rows = []
    calibration = []
    for group in groups:
        summary, group_calibration = score_group(
            corpus,
            date_groups,
            group,
            min_fighter_fights=args.min_fighter_fights,
            min_audit_rows=args.min_audit_rows,
            bins=args.bins,
        )
        audit_rows.append(summary)
        calibration.extend(group_calibration)

    audit_rows.sort(key=lambda row: row["log_loss"])
    write_csv(Path(args.out), format_rows(audit_rows, AUDIT_FIELDS), AUDIT_FIELDS)
    write_csv(Path(args.calibration_out), format_rows(calibration, CALIBRATION_FIELDS), CALIBRATION_FIELDS)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rules_csv": str(Path(args.rules_csv)),
        "data_dir": str(Path(args.data_dir)),
        "groups": len(audit_rows),
        "valid_fights": len(corpus.fights),
        "status": "unvalidated_audit_generated",
        "claim": "No trade-ready edge is claimed by this audit output.",
        "min_audit_rows": args.min_audit_rows,
    }
    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {Path(args.out).relative_to(ROOT)}")
    print(f"Wrote {Path(args.calibration_out).relative_to(ROOT)}")
    print(f"Audited {len(audit_rows)} exact grouped Kalshi rule sets over {len(corpus.fights)} valid fights.")
    print("No trade-ready edge is claimed; use these metrics as validation evidence only.")


if __name__ == "__main__":
    main()
