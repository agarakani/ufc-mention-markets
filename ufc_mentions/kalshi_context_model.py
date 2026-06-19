#!/usr/bin/env python3
"""Fight-level model predictions for exact Kalshi mention phrases."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from .fighter_history_features import add_prior_fighter_features
from .kalshi_mentions import TranscriptCorpus, grouped_matcher, name_tokens, normalized_name
from .mention_counts import last_name
from .predict_upcoming_mentions import normalize_upcoming
from .train_baseline_models import (
    add_date_features,
    bool_series,
    calibrate_from_validation,
    chronological_split,
    feature_columns,
    make_pipeline,
    parse_boolish,
    split_feature_types,
    tune_c,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORY_DEFAULT = ROOT / "data" / "processed" / "joined_fights.csv"
UPCOMING_DEFAULT = ROOT / "kaggle_data" / "ultimate_ufc_dataset" / "upcoming.csv"
MASTER_DEFAULT = ROOT / "kaggle_data" / "ultimate_ufc_dataset" / "ufc-master.csv"
TARGET = "mention_kalshi_dynamic"

ODDS_FIELDS = {
    "R_odds", "B_odds", "R_ev", "B_ev",
    "r_dec_odds", "b_dec_odds", "r_sub_odds", "b_sub_odds",
    "r_ko_odds", "b_ko_odds",
}

DIFF_SOURCES = {
    "lose_streak_dif": ("B_current_lose_streak", "R_current_lose_streak"),
    "win_streak_dif": ("B_current_win_streak", "R_current_win_streak"),
    "longest_win_streak_dif": ("B_longest_win_streak", "R_longest_win_streak"),
    "win_dif": ("B_wins", "R_wins"),
    "loss_dif": ("B_losses", "R_losses"),
    "total_round_dif": ("B_total_rounds_fought", "R_total_rounds_fought"),
    "total_title_bout_dif": ("B_total_title_bouts", "R_total_title_bouts"),
    "ko_dif": ("B_win_by_KO/TKO", "R_win_by_KO/TKO"),
    "sub_dif": ("B_win_by_Submission", "R_win_by_Submission"),
    "height_dif": ("B_Height_cms", "R_Height_cms"),
    "reach_dif": ("B_Reach_cms", "R_Reach_cms"),
    "age_dif": ("B_age", "R_age"),
    "sig_str_dif": ("B_avg_SIG_STR_landed", "R_avg_SIG_STR_landed"),
    "avg_sub_att_dif": ("B_avg_SUB_ATT", "R_avg_SUB_ATT"),
    "avg_td_dif": ("B_avg_TD_landed", "R_avg_TD_landed"),
}


@dataclass(frozen=True)
class ContextPrediction:
    probability: float | None
    status: str
    note: str
    profile: str
    training_rows: int = 0
    validation_rows: int = 0
    positive_rate: float | None = None
    validation_log_loss: float | None = None
    base_log_loss: float | None = None
    log_loss_improvement: float | None = None
    best_c: str | float = ""
    calibrated: bool = False
    row_source: str = ""


@dataclass
class _TargetModel:
    forms: tuple[str, ...]
    history: pd.DataFrame
    prepared_history: pd.DataFrame
    columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    pipeline: object | None
    y_validation: pd.Series | None
    validation_probability: np.ndarray | None
    prediction: ContextPrediction


def _forms_key(forms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", form.strip().casefold()) for form in forms)


def _clip_probability(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _name_match(query: str, candidate: str) -> bool:
    query_key = normalized_name(query)
    candidate_key = normalized_name(candidate)
    if not query_key or not candidate_key:
        return False
    if query_key == candidate_key:
        return True
    query_tokens = set(name_tokens(query))
    candidate_tokens = set(name_tokens(candidate))
    if len(query_tokens) >= 2 and len(candidate_tokens) >= 2:
        if query_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(query_tokens):
            return True
        ordered_query = tuple(name_tokens(query))
        ordered_candidate = tuple(name_tokens(candidate))
        return ordered_query[0] == ordered_candidate[0] and ordered_query[-1] == ordered_candidate[-1]
    return False


def _pair_match(row: pd.Series, fighter_1: str, fighter_2: str) -> bool:
    left = str(row.get("R_fighter", ""))
    right = str(row.get("B_fighter", ""))
    return (
        (_name_match(fighter_1, left) and _name_match(fighter_2, right))
        or (_name_match(fighter_1, right) and _name_match(fighter_2, left))
    )


def _number(value) -> float | None:
    try:
        if value in ("", None) or pd.isna(value):
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _prepare_with_types(
    frame: pd.DataFrame,
    columns: list[str],
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> pd.DataFrame:
    prepared = frame.copy()
    for column in columns:
        if column not in prepared.columns:
            prepared[column] = np.nan
    out = prepared[columns].copy()
    for column in numeric_columns:
        out[column] = pd.to_numeric(parse_boolish(out[column]).replace("", np.nan), errors="coerce")
    for column in categorical_columns:
        out[column] = out[column].fillna("").astype(str)
    return out


class KalshiFightContextModel:
    """Train exact phrase models and predict one listed fight at a time."""

    def __init__(
        self,
        history: pd.DataFrame,
        corpus: TranscriptCorpus,
        *,
        upcoming: pd.DataFrame | None = None,
        master: pd.DataFrame | None = None,
        profile: str = "stats_only_history",
        min_training_rows: int = 500,
    ):
        self.history = add_date_features(history.copy()).reset_index(drop=True)
        self.history.index = [f"h_{index}" for index in range(len(self.history))]
        self.corpus = corpus
        self.text_by_id = {fight.transcript_id: fight.text for fight in corpus.fights}
        self.upcoming = upcoming.copy() if upcoming is not None else pd.DataFrame()
        self.master = master.copy() if master is not None else pd.DataFrame()
        self.profile = profile
        self.min_training_rows = min_training_rows
        self._target_cache: dict[tuple[str, ...], _TargetModel] = {}
        self._prediction_cache: dict[tuple[tuple[str, ...], str, str, str], ContextPrediction] = {}

    @classmethod
    def load(
        cls,
        corpus: TranscriptCorpus,
        *,
        history_path: str | Path = HISTORY_DEFAULT,
        upcoming_path: str | Path = UPCOMING_DEFAULT,
        master_path: str | Path = MASTER_DEFAULT,
        profile: str = "stats_only_history",
        min_training_rows: int = 500,
    ) -> "KalshiFightContextModel":
        history = pd.read_csv(Path(history_path))
        upcoming_path = Path(upcoming_path)
        master_path = Path(master_path)
        upcoming = pd.read_csv(upcoming_path) if upcoming_path.exists() else pd.DataFrame()
        master = pd.read_csv(master_path) if master_path.exists() else pd.DataFrame()
        return cls(
            history,
            corpus,
            upcoming=upcoming,
            master=master,
            profile=profile,
            min_training_rows=min_training_rows,
        )

    def predict(
        self,
        forms: tuple[str, ...],
        fighter_1: str,
        fighter_2: str,
        event_date: str | None,
    ) -> ContextPrediction:
        key = (_forms_key(forms), normalized_name(fighter_1), normalized_name(fighter_2), event_date or "")
        if key in self._prediction_cache:
            return self._prediction_cache[key]

        target_model = self._fit_target(forms)
        if target_model.prediction.status != "ok":
            self._prediction_cache[key] = target_model.prediction
            return target_model.prediction

        future, row_source, row_note = self._future_frame(fighter_1, fighter_2, event_date)
        try:
            _, future_featured = add_prior_fighter_features(target_model.history, [TARGET], future)
            x_future = _prepare_with_types(
                future_featured,
                target_model.columns,
                target_model.numeric_columns,
                target_model.categorical_columns,
            )
            raw = target_model.pipeline.predict_proba(x_future)[:, 1]
            calibrated, used_calibration = calibrate_from_validation(
                target_model.y_validation,
                target_model.validation_probability,
                raw,
            )
            probability = _clip_probability(float(calibrated[0]))
        except Exception as exc:
            prediction = ContextPrediction(
                probability=None,
                status="error",
                note=f"fight model failed for this matchup: {exc}",
                profile=self.profile,
                row_source=row_source,
            )
            self._prediction_cache[key] = prediction
            return prediction

        base = target_model.prediction
        prediction = ContextPrediction(
            probability=probability,
            status="ok",
            note=(
                f"fight model for this exact phrase group; {row_note}; "
                f"checked on {base.validation_rows} recent fights"
            ),
            profile=self.profile,
            training_rows=base.training_rows,
            validation_rows=base.validation_rows,
            positive_rate=base.positive_rate,
            validation_log_loss=base.validation_log_loss,
            base_log_loss=base.base_log_loss,
            log_loss_improvement=base.log_loss_improvement,
            best_c=base.best_c,
            calibrated=bool(used_calibration),
            row_source=row_source,
        )
        self._prediction_cache[key] = prediction
        return prediction

    def _fit_target(self, forms: tuple[str, ...]) -> _TargetModel:
        key = _forms_key(forms)
        if key in self._target_cache:
            return self._target_cache[key]

        matcher = grouped_matcher(forms)
        history = self.history.loc[self.history["transcript_id"].astype(str).isin(self.text_by_id)].copy()
        history[TARGET] = history["transcript_id"].map(lambda value: bool(matcher(self.text_by_id[str(value)])))
        positive_rate = float(bool_series(history[TARGET]).astype(int).mean()) if len(history) else None

        empty = _TargetModel(
            forms=forms,
            history=history,
            prepared_history=pd.DataFrame(),
            columns=[],
            numeric_columns=[],
            categorical_columns=[],
            pipeline=None,
            y_validation=None,
            validation_probability=None,
            prediction=ContextPrediction(
                probability=None,
                status="insufficient_training_rows",
                note="not enough old fights with both context data and transcripts",
                profile=self.profile,
                positive_rate=positive_rate,
            ),
        )
        if len(history) < self.min_training_rows:
            self._target_cache[key] = empty
            return empty

        try:
            history_featured, _ = add_prior_fighter_features(history, [TARGET])
            fit, validation, _first_validation_date = chronological_split(history_featured, test_frac=0.20)
            y_fit = bool_series(fit[TARGET]).astype(int)
            y_validation = bool_series(validation[TARGET]).astype(int)
            if len(set(y_fit)) < 2:
                prediction = ContextPrediction(
                    probability=None,
                    status="one_sided_history",
                    note="old fights are all the same answer for this phrase",
                    profile=self.profile,
                    training_rows=len(fit),
                    validation_rows=len(validation),
                    positive_rate=positive_rate,
                )
                result = empty
                result.prediction = prediction
                self._target_cache[key] = result
                return result

            columns = feature_columns(
                history_featured,
                profile=self.profile,
                include_identity=False,
                target=TARGET,
            )
            numeric_columns, categorical_columns, prepared = split_feature_types(history_featured, columns)
            best_c, _validation_loss = tune_c(
                prepared.loc[fit.index],
                y_fit,
                prepared.loc[validation.index],
                y_validation,
                numeric_columns,
                categorical_columns,
            )
            pipeline = make_pipeline(numeric_columns, categorical_columns, best_c)
            pipeline.fit(prepared.loc[fit.index], y_fit)
            validation_probability = pipeline.predict_proba(prepared.loc[validation.index])[:, 1]
            model_loss = log_loss(y_validation, validation_probability, labels=[0, 1])
            base_probability = np.repeat(float(y_fit.mean()), len(y_validation))
            base_loss = log_loss(y_validation, base_probability, labels=[0, 1])
            prediction = ContextPrediction(
                probability=None,
                status="ok",
                note="fight model trained",
                profile=self.profile,
                training_rows=len(fit),
                validation_rows=len(validation),
                positive_rate=positive_rate,
                validation_log_loss=float(model_loss),
                base_log_loss=float(base_loss),
                log_loss_improvement=float(base_loss - model_loss),
                best_c=best_c,
            )
            result = _TargetModel(
                forms=forms,
                history=history,
                prepared_history=prepared,
                columns=columns,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
                pipeline=pipeline,
                y_validation=y_validation,
                validation_probability=validation_probability,
                prediction=prediction,
            )
        except Exception as exc:
            result = empty
            result.prediction = ContextPrediction(
                probability=None,
                status="error",
                note=f"fight model could not train for this phrase: {exc}",
                profile=self.profile,
                positive_rate=positive_rate,
            )

        self._target_cache[key] = result
        return result

    def _future_frame(self, fighter_1: str, fighter_2: str, event_date: str | None) -> tuple[pd.DataFrame, str, str]:
        upcoming = self._future_from_upcoming(fighter_1, fighter_2, event_date)
        if upcoming is not None:
            return upcoming, "upcoming_csv", "using the upcoming-fight stats file"

        from_master = self._future_from_master(fighter_1, fighter_2, event_date)
        if from_master is not None:
            return from_master, "latest_known_fighter_stats", "using latest known fighter stat rows"

        minimal = self._minimal_future_frame(fighter_1, fighter_2, event_date)
        return minimal, "names_only", "using fighter names and their phrase history only"

    def _future_from_upcoming(self, fighter_1: str, fighter_2: str, event_date: str | None) -> pd.DataFrame | None:
        if self.upcoming.empty or not event_date or "date" not in self.upcoming.columns:
            return None
        dated = self.upcoming.loc[self.upcoming["date"].astype(str) == event_date]
        for _, row in dated.iterrows():
            if _pair_match(row, fighter_1, fighter_2):
                frame = normalize_upcoming(pd.DataFrame([row.to_dict()])).reset_index(drop=True)
                frame.index = ["future"]
                return self._finish_future_frame(frame, fighter_1, fighter_2, event_date)
        return None

    def _future_from_master(self, fighter_1: str, fighter_2: str, event_date: str | None) -> pd.DataFrame | None:
        if self.master.empty or "date" not in self.master.columns:
            return None
        left = self._latest_snapshot(fighter_1, event_date)
        right = self._latest_snapshot(fighter_2, event_date)
        if left is None and right is None:
            return None

        raw = {column: "" for column in self.master.columns}
        raw.update({
            "R_fighter": fighter_1,
            "B_fighter": fighter_2,
            "date": event_date or "",
            "Winner": "",
            "title_bout": "",
            "no_of_rounds": "",
        })
        if left is not None:
            self._copy_side(raw, left[0], left[1], "R")
        if right is not None:
            self._copy_side(raw, right[0], right[1], "B")
        raw["weight_class"] = raw.get("weight_class") or self._pick_weight_class(left, right)
        raw["gender"] = raw.get("gender") or self._pick_shared("gender", left, right)
        for field in ODDS_FIELDS:
            if field in raw:
                raw[field] = ""
        self._fill_differences(raw)

        base = {
            "transcript_id": self._future_id(fighter_1, fighter_2, event_date),
            "fighter_1": fighter_1,
            "fighter_2": fighter_2,
            "fighter_1_last": last_name(fighter_1),
            "fighter_2_last": last_name(fighter_2),
            "event_date": event_date or "",
            "weight_class": raw.get("weight_class", ""),
            "event_title": f"{fighter_1} vs {fighter_2}",
            "duration_s": "",
        }
        base.update({f"kaggle_{column}": value for column, value in raw.items()})
        frame = pd.DataFrame([base])
        frame.index = ["future"]
        return self._finish_future_frame(frame, fighter_1, fighter_2, event_date)

    def _minimal_future_frame(self, fighter_1: str, fighter_2: str, event_date: str | None) -> pd.DataFrame:
        frame = pd.DataFrame([{
            "transcript_id": self._future_id(fighter_1, fighter_2, event_date),
            "fighter_1": fighter_1,
            "fighter_2": fighter_2,
            "fighter_1_last": last_name(fighter_1),
            "fighter_2_last": last_name(fighter_2),
            "event_date": event_date or "",
            "weight_class": "",
            "event_title": f"{fighter_1} vs {fighter_2}",
            "duration_s": "",
        }])
        frame.index = ["future"]
        return self._finish_future_frame(frame, fighter_1, fighter_2, event_date)

    def _finish_future_frame(
        self,
        frame: pd.DataFrame,
        fighter_1: str,
        fighter_2: str,
        event_date: str | None,
    ) -> pd.DataFrame:
        frame = frame.copy()
        frame["fighter_1"] = fighter_1
        frame["fighter_2"] = fighter_2
        frame["fighter_1_last"] = last_name(fighter_1)
        frame["fighter_2_last"] = last_name(fighter_2)
        frame["event_date"] = event_date or ""
        frame["transcript_id"] = frame.get("transcript_id", self._future_id(fighter_1, fighter_2, event_date))
        for column in self.history.columns:
            if column not in frame.columns and not column.startswith("mention_"):
                frame[column] = ""
        return add_date_features(frame)

    def _latest_snapshot(self, fighter: str, event_date: str | None) -> tuple[pd.Series, str] | None:
        dates = pd.to_datetime(self.master["date"], errors="coerce")
        cutoff = pd.to_datetime(event_date, errors="coerce") if event_date else None
        candidates = []
        for index, row in self.master.iterrows():
            row_date = dates.loc[index]
            if pd.isna(row_date):
                continue
            if cutoff is not None and not pd.isna(cutoff) and row_date >= cutoff:
                continue
            if _name_match(fighter, str(row.get("R_fighter", ""))):
                candidates.append((row_date, row, "R"))
            if _name_match(fighter, str(row.get("B_fighter", ""))):
                candidates.append((row_date, row, "B"))
        if not candidates:
            return None
        _row_date, row, side = max(candidates, key=lambda item: item[0])
        return row, side

    def _copy_side(self, raw: dict, source_row: pd.Series, source_side: str, target_side: str) -> None:
        source_prefix = f"{source_side}_"
        target_prefix = f"{target_side}_"
        for column, value in source_row.items():
            if not str(column).startswith(source_prefix):
                continue
            suffix = str(column)[2:]
            target = f"{target_prefix}{suffix}"
            if target in raw and target not in ODDS_FIELDS:
                raw[target] = value

    def _fill_differences(self, raw: dict) -> None:
        for target, (left, right) in DIFF_SOURCES.items():
            if target not in raw:
                continue
            left_value = _number(raw.get(left))
            right_value = _number(raw.get(right))
            if left_value is not None and right_value is not None:
                raw[target] = left_value - right_value

    def _pick_weight_class(self, left, right) -> str:
        return self._pick_shared("weight_class", left, right)

    def _pick_shared(self, field: str, left, right) -> str:
        for item in (left, right):
            if item is not None:
                value = str(item[0].get(field, "") or "")
                if value:
                    return value
        return ""

    def _future_id(self, fighter_1: str, fighter_2: str, event_date: str | None) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", f"{event_date}_{fighter_1}_vs_{fighter_2}".lower()).strip("_")
        return f"kalshi_live_{slug}"
