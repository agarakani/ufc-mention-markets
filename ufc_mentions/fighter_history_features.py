#!/usr/bin/env python3
"""Leakage-safe fighter mention-history features.

Each fight receives rates calculated from strictly earlier event dates. Rows on
the same card are scored before that card updates the history, so one bout can
never reveal transcript labels to another bout on the same event.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd


FEATURE_PREFIX = "fighter_history_"
PRIOR_STRENGTH = 8.0


def fighter_key(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def target_slug(target: str) -> str:
    return target.removeprefix("mention_")


def feature_names(target: str) -> list[str]:
    slug = target_slug(target)
    return [
        f"{FEATURE_PREFIX}{slug}_mean_rate",
        f"{FEATURE_PREFIX}{slug}_max_rate",
        f"{FEATURE_PREFIX}{slug}_max_fights",
        f"{FEATURE_PREFIX}{slug}_both_seen",
    ]


def _bool_value(value) -> int | None:
    lowered = str(value).strip().lower()
    if lowered == "true" or value is True or value == 1:
        return 1
    if lowered == "false" or value is False or value == 0:
        return 0
    return None


def add_prior_fighter_features(
    history: pd.DataFrame,
    targets: list[str],
    future: pd.DataFrame | None = None,
    prior_strength: float = PRIOR_STRENGTH,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Add target-specific fighter rates to history and optional future rows.

    Historical rows use only earlier event dates. Future rows use all labeled
    history and never update from other future rows.
    """
    hist = history.copy()
    fut = future.copy() if future is not None else None
    for target in targets:
        for name in feature_names(target):
            hist[name] = np.nan
            if fut is not None:
                fut[name] = np.nan

    dates = pd.to_datetime(hist["event_date"], errors="coerce")
    order = sorted(
        hist.index,
        key=lambda idx: (dates.loc[idx] if pd.notna(dates.loc[idx]) else pd.Timestamp.max, str(idx)),
    )
    groups: list[list] = []
    for idx in order:
        date = dates.loc[idx]
        key = date.date().isoformat() if pd.notna(date) else f"missing:{idx}"
        if not groups or groups[-1][0][0] != key:
            groups.append([])
        groups[-1].append((key, idx))

    fighter_stats = {
        target: defaultdict(lambda: [0, 0]) for target in targets
    }
    global_stats = {target: [0, 0] for target in targets}

    def assign(frame: pd.DataFrame, idx, target: str):
        positive, total = global_stats[target]
        global_rate = (positive + 1.0) / (total + 2.0)
        rates = []
        supports = []
        for column in ("fighter_1", "fighter_2"):
            key = fighter_key(frame.at[idx, column])
            fighter_positive, fighter_total = fighter_stats[target][key]
            rate = (
                fighter_positive + prior_strength * global_rate
            ) / (fighter_total + prior_strength)
            rates.append(rate)
            supports.append(fighter_total)
        names = feature_names(target)
        frame.at[idx, names[0]] = float(np.mean(rates))
        frame.at[idx, names[1]] = float(max(rates))
        frame.at[idx, names[2]] = int(max(supports))
        frame.at[idx, names[3]] = int(min(supports) > 0)

    for group in groups:
        indices = [idx for _key, idx in group]
        for idx in indices:
            for target in targets:
                assign(hist, idx, target)

        # Update only after every fight on the event has been scored.
        for idx in indices:
            fighters = {
                fighter_key(hist.at[idx, "fighter_1"]),
                fighter_key(hist.at[idx, "fighter_2"]),
            }
            fighters.discard("")
            for target in targets:
                value = _bool_value(hist.at[idx, target]) if target in hist.columns else None
                if value is None:
                    continue
                global_stats[target][0] += value
                global_stats[target][1] += 1
                for fighter in fighters:
                    fighter_stats[target][fighter][0] += value
                    fighter_stats[target][fighter][1] += 1

    if fut is not None:
        for idx in fut.index:
            for target in targets:
                assign(fut, idx, target)
    return hist, fut
