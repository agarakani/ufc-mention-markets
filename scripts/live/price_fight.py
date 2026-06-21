#!/usr/bin/env python3
"""Read-only live pricer for Kalshi UFC announcer-mention markets."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.kalshi_client import KalshiClient, KalshiError, TopOfBook
from ufc_mentions.kalshi_context_model import KalshiFightContextModel
from ufc_mentions.kalshi_mentions import (
    MentionEstimate,
    RuleParseError,
    TranscriptCorpus,
    event_date_from_ticker,
    fighters_from_market_title,
    phrase_forms_from_rules,
)


DATA_DEFAULT = ROOT / "ufc_cleaned_export"


@dataclass(frozen=True)
class PricedMarket:
    ticker: str
    label: str
    forms: tuple[str, ...]
    rules: str
    book: TopOfBook
    estimate: MentionEstimate
    edge: float | None
    hurdle: float | None
    watch: bool
    validation_status: str
    note: str


def apply_context_prediction(
    estimate: MentionEstimate,
    prediction,
) -> MentionEstimate:
    if prediction is None:
        return estimate
    if prediction.status != "ok" or prediction.probability is None:
        return replace(
            estimate,
            probability_source="simple_history_fallback",
            context_status=prediction.status,
            context_note=prediction.note,
            context_profile=prediction.profile,
            context_training_rows=prediction.training_rows,
            context_validation_rows=prediction.validation_rows,
            context_positive_rate=prediction.positive_rate,
            context_validation_log_loss=prediction.validation_log_loss,
            context_base_log_loss=prediction.base_log_loss,
            context_log_loss_improvement=prediction.log_loss_improvement,
            context_best_c=prediction.best_c,
            context_calibrated=prediction.calibrated,
            context_row_source=prediction.row_source,
        )

    return replace(
        estimate,
        probability=prediction.probability,
        probability_source="fight_context_model",
        context_probability=prediction.probability,
        context_status=prediction.status,
        context_note=prediction.note,
        context_profile=prediction.profile,
        context_training_rows=prediction.training_rows,
        context_validation_rows=prediction.validation_rows,
        context_positive_rate=prediction.positive_rate,
        context_validation_log_loss=prediction.validation_log_loss,
        context_base_log_loss=prediction.base_log_loss,
        context_log_loss_improvement=prediction.log_loss_improvement,
        context_best_c=prediction.best_c,
        context_calibrated=prediction.calibrated,
        context_row_source=prediction.row_source,
    )


def price_market(
    market: dict,
    book: TopOfBook,
    corpus: TranscriptCorpus,
    fighter_1: str,
    fighter_2: str,
    *,
    cutoff_date: str | None,
    fee_buffer: float,
    min_fighter_fights: int,
    context_model: Any | None = None,
    require_context_model: bool = False,
) -> PricedMarket | None:
    try:
        forms = phrase_forms_from_rules(market)
    except RuleParseError as exc:
        if "qualification" in str(exc).lower():
            return None
        raise
    estimate = corpus.estimate(
        forms,
        fighter_1,
        fighter_2,
        cutoff_date=cutoff_date,
        min_fighter_fights=min_fighter_fights,
    )
    if context_model is not None:
        estimate = apply_context_prediction(
            estimate,
            context_model.predict(forms, fighter_1, fighter_2, cutoff_date),
        )
    edge = None if book.yes_ask is None else estimate.probability - book.yes_ask
    hurdle = None if book.spread is None else book.spread + fee_buffer
    fight_model_ready = estimate.probability_source == "fight_context_model"
    watch = bool(
        estimate.confidence_ok
        and (fight_model_ready or not require_context_model)
        and edge is not None
        and hurdle is not None
        and edge > hurdle
    )
    if book.yes_ask is None or book.no_ask is None:
        note = "missing executable two-sided order book"
    elif require_context_model and not fight_model_ready:
        note = f"fight-specific model unavailable; {estimate.context_note or estimate.context_status or 'simple history only'}"
    elif not estimate.confidence_ok:
        note = estimate.confidence_note
    elif edge is not None and hurdle is not None and edge <= hurdle:
        note = "model edge does not clear spread + fee buffer"
    else:
        note = "unvalidated watch; exact grouped-rule audit required before any trade claim"
    return PricedMarket(
        ticker=market.get("ticker", ""),
        label=" / ".join(forms),
        forms=forms,
        rules=market.get("rules_primary", ""),
        book=book,
        estimate=estimate,
        edge=edge,
        hurdle=hurdle,
        watch=watch,
        validation_status="unvalidated",
        note=note,
    )


def analyze_event(
    client: KalshiClient,
    corpus: TranscriptCorpus,
    event_ticker: str,
    fighter_1: str | None = None,
    fighter_2: str | None = None,
    *,
    context_model: Any | None = None,
    require_context_model: bool = False,
    fee_buffer: float = 0.02,
    min_fighter_fights: int = 15,
) -> tuple[str, str, list[PricedMarket]]:
    markets = client.get_markets(event_ticker=event_ticker)
    if not markets:
        raise KalshiError(f"No markets found for {event_ticker}.")
    if not fighter_1 or not fighter_2:
        fighter_1, fighter_2 = fighters_from_market_title(markets[0].get("title", ""))
    cutoff_date = event_date_from_ticker(event_ticker)
    rows = []
    for market in markets:
        book = client.get_orderbook(market["ticker"])
        priced = price_market(
            market,
            book,
            corpus,
            fighter_1,
            fighter_2,
            cutoff_date=cutoff_date,
            fee_buffer=fee_buffer,
            min_fighter_fights=min_fighter_fights,
            context_model=context_model,
            require_context_model=require_context_model,
        )
        if priced is not None:
            rows.append(priced)
    rows.sort(
        key=lambda row: (
            row.watch,
            row.edge if row.edge is not None else -999,
        ),
        reverse=True,
    )
    return fighter_1, fighter_2, rows


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "--"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value * 100:.1f}%"


def print_rows(rows: list[PricedMarket], *, show_all: bool) -> None:
    shown = rows if show_all else [row for row in rows if row.watch]
    if not shown:
        print("No markets clear the model edge gate with adequate sample confidence.")
        return
    print(
        f"{'phrase group':<39} {'model':>7} {'YES ask':>8} {'spread':>7} "
        f"{'edge':>7} {'need':>7}  status"
    )
    print("-" * 128)
    for row in shown:
        print(
            f"{row.label[:39]:<39} {_pct(row.estimate.probability):>7} "
            f"{_pct(row.book.yes_ask):>8} "
            f"{_pct(row.book.spread):>7} {_pct(row.edge, signed=True):>7} "
            f"{_pct(row.hurdle):>7}  "
            f"{'WATCH' if row.watch else 'no watch'}; {row.validation_status}"
        )
        if show_all:
            prior = "league only" if row.estimate.prior_strength is None else f"k={row.estimate.prior_strength:g}"
            print(
                f"  type={row.estimate.word_type}; league={_pct(row.estimate.league_rate)} "
                f"({row.estimate.league_hits}/{row.estimate.league_fights}); "
                f"fighters={row.estimate.fighter_hits}/{row.estimate.fighter_fights}; "
                f"source={row.estimate.probability_source}; "
                f"{prior}; {row.note}"
            )
            if row.estimate.context_note:
                check = (
                    "--"
                    if row.estimate.context_log_loss_improvement is None
                    else f"{row.estimate.context_log_loss_improvement:+.4f}"
                )
                print(
                    f"  fight-model={row.estimate.context_status}; "
                    f"profile={row.estimate.context_profile}; "
                    f"recent-check={check}; "
                    f"{row.estimate.context_note}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Price live Kalshi UFC mention markets without placing trades.")
    parser.add_argument("--event-ticker")
    parser.add_argument("--fighter-1")
    parser.add_argument("--fighter-2")
    parser.add_argument("--date", help="YYYY-MM-DD; used with fighter names to discover the event")
    parser.add_argument("--series", default="KXFIGHTMENTION")
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--fee-buffer-cents", type=float, default=2.0)
    parser.add_argument("--min-fighter-fights", type=int, default=15)
    parser.add_argument("--no-fight-model", action="store_true", help="use simple history only")
    parser.add_argument("--show-all", action="store_true", help="show rejected rows and audit details")
    parser.add_argument("--poll-seconds", type=float, default=0, help="poll live books repeatedly; 0 runs once")
    parser.add_argument("--iterations", type=int, default=0, help="poll count; 0 means until interrupted")
    args = parser.parse_args()

    client = KalshiClient()
    event_ticker = args.event_ticker
    if not event_ticker:
        if not args.fighter_1 or not args.fighter_2:
            parser.error("use --event-ticker or provide --fighter-1 and --fighter-2")
        event_ticker = client.find_event(args.fighter_1, args.fighter_2, args.date, args.series)

    print(f"Loading transcript corpus from {args.data_dir} ...")
    corpus = TranscriptCorpus.load(args.data_dir)
    print(f"Loaded {len(corpus.fights)} valid fights. READ-ONLY: this command cannot place trades.\n")
    context_model = None
    if not args.no_fight_model:
        print("Loading fight-level phrase model ...")
        context_model = KalshiFightContextModel.load(corpus)
        print("Live rows will use fight-specific model probabilities when available.\n")

    iteration = 0
    while True:
        iteration += 1
        fighter_1, fighter_2, rows = analyze_event(
            client,
            corpus,
            event_ticker,
            args.fighter_1,
            args.fighter_2,
            context_model=context_model,
            require_context_model=not args.no_fight_model,
            fee_buffer=args.fee_buffer_cents / 100.0,
            min_fighter_fights=args.min_fighter_fights,
        )
        print(f"{event_ticker} | {fighter_1} vs {fighter_2} | live order books | {len(rows)} phrase markets")
        print_rows(rows, show_all=args.show_all)
        if args.poll_seconds <= 0 or (args.iterations and iteration >= args.iterations):
            break
        print(f"\nPolling again in {args.poll_seconds:g}s ...\n")
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
