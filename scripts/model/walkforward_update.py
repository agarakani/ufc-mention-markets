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
    apply_group_bias,
    group_bias_key,
)
from ufc_mentions.kalshi_mentions import TranscriptCorpus  # noqa: E402

DATA_DIR_DEFAULT = ROOT / "ufc_cleaned_export"
REPORT_PATH = ROOT / "model_outputs" / "walkforward_report.json"
GATE_REPORT_PATH = ROOT / "model_outputs" / "v2_gate_report.json"
WEIGHTS = [0.0, 3.0, 5.0, 10.0]
MIN_CALIBRATION_PAIRS = 30


def forms_from_phrase(phrase: str) -> tuple[str, ...]:
    parts = [part.strip() for part in str(phrase).split("/") if part.strip()]
    return tuple(parts) if parts else (str(phrase).strip(),)


def clipped(p: float) -> float:
    return min(1 - 1e-6, max(1e-6, float(p)))


def collect_card_pairs(model: KalshiFightContextModel, card_labels: pd.DataFrame) -> list[tuple[float, int]]:
    """(probability, outcome) for every scorable market on one held-out card."""
    return [(p, y) for p, y, _ in collect_card_rows(model, card_labels)]


def collect_card_rows(
    model: KalshiFightContextModel, card_labels: pd.DataFrame
) -> list[tuple[float, int, str]]:
    """(probability, outcome, phrase group) for one held-out card."""
    rows = []
    for _, label in card_labels.iterrows():
        prediction = model.predict(
            forms_from_phrase(label["phrase"]),
            str(label["fighter_1"]),
            str(label["fighter_2"]),
            str(label["event_date"]),
        )
        if prediction.status != "ok" or prediction.probability is None:
            continue
        y = 1 if str(label["outcome"]).strip().lower() == "yes" else 0
        rows.append((float(prediction.probability), y, group_bias_key(str(label["phrase"]))))
    return rows


def loss_from_pairs(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    losses = [-(y * math.log(clipped(p)) + (1 - y) * math.log(1 - clipped(p))) for p, y in pairs]
    return sum(losses) / len(losses)


def card_log_loss(model: KalshiFightContextModel, card_labels: pd.DataFrame) -> tuple[float | None, int]:
    """Mean log loss of the model's predictions on one held-out card."""
    pairs = collect_card_pairs(model, card_labels)
    return loss_from_pairs(pairs), len(pairs)


def fit_platt(pairs: list[tuple[float, int]]) -> dict | None:
    """Fit logit -> a*z + b on (probability, outcome) pairs from settled cards."""
    if len(pairs) < MIN_CALIBRATION_PAIRS:
        return None
    outcomes = {y for _, y in pairs}
    if len(outcomes) < 2:
        return None
    from sklearn.linear_model import LogisticRegression
    import numpy as np

    z = np.array([[math.log(clipped(p) / (1 - clipped(p)))] for p, _ in pairs])
    y = np.array([y for _, y in pairs])
    calibrator = LogisticRegression(max_iter=1000, C=1_000_000.0, solver="lbfgs")
    calibrator.fit(z, y)
    return {"a": float(calibrator.coef_[0][0]), "b": float(calibrator.intercept_[0])}


def calibrated_pairs(pairs: list[tuple[float, int]], calibration: dict | None) -> list[tuple[float, int]]:
    from ufc_mentions.kalshi_context_model import apply_live_calibration

    if not calibration:
        return pairs
    return [(apply_live_calibration(p, calibration), y) for p, y in pairs]


def as_pairs(rows: list) -> list[tuple[float, int]]:
    """Accept either (p, y) or (p, y, phrase group) rows."""
    return [(row[0], row[1]) for row in rows]


def calibrated_holdout_means(per_holdout_rows: dict[str, list], holdout_order: list[str]) -> float | None:
    """Mean holdout loss when each card is scored with a calibrator fitted
    only on the holdout cards before it. Cards with no earlier fit data are
    scored uncalibrated."""
    losses = []
    for index, holdout in enumerate(holdout_order):
        earlier = as_pairs([row for prior in holdout_order[:index] for row in per_holdout_rows.get(prior, [])])
        calibration = fit_platt(earlier)
        loss = loss_from_pairs(
            calibrated_pairs(as_pairs(per_holdout_rows.get(holdout, [])), calibration)
        )
        if loss is not None:
            losses.append(loss)
    return sum(losses) / len(losses) if losses else None


GROUP_BIAS_SHRINK = 30.0   # a group needs ~30 settled markets to move halfway
GROUP_BIAS_MIN_ROWS = 8
GROUP_BIAS_MAX = 1.2       # logit units, so no group can be flipped wholesale


def fit_group_bias(rows: list[tuple[float, int, str]]) -> dict[str, float]:
    """Per-phrase-group logit shift, fitted on settled cards and shrunk hard.

    Commentary vocabulary is uneven: the physical-action groups have settled
    above our number and the catchphrases below it. Each group gets its own
    shift, pulled toward zero by n/(n + 30) so a thin group barely moves."""
    buckets: dict[str, list[tuple[float, int]]] = {}
    for p, y, key in rows:
        if key:
            buckets.setdefault(key, []).append((p, y))
    bias: dict[str, float] = {}
    for key, values in buckets.items():
        n = len(values)
        if n < GROUP_BIAS_MIN_ROWS:
            continue
        mean_p = sum(clipped(p) for p, _ in values) / n
        mean_y = sum(y for _, y in values) / n
        # Laplace-smoothed outcome rate keeps a 0/1 group from exploding.
        smoothed = (mean_y * n + 0.5) / (n + 1.0)
        delta = math.log(clipped(smoothed) / (1 - clipped(smoothed))) - math.log(mean_p / (1 - mean_p))
        delta *= n / (n + GROUP_BIAS_SHRINK)
        delta = max(-GROUP_BIAS_MAX, min(GROUP_BIAS_MAX, delta))
        if abs(delta) > 1e-4:
            bias[key] = delta
    return bias


def group_adjusted_pairs(
    rows: list[tuple[float, int, str]], bias: dict[str, float] | None
) -> list[tuple[float, int]]:
    if not bias:
        return [(p, y) for p, y, _ in rows]
    return [(apply_group_bias(p, key, bias), y) for p, y, key in rows]


def group_holdout_mean(
    per_holdout_rows: dict[str, list], holdout_order: list[str]
) -> float | None:
    """Each card scored with a bias fitted only on the cards before it."""
    losses = []
    for index, holdout in enumerate(holdout_order):
        earlier = [row for prior in holdout_order[:index] for row in per_holdout_rows.get(prior, [])]
        bias = fit_group_bias(earlier) if earlier else {}
        loss = loss_from_pairs(group_adjusted_pairs(per_holdout_rows.get(holdout, []), bias))
        if loss is not None:
            losses.append(loss)
    return sum(losses) / len(losses) if losses else None


VARIANT_ORDER = ["v1", "v2", "v1+calib", "v2+calib", "v1+group", "v2+group"]


def pick_best_variant(means: dict[str, float | None]) -> str:
    """Lowest mean holdout loss wins; ties go to the simpler variant."""
    scored = [(mean, name) for name, mean in means.items() if mean is not None]
    if not scored:
        return "v1"
    best = min(mean for mean, _ in scored)
    for name in VARIANT_ORDER:
        mean = means.get(name)
        if mean is not None and abs(mean - best) < 1e-9:
            return name
    return "v1"


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
        # A new contender means the old verdict no longer covers the field.
        and report.get("variants_tested") == VARIANT_ORDER
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

    def holdout_pass(weight: float, feature_set: str) -> tuple[dict, dict[str, list]]:
        card_scores = {}
        pairs_by_card: dict[str, list] = {}
        for holdout in holdouts:
            model = KalshiFightContextModel(
                history, corpus,
                upcoming=upcoming, master=master,
                labels=labels, label_weight=weight,
                feature_set=feature_set,
            )
            model.label_cutoff_date = holdout
            card_labels = labels.loc[labels["event_date"].astype(str) == holdout]
            rows = collect_card_rows(model, card_labels)
            pairs = [(prob, y) for prob, y, _ in rows]
            pairs_by_card[holdout] = rows
            loss = loss_from_pairs(pairs)
            card_scores[holdout] = {"log_loss": loss, "scored": len(pairs)}
            print(f"  weight {weight:g} {feature_set} | holdout {holdout}: "
                  f"log loss {loss:.4f} over {len(pairs)} markets" if loss is not None
                  else f"  weight {weight:g} {feature_set} | holdout {holdout}: no scorable predictions")
        losses = [entry["log_loss"] for entry in card_scores.values() if entry["log_loss"] is not None]
        summary = {
            "cards": card_scores,
            "mean_log_loss": sum(losses) / len(losses) if losses else None,
        }
        return summary, pairs_by_card

    per_weight: dict[float, dict] = {}
    pairs_v1_by_weight: dict[float, dict[str, list]] = {}
    for weight in WEIGHTS:
        per_weight[weight], pairs_v1_by_weight[weight] = holdout_pass(weight, "v1")

    means = {weight: per_weight[weight]["mean_log_loss"] for weight in WEIGHTS}
    chosen = pick_best_weight(means)
    baseline = means.get(0.0)
    chosen_mean = means.get(chosen)

    # Variant gate at the chosen weight: v2 features and settled-card
    # calibration only ship if they beat plain v1 on the same held-out cards.
    print(f"\nVariant gate at label weight {chosen:g}:")
    pairs_v1 = pairs_v1_by_weight[chosen]
    v2_summary, pairs_v2 = holdout_pass(chosen, "v2")
    variant_means = {
        "v1": chosen_mean,
        "v2": v2_summary["mean_log_loss"],
        "v1+calib": calibrated_holdout_means(pairs_v1, holdouts),
        "v2+calib": calibrated_holdout_means(pairs_v2, holdouts),
        "v1+group": group_holdout_mean(pairs_v1, holdouts),
        "v2+group": group_holdout_mean(pairs_v2, holdouts),
    }
    best_variant = pick_best_variant(variant_means)
    chosen_feature_set = "v2" if best_variant.startswith("v2") else "v1"
    final_calibration = None
    final_group_bias = None
    winning_rows = pairs_v2 if chosen_feature_set == "v2" else pairs_v1
    if best_variant.endswith("+calib"):
        final_calibration = fit_platt([
            (prob, y) for card_rows in winning_rows.values() for prob, y, _ in card_rows
        ])
        if final_calibration is None:
            best_variant = chosen_feature_set  # not enough data to fit for live use
    elif best_variant.endswith("+group"):
        # Fit the shipped bias on every settled card, the same shape the gate scored.
        final_group_bias = fit_group_bias([
            row for card_rows in winning_rows.values() for row in card_rows
        ]) or None
        if final_group_bias is None:
            best_variant = chosen_feature_set
    for name in VARIANT_ORDER:
        mean = variant_means.get(name)
        marker = " <- chosen" if name == best_variant else ""
        print(f"  {name}: {mean:.4f}{marker}" if mean is not None else f"  {name}: n/a{marker}")

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

    gate_report = {
        "generated_at": report["generated_at"],
        "label_weight": chosen,
        "holdout_cards": holdouts,
        "variant_means": variant_means,
        "chosen_variant": best_variant,
        "variants_tested": VARIANT_ORDER,
        "chosen_feature_set": chosen_feature_set,
        "calibration": final_calibration,
        "group_bias": final_group_bias,
        "note": (
            "v2 adds the event-tier feature; +calib recalibrates globally on "
            "settled-card outcomes; +group shifts each phrase group by its own "
            "settled history, shrunk by sample size. Every holdout card is scored "
            "with a correction fitted only on cards before it, and a variant ships "
            "only when it beat plain v1 here."
        ),
    }
    GATE_REPORT_PATH.write_text(json.dumps(gate_report, indent=2) + "\n")

    UPDATE_CONFIG_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_CONFIG_DEFAULT.write_text(json.dumps({
        "label_weight": chosen,
        "feature_set": chosen_feature_set,
        "calibration": final_calibration if best_variant.endswith("+calib") else None,
        "group_bias": final_group_bias if best_variant.endswith("+group") else None,
        "chosen_variant": best_variant,
        "chosen_at": report["generated_at"],
        "basis": f"walk-forward over {len(holdouts)} held-out cards",
    }, indent=2) + "\n")

    print(f"\nBaseline (transcripts only): {baseline:.4f}" if baseline is not None else "\nBaseline: n/a")
    for weight in WEIGHTS[1:]:
        mean = means[weight]
        print(f"Weight {weight:g}: {mean:.4f}" if mean is not None else f"Weight {weight:g}: n/a")
    print(f"Chosen label weight: {chosen:g}")
    print(f"Chosen variant: {best_variant}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}, {GATE_REPORT_PATH.relative_to(ROOT)}, "
          f"and {UPDATE_CONFIG_DEFAULT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
