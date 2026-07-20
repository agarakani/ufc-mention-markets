#!/usr/bin/env python3
"""Refresh live Kalshi UFC mention prices and dashboard data, read-only."""

from __future__ import annotations

import argparse
import csv
import os
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.build_dashboard_data import build_payload, write_data, OUT_DEFAULT as DASHBOARD_DATA
from ufc_mentions.kalshi_client import KalshiClient
from ufc_mentions.kalshi_context_model import KalshiFightContextModel
from ufc_mentions.kalshi_mentions import (
    TranscriptCorpus,
    event_date_from_ticker,
    fighters_from_market_title,
)
from scripts.live.price_fight import price_market
from ufc_mentions.entry_rules import EDGE_CAP_DEFAULT, load_phrase_trust
from scripts.model.backtest_pl import (
    PRICE_HISTORY,
    load_results_cache,
    pending_result_events,
    read_csv as read_history_csv,
    run_backtest,
)
from scripts.tracking.live_paper import OUT_ROOT_DEFAULT as PAPER_ROOT_DEFAULT
from scripts.tracking.live_paper import record_live_entries


DATA_DEFAULT = ROOT / "ufc_cleaned_export"
LIVE_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
HISTORY_DEFAULT = ROOT / "market_data" / "kalshi_price_history.csv"
META_DEFAULT = ROOT / "market_data" / "kalshi_live_meta.json"
SETTLE_ATTEMPT_MARKER = ROOT / "model_outputs" / ".pl_settle_attempt"
SETTLE_MIN_INTERVAL_SECONDS = 30 * 60
PHOTO_FETCH_MARKER = ROOT / "model_outputs" / ".photo_fetch_stamp"
PHOTO_FETCH_INTERVAL_SECONDS = 6 * 60 * 60
UPCOMING_FETCH_MARKER = ROOT / "model_outputs" / ".upcoming_fetch_stamp"
UPCOMING_FETCH_INTERVAL_SECONDS = 24 * 60 * 60


def cards_needing_settle(
    out_root: Path,
    active_cards: set[str],
    *,
    now: datetime | None = None,
    min_recheck_minutes: float = 15.0,
) -> list[str]:
    """Tracking cards whose outcomes still need a result check.

    A finished card drops out of the live Kalshi feed, so the normal entry
    path never touches it again. This finds cards with unresolved outcomes
    that have not been rechecked recently, so the refresher can keep asking
    Kalshi for results until every entry is settled.
    """
    now = now or datetime.now(timezone.utc)
    due: list[str] = []
    root = Path(out_root)
    if not root.exists():
        return due
    for card_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        card = card_dir.name
        if card in active_cards:
            continue
        outcomes = read_csv(card_dir / "outcomes.csv")
        if not outcomes:
            continue
        unresolved = [
            row for row in outcomes
            if str(row.get("outcome", "")).strip().lower() not in ("yes", "no")
        ]
        if not unresolved:
            continue
        last_checked = max((str(row.get("checked_at", "")) for row in outcomes), default="")
        if last_checked:
            try:
                checked_at = datetime.fromisoformat(last_checked)
                if (now - checked_at).total_seconds() < min_recheck_minutes * 60:
                    continue
            except ValueError:
                pass
        due.append(card)
    return due


def settle_finished_paper_cards(
    client,
    *,
    out_root: Path = PAPER_ROOT_DEFAULT,
    active_cards: set[str],
    verbose: bool = False,
) -> None:
    for card in cards_needing_settle(Path(out_root), active_cards):
        try:
            result = record_live_entries(
                [],
                card=card,
                out_root=Path(out_root),
                client=client,
                allow_entries=False,
            )
            if verbose:
                print(
                    f"  settled outcomes for {card}: "
                    f"{result.get('resolved', 0)} resolved, {result.get('pending', 0)} pending",
                    flush=True,
                )
        except Exception as exc:
            if verbose:
                print(f"  outcome check failed for {card}: {exc}", flush=True)


def paper_card_groups(paper_card: str, rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Split rows into (card name, rows) groups for the paper tracker.

    With an explicit card name, everything goes into that one card. With
    "auto", each fight-event date becomes its own card (ufc_card_YYYY-MM-DD),
    so an always-on server tracks every card without anyone naming it.
    """
    if paper_card.strip().lower() != "auto":
        return [(paper_card, rows)] if rows else []
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        event_date = str(row.get("event_date", "")).strip()
        if not event_date:
            continue
        by_date.setdefault(event_date, []).append(row)
    return [(f"ufc_card_{event_date}", group) for event_date, group in sorted(by_date.items())]


def combine_paper_results(paper_card: str, results: list[dict]) -> dict | None:
    """Merge per-card tracker results into the single summary the meta expects."""
    if not results:
        return None
    if len(results) == 1 and paper_card.strip().lower() != "auto":
        return results[0]
    combined = dict(results[0])
    for key in ("new_entries", "total_entries", "resolved", "pending", "open"):
        combined[key] = sum(int(result.get(key) or 0) for result in results)
    combined["card"] = ", ".join(str(result.get("card", "")) for result in results)
    combined["path"] = "; ".join(str(result.get("path", "")) for result in results)
    return combined


def maybe_settle_money_backtest(*, now: float | None = None) -> str:
    """Fold finished cards into the money backtest without being asked.

    Runs only when a past-dated event still has markets with no known result,
    and at most once every SETTLE_MIN_INTERVAL_SECONDS so the poll loop stays
    cheap. Read-only, like everything else here.
    """
    now = time.time() if now is None else now
    history = read_history_csv(PRICE_HISTORY)
    if not history:
        return "no price history yet"
    today = datetime.now(timezone.utc).date().isoformat()
    pending = pending_result_events(history, load_results_cache(), today)
    if not pending:
        return "nothing new to settle"
    if SETTLE_ATTEMPT_MARKER.exists():
        age = now - SETTLE_ATTEMPT_MARKER.stat().st_mtime
        if age < SETTLE_MIN_INTERVAL_SECONDS:
            return f"waiting to retry ({int((SETTLE_MIN_INTERVAL_SECONDS - age) // 60)}m)"
    SETTLE_ATTEMPT_MARKER.parent.mkdir(parents=True, exist_ok=True)
    SETTLE_ATTEMPT_MARKER.touch()
    summary = run_backtest(offline=False, quiet=True)
    try:
        from scripts.model.build_results_labels import build as build_labels
        build_labels(offline=False, quiet=True)
        import subprocess
        subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "model" / "walkforward_update.py")],
            stdout=open(ROOT / "model_outputs" / "walkforward.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception:
        pass  # labels and retraining are byproducts; never break the refresh
    official = summary.get("official") or {}
    return (
        f"settled {summary.get('markets_with_results', 0)} markets "
        f"through {summary.get('latest_settled_event_date') or '?'}; "
        f"paper trades now {official.get('trades', 0)}"
    )

def _launch_photo_fetch() -> None:
    import subprocess

    subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "data" / "fetch_fighter_photos.py"), "--from-live"],
        stdout=open(ROOT / "model_outputs" / "photo_fetch.log", "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def maybe_fetch_photos(*, now: float | None = None) -> str:
    now = time.time() if now is None else now
    if PHOTO_FETCH_MARKER.exists():
        age = now - PHOTO_FETCH_MARKER.stat().st_mtime
        if age < PHOTO_FETCH_INTERVAL_SECONDS:
            return f"waiting ({int((PHOTO_FETCH_INTERVAL_SECONDS - age) // 3600)}h)"
    try:
        PHOTO_FETCH_MARKER.parent.mkdir(parents=True, exist_ok=True)
        PHOTO_FETCH_MARKER.touch()
        _launch_photo_fetch()
    except Exception:
        return "photo fetch skipped"
    return "photo fetch started"


def maybe_fetch_upcoming(*, now: float | None = None) -> str:
    now = time.time() if now is None else now
    if UPCOMING_FETCH_MARKER.exists():
        age = now - UPCOMING_FETCH_MARKER.stat().st_mtime
        if age < UPCOMING_FETCH_INTERVAL_SECONDS:
            return "waiting"
    try:
        UPCOMING_FETCH_MARKER.parent.mkdir(parents=True, exist_ok=True)
        UPCOMING_FETCH_MARKER.touch()
        from scripts.data.fetch_upcoming_events import OUT_DEFAULT as UPCOMING_OUT, refresh as refresh_upcoming
        return refresh_upcoming(UPCOMING_OUT)
    except Exception as exc:
        return f"upcoming fetch skipped ({exc})"


FIELDS = [
    "snapshot_timestamp", "series_ticker", "event_ticker", "event_date",
    "event_title", "fighter_1", "fighter_2", "ticker", "phrase", "forms",
    "rules_primary", "market_status", "market_result", "market_expiration_value",
    "market_close_time", "model_probability", "history_probability", "probability_source",
    "context_probability", "context_status", "context_note", "context_profile",
    "context_training_rows", "context_validation_rows", "context_positive_rate",
    "context_validation_log_loss", "context_base_log_loss",
    "context_log_loss_improvement", "context_best_c", "context_calibrated",
    "context_row_source", "league_rate", "league_hits",
    "league_fights", "fighter_rate", "fighter_hits", "fighter_fights",
    "word_type", "prior_strength", "confidence_ok", "confidence_note",
    "yes_bid", "yes_ask", "no_bid", "no_ask", "spread", "fee_buffer",
    "data_risk", "data_buffer", "hurdle", "yes_edge", "no_edge", "side", "side_price", "edge",
    "edge_cap", "gap_blocked", "trust_ok", "trust_note", "block_reason",
    "watch", "validation_status",
    "previous_yes_ask", "ask_change", "status", "error",
]

HISTORY_FIELDS = [
    "snapshot_timestamp", "event_ticker", "ticker", "phrase", "yes_bid",
    "yes_ask", "no_bid", "no_ask", "spread", "model_probability",
    "history_probability", "probability_source",
    "context_status", "market_status", "market_result", "market_expiration_value",
    "yes_edge", "no_edge", "side", "side_price", "edge",
    "edge_cap", "gap_blocked", "trust_ok",
    "data_risk", "data_buffer", "hurdle", "watch",
]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def append_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            existing_fields = next(csv.reader(fh), [])
        if existing_fields != fields:
            legacy_rows = read_csv(path)
            write_csv(path, legacy_rows, fields)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def value(value) -> str:
    return "" if value is None else f"{float(value):.8f}"


def bool_text(value: bool) -> str:
    return "yes" if value else "no"


def event_fighters(event: dict) -> tuple[str, str]:
    title = event.get("sub_title") or event.get("title") or ""
    try:
        return fighters_from_market_title(title)
    except Exception:
        match = re.search(r"^(.+?)\s+vs\.?\s+(.+?)\s+(?:UFC\s+)?Fight\b", title, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "", ""


def event_metadata(event: dict, rows: list[dict], *, error: str = "") -> dict:
    event_ticker = event.get("event_ticker", "")
    fighter_1, fighter_2 = event_fighters(event)
    if rows:
        fighter_1 = rows[0].get("fighter_1") or fighter_1
        fighter_2 = rows[0].get("fighter_2") or fighter_2
    return {
        "event_ticker": event_ticker,
        "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
        "event_date": event_date_from_ticker(event_ticker) or "",
        "title": event.get("title", ""),
        "sub_title": event.get("sub_title", ""),
        "fighter_1": fighter_1,
        "fighter_2": fighter_2,
        "category": event.get("category", ""),
        "available_on_brokers": bool_text(bool(event.get("available_on_brokers"))),
        "last_updated_ts": event.get("last_updated_ts", ""),
        "market_rows": len(rows),
        "priced_rows": sum(bool(row.get("yes_ask")) for row in rows),
        "watch_rows": sum(row.get("watch") == "yes" for row in rows),
        "error": error,
    }


def event_snapshot(
    client: KalshiClient,
    corpus: TranscriptCorpus,
    event: dict,
    *,
    fee_buffer: float,
    min_fighter_fights: int,
    low_data_buffer: float = 0.10,
    snapshot_timestamp: str,
    context_model=None,
    require_context_model: bool = False,
    edge_cap: float = EDGE_CAP_DEFAULT,
    phrase_trust_map: dict | None = None,
) -> list[dict]:
    event_ticker = event.get("event_ticker", "")
    markets = client.get_markets(event_ticker=event_ticker)
    if not markets:
        return []
    title = event.get("title") or markets[0].get("title", "")
    fighter_1, fighter_2 = fighters_from_market_title(markets[0].get("title", title))
    event_date = event_date_from_ticker(event_ticker) or ""
    rows = []
    for market in markets:
        phrase = str((market.get("custom_strike") or {}).get("Word") or market.get("yes_sub_title") or "")
        book = client.get_orderbook(market["ticker"])
        try:
            priced = price_market(
                market,
                book,
                corpus,
                fighter_1,
                fighter_2,
                cutoff_date=event_date or None,
                fee_buffer=fee_buffer,
                min_fighter_fights=min_fighter_fights,
                low_data_buffer=low_data_buffer,
                context_model=context_model,
                require_context_model=require_context_model,
                edge_cap=edge_cap,
                phrase_trust_map=phrase_trust_map,
            )
        except Exception as exc:
            rows.append({
                "snapshot_timestamp": snapshot_timestamp,
                "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
                "event_ticker": event_ticker,
                "event_date": event_date,
                "event_title": title,
                "fighter_1": fighter_1,
                "fighter_2": fighter_2,
                "ticker": market.get("ticker", ""),
                "phrase": phrase,
                "forms": phrase,
                "rules_primary": market.get("rules_primary", ""),
                "market_status": market.get("status", ""),
                "market_result": market.get("result", ""),
                "market_expiration_value": market.get("expiration_value", ""),
                "market_close_time": market.get("close_time", ""),
                "yes_bid": value(book.yes_bid),
                "yes_ask": value(book.yes_ask),
                "no_bid": value(book.no_bid),
                "no_ask": value(book.no_ask),
                "spread": value(book.spread),
                "fee_buffer": value(fee_buffer),
                "data_risk": bool_text(False),
                "data_buffer": value(0),
                "watch": bool_text(False),
                "validation_status": "unvalidated",
                "probability_source": "unavailable",
                "status": "error",
                "error": str(exc),
            })
            continue
        if priced is None:
            continue
        estimate = priced.estimate
        rows.append({
            "snapshot_timestamp": snapshot_timestamp,
            "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
            "event_ticker": event_ticker,
            "event_date": event_date,
            "event_title": title,
            "fighter_1": fighter_1,
            "fighter_2": fighter_2,
            "ticker": priced.ticker,
            "phrase": priced.label,
            "forms": " | ".join(priced.forms),
            "rules_primary": priced.rules,
            "market_status": market.get("status", ""),
            "market_result": market.get("result", ""),
            "market_expiration_value": market.get("expiration_value", ""),
            "market_close_time": market.get("close_time", ""),
            "model_probability": value(estimate.probability),
            "history_probability": value(estimate.history_probability),
            "probability_source": estimate.probability_source,
            "context_probability": value(estimate.context_probability),
            "context_status": estimate.context_status,
            "context_note": estimate.context_note,
            "context_profile": estimate.context_profile,
            "context_training_rows": estimate.context_training_rows,
            "context_validation_rows": estimate.context_validation_rows,
            "context_positive_rate": value(estimate.context_positive_rate),
            "context_validation_log_loss": value(estimate.context_validation_log_loss),
            "context_base_log_loss": value(estimate.context_base_log_loss),
            "context_log_loss_improvement": value(estimate.context_log_loss_improvement),
            "context_best_c": estimate.context_best_c,
            "context_calibrated": bool_text(estimate.context_calibrated),
            "context_row_source": estimate.context_row_source,
            "league_rate": value(estimate.league_rate),
            "league_hits": estimate.league_hits,
            "league_fights": estimate.league_fights,
            "fighter_rate": value(estimate.fighter_rate),
            "fighter_hits": estimate.fighter_hits,
            "fighter_fights": estimate.fighter_fights,
            "word_type": estimate.word_type,
            "prior_strength": "" if estimate.prior_strength is None else value(estimate.prior_strength),
            "confidence_ok": bool_text(estimate.confidence_ok),
            "confidence_note": estimate.confidence_note,
            "yes_bid": value(book.yes_bid),
            "yes_ask": value(book.yes_ask),
            "no_bid": value(book.no_bid),
            "no_ask": value(book.no_ask),
            "spread": value(book.spread),
            "fee_buffer": value(fee_buffer),
            "data_risk": bool_text(priced.data_risk),
            "data_buffer": value(priced.data_buffer),
            "hurdle": value(priced.hurdle),
            "yes_edge": value(priced.yes_edge),
            "no_edge": value(priced.no_edge),
            "side": priced.side,
            "side_price": value(priced.side_price),
            "edge": value(priced.edge),
            "edge_cap": value(priced.edge_cap),
            "gap_blocked": bool_text(priced.gap_blocked),
            "trust_ok": bool_text(priced.trust_ok),
            "trust_note": priced.trust_note,
            "block_reason": priced.block_reason,
            "watch": bool_text(priced.watch),
            "validation_status": priced.validation_status,
            "status": "ok",
            "error": "",
        })
    return rows


def add_price_changes(rows: list[dict], previous: list[dict]) -> None:
    previous_by_ticker = {row.get("ticker"): row for row in previous}
    for row in rows:
        old = previous_by_ticker.get(row.get("ticker"), {})
        prior = old.get("yes_ask", "")
        row["previous_yes_ask"] = prior
        try:
            row["ask_change"] = value(float(row["yes_ask"]) - float(prior))
        except (KeyError, TypeError, ValueError):
            row["ask_change"] = ""


def refresh_once(
    client: KalshiClient,
    corpus: TranscriptCorpus,
    *,
    series_ticker: str,
    event_ticker: str | None,
    exclude_event_tickers: set[str] | None = None,
    fee_buffer: float,
    min_fighter_fights: int,
    low_data_buffer: float = 0.10,
    poll_seconds: float,
    context_model=None,
    require_context_model: bool = True,
    verbose: bool = False,
    live_path: Path = LIVE_DEFAULT,
    history_path: Path = HISTORY_DEFAULT,
    meta_path: Path = META_DEFAULT,
    paper_card: str | None = None,
    paper_out_root: Path = PAPER_ROOT_DEFAULT,
    paper_contracts: float = 1.0,
    paper_settle_only: bool = False,
) -> list[dict]:
    snapshot_timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if event_ticker:
        events = [{
            "event_ticker": event_ticker,
            "series_ticker": series_ticker,
            "title": "",
        }]
    else:
        events = client.get_events(series_ticker=series_ticker, status="open")
        excluded = {ticker.upper() for ticker in (exclude_event_tickers or set())}
        if excluded:
            events = [
                event for event in events
                if str(event.get("event_ticker") or "").upper() not in excluded
            ]

    if verbose:
        print(f"Found {len(events)} open Kalshi fight event(s). Pricing phrases now...", flush=True)

    rows = []
    errors = []
    event_rows_for_meta = []
    phrase_trust_map = load_phrase_trust()
    for index, event in enumerate(events, start=1):
        event_name = event.get("title") or event.get("event_ticker") or "fight"
        if verbose:
            print(f"  {index}/{len(events)} {event_name}", flush=True)
        try:
            event_rows = event_snapshot(
                client,
                corpus,
                event,
                context_model=context_model,
                require_context_model=require_context_model,
                fee_buffer=fee_buffer,
                min_fighter_fights=min_fighter_fights,
                low_data_buffer=low_data_buffer,
                snapshot_timestamp=snapshot_timestamp,
                phrase_trust_map=phrase_trust_map,
            )
            rows.extend(event_rows)
            event_rows_for_meta.append(event_metadata(event, event_rows))
        except Exception as exc:
            errors.append(f"{event.get('event_ticker', '')}: {exc}")
            event_rows_for_meta.append(event_metadata(event, [], error=str(exc)))
            if verbose:
                print(f"    skipped: {exc}", flush=True)

    rows.sort(key=lambda row: (
        row.get("watch") != "yes",
        -(float(row.get("edge") or -999)),
        row.get("event_date", ""),
        row.get("phrase", ""),
    ))
    previous = read_csv(live_path)
    add_price_changes(rows, previous)
    write_csv(live_path, rows, FIELDS)
    append_csv(history_path, rows, HISTORY_FIELDS)
    paper_tracking = None
    if paper_card:
        card_groups = paper_card_groups(paper_card, rows)
        results = []
        for card_name, card_rows in card_groups:
            results.append(record_live_entries(
                card_rows,
                card=card_name,
                out_root=paper_out_root,
                contracts=paper_contracts,
                client=client,
                allow_entries=not paper_settle_only,
            ))
        paper_tracking = combine_paper_results(paper_card, results)
        # Finished cards leave the live feed; keep checking their results
        # until every entry has settled.
        settle_finished_paper_cards(
            client,
            out_root=paper_out_root,
            active_cards={name for name, _rows in card_groups},
            verbose=verbose,
        )
        if verbose and paper_tracking:
            print(
                "  paper tracker: "
                f"{paper_tracking['new_entries']} new, "
                f"{paper_tracking['total_entries']} total "
                f"({paper_tracking['path']})",
                flush=True,
            )

    meta = {
        "snapshot_timestamp": snapshot_timestamp,
        "series_ticker": series_ticker,
        "poll_seconds": poll_seconds,
        "events_discovered": len(events),
        "events": event_rows_for_meta,
        "excluded_event_tickers": sorted(exclude_event_tickers or []),
        "markets_priced": len(rows),
        "watch_rows": sum(row.get("watch") == "yes" for row in rows),
        "low_data_buffer": low_data_buffer,
        "fight_model_required": require_context_model,
        "authenticated": client.authenticated,
        "paper_tracking": paper_tracking,
        "errors": errors,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # Fold any newly finished cards into the money backtest. Throttled and
    # read-only; runs here so the always-on server settles by itself too.
    try:
        settle_note = maybe_settle_money_backtest()
        if verbose and settle_note != "nothing new to settle":
            print(f"  money backtest: {settle_note}", flush=True)
    except Exception as exc:
        if verbose:
            print(f"  money backtest settle skipped: {exc}", flush=True)

    photo_note = maybe_fetch_photos()
    if verbose and photo_note == "photo fetch started":
        print("  fighter photos: refresh started", flush=True)

    upcoming_note = maybe_fetch_upcoming()
    if verbose and "saved" in upcoming_note:
        print(f"  upcoming events: {upcoming_note}", flush=True)

    payload = build_payload()
    write_data(DASHBOARD_DATA, payload)

    # Push the public snapshot when sharing is turned on (UFC_PUBLISH=1).
    # Publishes every minute while a listed card is on today's date.
    if os.environ.get("UFC_PUBLISH") == "1":
        try:
            from scripts.live.publish_site import publish, publish_due, publish_interval_seconds
            today = datetime.now(timezone.utc).date().isoformat()
            live_dates = sorted({str(row.get("event_date", "")) for row in rows if row.get("event_date")})
            if publish_due(interval_seconds=publish_interval_seconds(today, live_dates)):
                note = publish(quiet=True)
                if verbose:
                    print(f"  site: {note}", flush=True)
        except Exception as exc:
            if verbose:
                print(f"  site publish skipped: {exc}", flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously refresh the read-only Kalshi dashboard feed.")
    parser.add_argument("--series", default="KXFIGHTMENTION")
    parser.add_argument("--event-ticker", help="restrict refresh to one event")
    parser.add_argument(
        "--exclude-event-ticker",
        action="append",
        default=[],
        help="skip an event, useful after a fight has started; can be repeated",
    )
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--fee-buffer-cents", type=float, default=2.0)
    parser.add_argument("--low-data-buffer-cents", type=float, default=10.0)
    parser.add_argument("--min-fighter-fights", type=int, default=15)
    parser.add_argument("--no-fight-model", action="store_true", help="use simple history only")
    parser.add_argument("--paper-card", help="record one paper entry the first time a market becomes WATCH")
    parser.add_argument("--paper-contracts", type=float, default=1.0, help="paper contracts per live entry")
    parser.add_argument("--paper-out-root", default=str(PAPER_ROOT_DEFAULT), help="where paper tracking files are written")
    parser.add_argument("--paper-settle-only", action="store_true", help="update paper outcomes without adding new entries")
    parser.add_argument("--poll-seconds", type=float, default=0, help="0 refreshes once")
    parser.add_argument("--iterations", type=int, default=0, help="0 polls until interrupted")
    args = parser.parse_args()

    client = KalshiClient()
    print(f"Loading transcript corpus from {args.data_dir} ...")
    corpus = TranscriptCorpus.load(args.data_dir)
    print(f"Loaded {len(corpus.fights)} valid fights. Kalshi access: {'authenticated' if client.authenticated else 'public read'}.")
    print("READ-ONLY: this process cannot place trades.\n")
    context_model = None
    if not args.no_fight_model:
        print("Loading fight-level phrase model ...")
        context_model = KalshiFightContextModel.load(corpus)
        print("Live rows will use fight-specific model probabilities when available.\n")

    iteration = 0
    while True:
        iteration += 1
        try:
            rows = refresh_once(
                client,
                corpus,
                context_model=context_model,
                require_context_model=not args.no_fight_model,
                series_ticker=args.series,
                event_ticker=args.event_ticker,
                exclude_event_tickers={ticker.upper() for ticker in args.exclude_event_ticker},
                fee_buffer=args.fee_buffer_cents / 100.0,
                low_data_buffer=args.low_data_buffer_cents / 100.0,
                min_fighter_fights=args.min_fighter_fights,
                poll_seconds=args.poll_seconds,
                paper_card=args.paper_card,
                paper_out_root=Path(args.paper_out_root),
                paper_contracts=args.paper_contracts,
                paper_settle_only=args.paper_settle_only,
                verbose=True,
            )
            print(
                f"Refreshed {len({row.get('event_ticker') for row in rows})} fights, "
                f"{len(rows)} phrase markets, {sum(row.get('watch') == 'yes' for row in rows)} watch rows."
            )
        except Exception as exc:
            print(f"Refresh failed; previous dashboard snapshot was preserved: {exc}")
        if args.poll_seconds <= 0 or (args.iterations and iteration >= args.iterations):
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
