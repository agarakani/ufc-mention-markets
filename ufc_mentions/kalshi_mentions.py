#!/usr/bin/env python3
"""Rule-aligned grouped mention matching and conservative fight estimates."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from math import sqrt
from pathlib import Path

from .mention_counts import iter_records, norm, strict_pattern


GENERIC_FORMS = {
    "blood", "bloody", "championship", "choke", "choked", "chokehold",
    "decision", "judged", "knock out", "knocked out", "knockout", "legal",
    "illegal", "lights out", "slip", "slipped", "slips", "tired", "tiring",
    "train", "trained", "training", "triangle", "what a fight", "dana",
}


class RuleParseError(ValueError):
    pass


def normalized_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def name_tokens(value: str) -> tuple[str, ...]:
    text = re.sub(r"\([^)]*\)", " ", str(value or ""))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    particles = {"da", "de", "del", "do", "dos", "van", "von"}
    return tuple(token for token in re.findall(r"[a-z0-9]+", text) if token not in particles)


def phrase_forms_from_rules(market: dict) -> tuple[str, ...]:
    label = str((market.get("custom_strike") or {}).get("Word") or market.get("yes_sub_title") or "").strip()
    if label.lower() == "event does not qualify":
        raise RuleParseError("Event qualification is not a phrase-mention market.")
    rules = str(market.get("rules_primary") or "")
    match = re.search(r"\bsays\s+(.+?)\s+as part of\b", rules, re.IGNORECASE)
    if not match:
        raise RuleParseError(f"Could not extract phrase forms from rules_primary for {market.get('ticker', '')}.")
    rule_label = match.group(1).strip().strip('"“”')
    forms = tuple(part.strip().strip('"“”') for part in re.split(r"\s*/\s*", rule_label) if part.strip())
    if not forms:
        raise RuleParseError(f"No phrase forms found in rules for {market.get('ticker', '')}.")
    if label:
        label_forms = tuple(part.strip().casefold() for part in re.split(r"\s*/\s*", label) if part.strip())
        if tuple(form.casefold() for form in forms) != label_forms:
            raise RuleParseError(
                f"Rule forms disagree with custom strike for {market.get('ticker', '')}: {forms!r} vs {label!r}"
            )
    return forms


def grouped_matcher(forms: tuple[str, ...]):
    patterns = tuple(strict_pattern(form) for form in forms)
    return lambda text: any(pattern.search(norm(text)) for pattern in patterns)


@dataclass(frozen=True)
class TranscriptFight:
    transcript_id: str
    event_date: str
    fighter_1: str
    fighter_2: str
    nickname_1: str
    nickname_2: str
    text: str


@dataclass(frozen=True)
class MentionEstimate:
    probability: float
    conservative_probability: float | None
    conservative_probability_source: str
    league_rate: float
    league_hits: int
    league_fights: int
    fighter_rate: float | None
    fighter_hits: int
    fighter_fights: int
    word_type: str
    prior_strength: float | None
    confidence_ok: bool
    confidence_note: str
    missing_fighters: tuple[str, ...]
    history_probability: float | None = None
    probability_source: str = "simple_history"
    context_probability: float | None = None
    context_status: str = ""
    context_note: str = ""
    context_profile: str = ""
    context_training_rows: int = 0
    context_validation_rows: int = 0
    context_positive_rate: float | None = None
    context_validation_log_loss: float | None = None
    context_base_log_loss: float | None = None
    context_log_loss_improvement: float | None = None
    context_best_c: str | float = ""
    context_calibrated: bool = False
    context_row_source: str = ""


class TranscriptCorpus:
    def __init__(self, fights: list[TranscriptFight]):
        self.fights = fights
        self.by_fighter: dict[str, set[int]] = {}
        self.display_names: dict[str, str] = {}
        for index, fight in enumerate(fights):
            for name in (fight.fighter_1, fight.fighter_2):
                key = normalized_name(name)
                if not key:
                    continue
                self.by_fighter.setdefault(key, set()).add(index)
                self.display_names.setdefault(key, name)
        self._cache = {}

    @classmethod
    def load(cls, data_dir: str | Path) -> "TranscriptCorpus":
        fights = []
        for _filename, record in iter_records(str(Path(data_dir).expanduser())):
            if "__error__" in record or float(record.get("duration_s") or 0.0) == 0.0:
                continue
            fights.append(TranscriptFight(
                transcript_id=str(record.get("transcript_id") or _filename),
                event_date=str(record.get("event_date") or ""),
                fighter_1=str(record.get("fighter_1") or ""),
                fighter_2=str(record.get("fighter_2") or ""),
                nickname_1=str(record.get("fighter_1_nickname") or ""),
                nickname_2=str(record.get("fighter_2_nickname") or ""),
                text=norm(record.get("plain_text")),
            ))
        return cls(fights)

    def _match_fighter_key(self, name: str) -> str | None:
        exact = normalized_name(name)
        if exact in self.by_fighter:
            return exact
        query_tokens = name_tokens(name)
        expanded = []
        if len(query_tokens) >= 2:
            query_set = set(query_tokens)
            for key, display_name in self.display_names.items():
                candidate_tokens = name_tokens(display_name)
                candidate_set = set(candidate_tokens)
                if (
                    len(candidate_tokens) >= 2
                    and candidate_tokens[0] == query_tokens[0]
                    and candidate_set.issubset(query_set)
                ):
                    expanded.append(key)
        if len(expanded) == 1:
            return expanded[0]
        surname = normalized_name(str(name).split()[-1])
        candidates = [key for key in self.by_fighter if key.endswith(surname)]
        if len(candidates) == 1:
            return candidates[0]
        if expanded or candidates:
            raise ValueError(f"Could not uniquely match fighter {name!r} in transcript corpus.")
        return None

    def resolve_fighter(self, name: str) -> str:
        matched = self._match_fighter_key(name)
        if matched is not None:
            return matched
        raise ValueError(f"Could not uniquely match fighter {name!r} in transcript corpus.")

    def estimate(
        self,
        forms: tuple[str, ...],
        fighter_1: str,
        fighter_2: str,
        *,
        cutoff_date: str | None = None,
        min_fighter_fights: int = 15,
        fighter_specific_k: float = 4.0,
        contextual_k: float = 25.0,
    ) -> MentionEstimate:
        cache_key = (
            tuple(form.casefold() for form in forms), fighter_1, fighter_2,
            cutoff_date, min_fighter_fights,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        keys = []
        missing_fighters = []
        for fighter in (fighter_1, fighter_2):
            try:
                matched = self._match_fighter_key(fighter)
            except ValueError:
                matched = None
            if matched is None:
                missing_fighters.append(fighter)
            else:
                keys.append(matched)
        eligible = set(range(len(self.fights)))
        if cutoff_date:
            cutoff = datetime.strptime(cutoff_date, "%Y-%m-%d").date()
            eligible = {
                index for index, fight in enumerate(self.fights)
                if (_parsed_date(fight.event_date) is not None and _parsed_date(fight.event_date) < cutoff)
            }
        relevant_set = set()
        for key in keys:
            relevant_set.update(self.by_fighter[key])
        relevant = sorted(relevant_set & eligible)
        matches = grouped_matcher(forms)
        all_hits = {index: bool(matches(self.fights[index].text)) for index in eligible}
        league_hits = sum(all_hits.values())
        league_fights = len(eligible)
        league_rate = league_hits / league_fights if league_fights else 0.0
        fighter_hits = sum(all_hits[index] for index in relevant)
        fighter_n = len(relevant)
        fighter_rate = fighter_hits / fighter_n if fighter_n else None

        normalized_forms = {re.sub(r"\s+", " ", form.casefold()).strip() for form in forms}
        entity_terms = set()
        for index in relevant:
            fight = self.fights[index]
            for value in (
                fight.fighter_1, fight.fighter_2, fight.nickname_1, fight.nickname_2,
            ):
                value = str(value or "").strip().casefold()
                if value:
                    entity_terms.add(value)
                    entity_terms.update(token for token in re.findall(r"[a-z0-9']+", value) if len(token) >= 3)

        if league_rate >= 0.30 or normalized_forms & GENERIC_FORMS:
            word_type = "generic"
            probability = league_rate
            prior_strength = None
        elif normalized_forms & entity_terms:
            word_type = "fighter_specific"
            prior_strength = fighter_specific_k
            probability = (fighter_hits + prior_strength * league_rate) / (fighter_n + prior_strength)
        else:
            word_type = "contextual"
            prior_strength = contextual_k
            probability = (fighter_hits + prior_strength * league_rate) / (fighter_n + prior_strength)

        if word_type == "generic":
            conservative_probability = wilson_lower_bound(league_hits, league_fights)
            conservative_probability_source = f"league Wilson 95% ({league_hits}/{league_fights})"
        elif fighter_n:
            conservative_probability = wilson_lower_bound(fighter_hits, fighter_n)
            conservative_probability_source = f"fighter Wilson 95% ({fighter_hits}/{fighter_n})"
        else:
            conservative_probability = wilson_lower_bound(league_hits, league_fights)
            conservative_probability_source = f"league fallback Wilson 95% ({league_hits}/{league_fights})"

        sample_ok = fighter_n >= min_fighter_fights
        confidence_ok = sample_ok and not missing_fighters
        sample_note = (
            f"{fighter_n} combined fighter-fights"
            if sample_ok
            else f"{fighter_n} combined fighter-fights (<{min_fighter_fights})"
        )
        if missing_fighters:
            missing = ", ".join(str(name) for name in missing_fighters if str(name).strip())
            confidence_note = f"low: missing transcript history for {missing}; {sample_note}"
        else:
            confidence_note = f"ok: {sample_note}" if confidence_ok else f"low: {sample_note}"
        result = MentionEstimate(
            probability=probability,
            conservative_probability=conservative_probability,
            conservative_probability_source=conservative_probability_source,
            league_rate=league_rate,
            league_hits=league_hits,
            league_fights=league_fights,
            fighter_rate=fighter_rate,
            fighter_hits=fighter_hits,
            fighter_fights=fighter_n,
            word_type=word_type,
            prior_strength=prior_strength,
            confidence_ok=confidence_ok,
            confidence_note=confidence_note,
            missing_fighters=tuple(missing_fighters),
            history_probability=probability,
        )
        self._cache[cache_key] = result
        return result


def wilson_lower_bound(successes: int, trials: int, z: float = 1.959963984540054) -> float | None:
    if trials <= 0:
        return None
    rate = successes / trials
    denominator = 1.0 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denominator
    margin = z * sqrt((rate * (1 - rate) + z * z / (4 * trials)) / trials) / denominator
    return max(0.0, center - margin)


def _parsed_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def event_date_from_ticker(ticker: str) -> str | None:
    match = re.search(r"-(\d{2}[A-Z]{3}\d{2})", ticker or "", re.IGNORECASE)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1).upper(), "%y%b%d").date().isoformat()
    except ValueError:
        return None


def fighters_from_market_title(title: str) -> tuple[str, str]:
    match = re.search(r"during\s+(.+?)\s+vs\.?\s+(.+?)\s+(?:UFC\s+)?Fight\b", title or "", re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not parse fighters from Kalshi title: {title!r}")
    return match.group(1).strip(), match.group(2).strip()
