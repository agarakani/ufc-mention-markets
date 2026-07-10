#!/usr/bin/env python3
"""Serve the local dashboard and refresh Kalshi data on demand."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live.refresh_dashboard import DATA_DEFAULT, refresh_once
from scripts.tracking.live_paper import OUT_ROOT_DEFAULT as PAPER_ROOT_DEFAULT
from ufc_mentions.build_dashboard_data import build_payload
from ufc_mentions.kalshi_client import KalshiClient
from ufc_mentions.kalshi_context_model import KalshiFightContextModel
from ufc_mentions.kalshi_mentions import TranscriptCorpus


DASHBOARD_DIR = ROOT / "dashboard"


class DashboardRuntime:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.client = KalshiClient()
        print(f"Loading transcript corpus from {args.data_dir} ...", flush=True)
        self.corpus = TranscriptCorpus.load(args.data_dir)
        print(
            f"Loaded {len(self.corpus.fights)} valid fights. "
            f"Kalshi access: {'authenticated' if self.client.authenticated else 'public read'}.",
            flush=True,
        )
        self.context_model = None
        if not args.no_fight_model:
            print("Loading fight-level phrase model ...", flush=True)
            self.context_model = KalshiFightContextModel.load(self.corpus)
            print("Live rows will use fight-specific model probabilities when available.", flush=True)
        print("READ-ONLY: this server cannot place trades.\n", flush=True)

    def refresh(self) -> dict:
        with self.lock:
            rows = refresh_once(
                self.client,
                self.corpus,
                context_model=self.context_model,
                require_context_model=not self.args.no_fight_model,
                series_ticker=self.args.series,
                event_ticker=self.args.event_ticker,
                exclude_event_tickers={ticker.upper() for ticker in self.args.exclude_event_ticker},
                fee_buffer=self.args.fee_buffer_cents / 100.0,
                low_data_buffer=self.args.low_data_buffer_cents / 100.0,
                min_fighter_fights=self.args.min_fighter_fights,
                poll_seconds=self.args.poll_seconds,
                paper_card=self.args.paper_card,
                paper_out_root=Path(self.args.paper_out_root),
                paper_contracts=self.args.paper_contracts,
                paper_settle_only=self.args.paper_settle_only,
                verbose=True,
            )
            payload = build_payload()
            summary = payload.get("summary", {})
            print(
                f"Dashboard refresh complete: {len({row.get('event_ticker') for row in rows})} fights, "
                f"{len(rows)} phrase markets, {sum(row.get('watch') == 'yes' for row in rows)} watch rows.",
                flush=True,
            )
            return {
                "ok": True,
                "summary": summary,
            }


def make_handler(get_runtime):
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/refresh":
                runtime = get_runtime()
                if runtime is None:
                    self.send_json({
                        "ok": False,
                        "error": "Still starting up: the fight models are loading. "
                                 "The page updates by itself once they are ready.",
                    })
                    return
                self.send_json(runtime.refresh())
                return
            if parsed.path == "/api/status":
                self.send_json({"ok": True, "summary": build_payload().get("summary", {})})
                return
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()

        def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return DashboardHandler


def start_polling(get_runtime, seconds: float) -> threading.Event:
    stop = threading.Event()
    if seconds <= 0:
        return stop

    def loop():
        while not stop.wait(seconds):
            runtime = get_runtime()
            if runtime is None:
                continue
            try:
                runtime.refresh()
            except Exception as exc:
                print(f"Background refresh failed; old dashboard data was kept: {exc}", flush=True)

    thread = threading.Thread(target=loop, name="dashboard-refresh", daemon=True)
    thread.start()
    return stop


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the UFC mention dashboard with live auto-updates.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--series", default="KXFIGHTMENTION")
    parser.add_argument("--event-ticker")
    parser.add_argument("--exclude-event-ticker", action="append", default=[])
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--fee-buffer-cents", type=float, default=2.0)
    parser.add_argument("--low-data-buffer-cents", type=float, default=10.0)
    parser.add_argument("--min-fighter-fights", type=int, default=15)
    parser.add_argument("--no-fight-model", action="store_true")
    parser.add_argument("--paper-card")
    parser.add_argument("--paper-contracts", type=float, default=1.0)
    parser.add_argument("--paper-out-root", default=str(PAPER_ROOT_DEFAULT))
    parser.add_argument("--paper-settle-only", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=0)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    # Serve the page right away with the last saved data; load the heavy
    # models and run the first refresh in the background. The site should
    # never be a dead link just because the Mac restarted.
    state: dict = {"runtime": None}
    server = ThreadingHTTPServer((args.host, args.port), make_handler(lambda: state["runtime"]))
    url = f"http://{args.host}:{args.port}/"
    print(f"Dashboard server running at {url}", flush=True)
    print("Serving the last saved data while the fight models load...", flush=True)

    def start_runtime():
        try:
            runtime = DashboardRuntime(args)
            state["runtime"] = runtime
            runtime.refresh()
        except Exception as exc:
            print(f"Startup refresh failed; serving the last saved dashboard data: {exc}", flush=True)

    threading.Thread(target=start_runtime, name="dashboard-startup", daemon=True).start()
    stop_polling = start_polling(lambda: state["runtime"], args.poll_seconds)
    print("The dashboard auto-updates while this server is running.", flush=True)
    print("Use Update now only when you want an immediate extra refresh.", flush=True)
    if args.poll_seconds > 0:
        print(f"Background refresh: every {args.poll_seconds:g}s", flush=True)
    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_polling.set()
        server.server_close()
        print("\nDashboard server stopped.", flush=True)


if __name__ == "__main__":
    main()
