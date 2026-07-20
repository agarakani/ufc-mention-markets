# Product Overhaul — Design

Date: 2026-07-19. Approved by Aryo ("do it all at once, I trust you"). Four phases, sequenced; each phase tested + committed before the next.

## Goals

Make the whole product feel professional and personalized: every card, fight, and market should feel special to the fighters involved. Keep the fight-night terminal identity (design system v4) — evolve it, don't replace it. Keep all current functionality; the money-backtest record is never falsified.

## Phase 1 — Fighter Identity System

- `scripts/data/fetch_fighter_photos.py`: fetch fighter headshots from the Wikipedia API (page image thumbnails), cached to `dashboard/assets/fighters/<slug>.jpg`. Incremental (skip existing), fail-soft (dashboard never blocks on it), invoked from the refresh loop when new fighters appear.
- Fallback identity card when no photo: nickname in condensed display type, record, stance/reach (Kaggle join), style tags mined from the fighter's own transcript history (submission/knockout vocabulary rates → GRAPPLER / KNOCKOUT ARTIST / etc.).
- Marquee score per fight: past fights in dataset + title bout + main-event slot. High score → bigger cinematic tale-of-the-tape hero treatment.
- Identity data flows into `build_dashboard_data.py` → data.js.

## Phase 2 — UI Overhaul (fight-night terminal v4, evolved)

- Per-fight pages: click a fight → dedicated view with photo tale-of-the-tape, all phrase markets with plain-English reasoning, both fighters' mention history.
- Upcoming card preview: next event + countdown + lineup with identities, shown even when Kalshi has no open markets (site never looks empty).
- P/L performance visuals: cumulative realized P/L across settled cards, win rate by phrase, calibration — from existing `pl_backtest` outputs. Follow the dataviz skill.
- Signal alerts: "new since last visit" (localStorage watermark), highlighted new-WATCH feed with timestamps.
- Constraints from the v4 brief still stand: no rounded floating cards, no glassmorphism, no purple gradients, one red accent, mono numerals, connected surfaces.

## Phase 3 — Updates (speed + independence)

- Adaptive publish cadence: ~1 min during live cards, 5–15 min otherwise. LIVE indicator + "updated Xs ago" stamp on the page.
- GitHub Actions cloud runner (scheduled): re-prices open Kalshi markets against committed predictions, rebuilds data.js, republishes gh-pages — keeps the site fresh while the Mac sleeps. Mac remains source of truth for training, predictions, paper trades, price-history recording, settlement; the runner is display-only freshness and must not write price history or paper entries. Runner skips publishing if the Mac's published data is fresher.
- Kalshi/Oddpool key in GitHub Actions secrets.

## Phase 4 — Model (targeted, gated)

- Entity features: rival/past-opponent last-name mention rates + arena/location (Kaggle location), leakage-safe (built from strictly earlier fights only).
- Calibration fix for the known 40–60% overconfidence and >60% compression (recalibration layer on chronological validation).
- Ship gate: head-to-head vs current model on the same chronological split + held-out settled cards; adopt only on better log loss. Otherwise keep current model — walk-forward loop stays authoritative.

## Non-negotiables

- 98-test suite stays green; new behavior gets tests.
- Recorded history (price snapshots, paper trades) is never rewritten.
- No terminal steps for the user; everything auto or double-clickable.
- Photos are cached, offline-safe, and optional — the site must look deliberate without them.
