"""Entry rules: which priced rows are allowed to become WATCH.

Two rules live here, both set from evidence rather than taste:

Edge cap. On the first settled card, every official trade had a claimed edge
of +16 points or more, and 20 of 22 lost; the small-edge leans below the entry
bar were the only profitable group. A disagreement with the market that large
is usually the model missing something (a broadcast context the market can
see), not free money. So a row only becomes WATCH when its edge is between
the entry bar and EDGE_CAP. Bigger gaps are flagged BIG GAP and never traded
on paper.

Phrase trust. The walk-forward prediction backtest (about 44k old-fight
predictions) grades each phrase group. Groups that fail to beat the simple
base rate, or whose AUC shows almost no ranking skill, are not allowed to
produce WATCH rows at all - they can lean, nothing more. This is set on the
large prediction sample, not tuned on the tiny P/L sample.
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKTEST_GROUPS_CSV = ROOT / "model_outputs" / "kalshi_context_model_backtest.csv"

EDGE_CAP_DEFAULT = 0.15
MIN_TRUST_AUC = 0.55


def normalize_forms(forms) -> frozenset[str]:
    """Key a phrase group by its word forms, however they were written."""
    if isinstance(forms, str):
        for sep in ("|", "/"):
            if sep in forms:
                forms = forms.split(sep)
                break
        else:
            forms = [forms]
    return frozenset(str(f).strip().lower() for f in forms if str(f).strip())


def load_phrase_trust(path: Path | str = BACKTEST_GROUPS_CSV) -> dict[frozenset, dict]:
    """Per-phrase-group grades from the prediction backtest, keyed by forms."""
    path = Path(path)
    if not path.exists():
        return {}
    trust: dict[frozenset, dict] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            key = normalize_forms(row.get("forms") or row.get("phrase") or "")
            if not key:
                continue
            try:
                auc = float(row.get("auc") or 0.0)
            except ValueError:
                auc = 0.0
            beats = str(row.get("status", "")).strip() == "beats_base"
            trust[key] = {
                "auc": auc,
                "beats_base": beats,
                "trusted": beats and auc >= MIN_TRUST_AUC,
            }
    return trust


def phrase_trust(forms, trust_map: dict[frozenset, dict] | None) -> tuple[bool, str]:
    """(trusted, note). Unknown groups are trusted: there is no evidence against them."""
    if not trust_map:
        return True, ""
    entry = trust_map.get(normalize_forms(forms))
    if entry is None:
        return True, "no prediction-backtest record for this phrase group yet"
    if entry["trusted"]:
        return True, ""
    if not entry["beats_base"]:
        return False, "this phrase group failed the old-fight prediction test, so it can lean but never watch"
    return False, (
        f"this phrase group shows almost no ranking skill on old fights "
        f"(AUC {entry['auc']:.2f}), so it can lean but never watch"
    )


def watch_decision(
    *,
    edge: float | None,
    hurdle: float | None,
    side: str,
    model_ready: bool,
    require_model: bool,
    trusted: bool,
    edge_cap: float = EDGE_CAP_DEFAULT,
) -> tuple[bool, str]:
    """(watch, blocker). blocker is '' when watch, else why the row cannot be one."""
    if require_model and not model_ready:
        return False, "no_model"
    if side not in ("yes", "no") or edge is None or hurdle is None:
        return False, "no_prices"
    if edge <= hurdle:
        return False, "below_bar"
    if edge > edge_cap:
        return False, "big_gap"
    if not trusted:
        return False, "low_trust"
    return True, ""
