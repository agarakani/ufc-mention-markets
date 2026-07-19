#!/usr/bin/env python3
"""Weekly walk-forward update: learn from settled cards, prove it, then adopt.

After a card settles, its results become labeled training rows. This script
answers the only question that matters before using them: does training on
earlier settled cards actually improve predictions on the next card?

For each held-out card it trains one model on transcripts plus the labels
from cards before it, at several label weights including zero, then scores
every prediction on the held-out card against the real outcomes. The weight
with the best average held-out log loss wins and is written to
data/processed/model_update_config.json, which the live model reads. If
plain transcripts win, the config says weight zero and nothing changes.

The evaluation never lets a card see its own labels, so every score is a
true front test. Runs on its own after each settle; safe to run by hand.

Usage:
  python3 scripts/model/walkforward_update.py
  python3 scripts/model/walkforward_update.py --force   # ignore up-to-date check
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from ufc_mentions.kalshi_context_model import (  # noqa: E402
    HISTORY_DEFAULT,
    LABELS_DEFAULT,
    MASTER_DEFAULT,
    UPCOMING_DEFAULT,
    UPDATE_CONFIG_DEFAULT,
    KalshiFightContextModel,
)
from ufc_mentions.kalshi_mentions import TranscriptCorpus  # noqa: E402

DATA_DIR_DEFAULT = ROOT / "ufc_cleaned_export"
REPORT_PATH = ROOT / "model_outputs" / "walkforward_report.json"
WEIGHTS = [0.0, 3.0, 5.0, 10.0]


def forms_from_phrase(phrase: str) -> tuple[str, ...]:
    parts = [part.strip() for part in str(phrase).split("/") if part.strip()]
    return tuple(parts) if parts else (str(phrase).strip(),)


def clipped(p: float) -> float:
    return min(1 - 1e-6, max(1e-6, float(p)))


def card_log_loss(model: KalshiFightContextModel, card_labels: pd.DataFrame) -> tuple[float | None, int]:
    """Mean log loss of the model's predictions on one held-out card."""
    losses = []
    for _, label in card_labels.iterrows():
        prediction = model.predict(
            forms_from_phrase(label["phrase"]),
            str(label["fighter_1"]),
            str(label["fighter_2"]),
            str(label["event_date"]),
        )
        if prediction.status != "ok" or prediction.probability is None:
            continue
        p = clipped(prediction.probability)
        y = 1 if str(label["outcome"]).strip().lower() == "yes" else 0
        losses.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    if not losses:
        return None, 0
    return sum(losses) / len(losses), len(losses)


def pick_best_weight(means: dict[float, float | None]) -> float:
    """Lowest held-out log loss wins; ties go to the smaller weight."""
    scored = [(mean, weight) for weight, mean in means.items() if mean is not None]
    if not scored:
        return 0.0
    best_mean = min(mean for mean, _ in scored)
    candidates = [weight for mean, weight in scored if abs(mean - best_mean) < 1e-9]
    return min(candidates)


def up_to_date(labels: pd.DataFrame) -> bool:
    if not REPORT_PATH.exists():
        return False
    try:
        report = json.loads(REPORT_PATH.read_text())
    except (ValueError, json.JSONDecodeError):
        return False
    return (
        int(report.get("labels_count", -1)) == len(labels)
        and report.get("cards") == sorted(labels["event_date"].astype(str).unique().tolist())
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--data-dir", default=str(DATA_DIR_DEFAULT))
    args = parser.parse_args()

    if not LABELS_DEFAULT.exists():
        raise SystemExit("No settled labels yet; nothing to learn from.")
    labels = pd.read_csv(LABELS_DEFAULT)
    labels = labels.loc[
        labels["outcome"].astype(str).str.lower().isin(["yes", "no"])
        & labels["fighter_1"].astype(str).str.strip().ne("")
        & labels["event_date"].astype(str).str.strip().ne("")
    ]
    if labels.empty:
        raise SystemExit("No usable labels.")
    if not args.force and up_to_date(labels):
        print("Walk-forward report already covers the current labels; nothing to do.")
        return

    cards = sorted(labels["event_date"].astype(str).unique())
    print(f"{len(labels)} labels across {len(cards)} settled cards: {', '.join(cards)}")
    if len(cards) < 2:
        print("Need at least two settled cards to front-test; keeping weight 0.")
        UPDATE_CONFIG_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CONFIG_DEFAULT.write_text(json.dumps({"label_weight": 0.0}) + "\n")
        return

    print("Loading transcript corpus and stat tables once...")
    corpus = TranscriptCorpus.load(args.data_dir)
    history = pd.read_csv(HISTORY_DEFAULT)
    upcoming = pd.read_csv(UPCOMING_DEFAULT) if UPCOMING_DEFAULT.exists() else pd.DataFrame()
    master = pd.read_csv(MASTER_DEFAULT) if MASTER_DEFAULT.exists() else pd.DataFrame()

    # Hold out each card that has at least one earlier card to learn from.
    holdouts = cards[1:]
    per_weight: dict[float, dict] = {}
    for weight in WEIGHTS:
        card_scores = {}
        for holdout in holdouts:
            model = KalshiFightContextModel(
                history, corpus,
                upcoming=upcoming, master=master,
                labels=labels, label_weight=weight,
            )
            model.label_cutoff_date = holdout
            card_labels = labels.loc[labels["event_date"].astype(str) == holdout]
            loss, scored = card_log_loss(model, card_labels)
            card_scores[holdout] = {"log_loss": loss, "scored": scored}
            print(f"  weight {weight:g} | holdout {holdout}: "
                  f"log loss {loss:.4f} over {scored} markets" if loss is not None
                  else f"  weight {weight:g} | holdout {holdout}: no scorable predictions")
        losses = [entry["log_loss"] for entry in card_scores.values() if entry["log_loss"] is not None]
        per_weight[weight] = {
            "cards": card_scores,
            "mean_log_loss": sum(losses) / len(losses) if losses else None,
        }

    means = {weight: per_weight[weight]["mean_log_loss"] for weight in WEIGHTS}
    chosen = pick_best_weight(means)
    baseline = means.get(0.0)
    chosen_mean = means.get(chosen)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels_count": len(labels),
        "cards": cards,
        "holdout_cards": holdouts,
        "weights_tested": WEIGHTS,
        "per_weight": {str(weight): value for weight, value in per_weight.items()},
        "baseline_log_loss": baseline,
        "chosen_weight": chosen,
        "chosen_log_loss": chosen_mean,
        "note": (
            "Held-out cards never see their own labels. Weight 0 means plain "
            "transcripts; a nonzero weight is adopted only when it scored "
            "better on the held-out cards."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    UPDATE_CONFIG_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_CONFIG_DEFAULT.write_text(json.dumps({
        "label_weight": chosen,
        "chosen_at": report["generated_at"],
        "basis": f"walk-forward over {len(holdouts)} held-out cards",
    }, indent=2) + "\n")

    print(f"\nBaseline (transcripts only): {baseline:.4f}" if baseline is not None else "\nBaseline: n/a")
    for weight in WEIGHTS[1:]:
        mean = means[weight]
        print(f"Weight {weight:g}: {mean:.4f}" if mean is not None else f"Weight {weight:g}: n/a")
    print(f"Chosen label weight: {chosen:g}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)} and {UPDATE_CONFIG_DEFAULT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
