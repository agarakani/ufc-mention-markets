#!/usr/bin/env python3
"""Shared literal phrase target definitions.

Market phrases live in market_phrases.txt so the project can follow the actual
phrases listed by Polymarket/Kalshi rather than a hard-coded guess.
"""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PHRASES_FILE_DEFAULT = PROJECT_ROOT / "market_phrases.txt"

DEFAULT_PHRASES = [
    "submission",
    "knockout",
    "TKO",
    "KO",
    "knocked out",
    "split decision",
    "unanimous decision",
    "doctor",
]


def slugify_phrase(phrase: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", phrase.strip().lower()).strip("_")
    return slug or "phrase"


def phrase_column(phrase: str) -> str:
    return f"mention_{slugify_phrase(phrase)}"


def load_phrase_targets(path=PHRASES_FILE_DEFAULT) -> list[str]:
    path = Path(path)
    if not path.exists():
        return list(DEFAULT_PHRASES)

    phrases = []
    seen = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            phrase = line.split("#", 1)[0].strip()
            if not phrase:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            phrases.append(phrase)
            seen.add(key)
    return phrases or list(DEFAULT_PHRASES)


def phrase_columns(path=PHRASES_FILE_DEFAULT) -> list[tuple[str, str]]:
    return [(phrase_column(phrase), phrase) for phrase in load_phrase_targets(path)]


def phrase_to_column_map(path=PHRASES_FILE_DEFAULT) -> dict[str, str]:
    return {phrase.lower(): column for column, phrase in phrase_columns(path)}
