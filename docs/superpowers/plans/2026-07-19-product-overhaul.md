# Product Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Personalized, broadcast-quality dashboard (photos + rich fighter identities + per-fight pages + P/L visuals + alerts), faster/cloud-independent site updates, and gated model upgrades.

**Architecture:** The Mac stays the brain (training, predictions, paper trades, history). New offline-safe identity data (photos cache + fighter directory CSV) flows through `build_dashboard_data.py` into `data.js`; the vanilla-JS dashboard gains hash-routed fight pages and inline-SVG charts. A GitHub Actions runner freshens prices/edges on gh-pages when the Mac sleeps. Model changes ship only if they beat the current model on held-out cards.

**Tech Stack:** Python 3 stdlib + requests, vanilla JS/CSS (no build step), pytest, GitHub Actions, Wikipedia API, Kalshi public API.

## Global Constraints

- 98-test pytest suite stays green; every new module gets tests (`python3 -m pytest -q`).
- Never rewrite recorded history: `market_data/kalshi_price_history.csv`, tracking paper positions, results caches.
- Design system v4 stands: charcoal #0a0a0b, ink #ece9e2, single red accent #e5484d, condensed display type + mono numerals, squared connected panels, no glassmorphism/rounded floating cards/purple gradients.
- Everything fail-soft: network fetches (Wikipedia, Kalshi) must never break refresh or dashboard build.
- No user terminal steps; all new behavior rides the existing LaunchAgent refresh loop.
- Photos/identity assets live in `dashboard/assets/fighters/` (committed, published with site).
- No new Python deps beyond `requests` (already available).

---

## Phase 1 — Fighter Identity System

### Task 1.1: Fighter directory builder

**Files:**
- Create: `scripts/data/build_fighter_directory.py`
- Test: `tests/test_fighter_directory.py`

**Interfaces:**
- Produces: `data/processed/fighter_directory.csv` with columns:
  `name, name_lower, nickname, n_fights, last_event_date, record_wins, record_losses, stance, height_cms, reach_cms, rate_submission, rate_knockout_family, rate_decision_family, rate_choke, style_tags, marquee_score`
- Function `build_directory(fight_rows, joined_rows) -> list[dict]` (pure, testable).
- Function `style_tags(rates: dict, league: dict) -> list[str]`: tag when fighter rate ≥ league rate + 0.15 → `GRAPPLER` (submission), `FINISHER` (knockout_family = knockout|ko|tko|knocked_out), `DISTANCE FIGHTER` (decision family); max 2 tags, highest lift first.
- `marquee_score = min(n_fights, 15) + 10*title_bout_count` (title bouts from joined `title_bout`/weight-class "Title" markers).

**Steps:**
- [ ] Write failing tests: `test_directory_aggregates_fighter_rates` (two synthetic fights → correct n_fights/rates), `test_style_tags_thresholds` (rate below league+0.15 → no tag), `test_nickname_and_stats_from_latest_fight` (stance/record from most recent joined row; nickname from fight_mentions if present else "").
- [ ] Run: `python3 -m pytest tests/test_fighter_directory.py -q` → FAIL (module missing).
- [ ] Implement builder reading `data/processed/fight_mentions.csv` + `data/processed/joined_fights.csv` (Kaggle `kaggle_R_/B_` columns matched by corner via last-name comparison), writing the CSV. CLI: `python3 scripts/data/build_fighter_directory.py`.
- [ ] Tests pass; run full suite. Commit: `feat: fighter directory with style tags and marquee scores`.

### Task 1.2: Wikipedia photo fetcher

**Files:**
- Create: `scripts/data/fetch_fighter_photos.py`
- Test: `tests/test_fighter_photos.py`

**Interfaces:**
- Produces: `dashboard/assets/fighters/<slug>.jpg` + `dashboard/assets/fighters/manifest.json` mapping `name_lower -> {status: "ok"|"not_found", file, source_title, fetched_at}`.
- `slugify(name) -> str` (lowercase, non-alnum → `_`, collapse repeats).
- `resolve_photo(name, http_get) -> dict | None`: search Wikipedia (`list=search`, `srsearch=f"{name} mixed martial artist"`, srlimit=3), require snippet/title match containing fighter-ish evidence (`martial|fighter|UFC` in snippet, title similarity to name), then `prop=pageimages&pithumbsize=500`, download thumbnail.
- `fetch_missing(names, root, http_get, now) -> dict` — skips manifest hits (`ok` always; `not_found` retried after 30 days), never raises (records `not_found` on errors).

**Steps:**
- [ ] Failing tests with a fake `http_get`: `test_slugify`, `test_resolve_photo_happy_path`, `test_rejects_wrong_person` (snippet without martial/fighter/UFC → None), `test_manifest_skips_existing_and_retries_stale_not_found`, `test_network_error_is_soft`.
- [ ] Implement with `requests` (timeout=10, custom User-Agent). CLI: `--names` list or `--from-live` (names from `market_data/kalshi_live_edges.csv` + `data/tracking/*/paper_positions.csv` + fighter directory top-marquee).
- [ ] Tests pass; full suite green. Commit: `feat: cached Wikipedia photo fetcher for fighters`.

### Task 1.3: Identity payload in dashboard data

**Files:**
- Modify: `ufc_mentions/build_dashboard_data.py`
- Test: `tests/test_dashboard_identity.py`

**Interfaces:**
- `build_payload()` gains `"fighters": {name_lower: identity}` where identity = directory row + `photo` (relative asset path when manifest says ok, else None).
- Each fight in `kalshi_cards[].fights[]` gains `marquee_score` (sum of both fighters' scores, 0 when unknown).

**Steps:**
- [ ] Failing tests: `test_payload_includes_fighter_identities` (temp directory CSV + manifest → payload entries with photo path), `test_missing_directory_is_soft` (no CSV → `fighters: {}`), `test_fight_marquee_score`.
- [ ] Implement: read directory CSV + manifest in `build_payload`, attach.
- [ ] Suite green. Commit: `feat: fighter identities flow into dashboard feed`.

### Task 1.4: Refresh-loop integration

**Files:**
- Modify: `scripts/live/refresh_dashboard.py`
- Test: `tests/test_refresh_photo_hook.py`

**Interfaces:**
- `maybe_fetch_photos(root, now)` in refresh loop: throttled to once per 6h via marker `model_outputs/.photo_fetch_stamp`, runs fetcher `--from-live` in a subprocess (fail-soft, logged).

**Steps:**
- [ ] Failing test: `test_photo_fetch_throttled` (fresh stamp → skip; stale → invoked via injected runner).
- [ ] Implement + wire into `refresh_once`.
- [ ] Suite green. Commit: `feat: refresh loop keeps fighter photos current`.

---

## Phase 2 — UI Overhaul

### Task 2.1: Identity components (avatars everywhere)

**Files:**
- Modify: `dashboard/app.js`, `dashboard/styles.css`

**Interfaces:**
- `identityFor(name) -> identity|null` (lookup in `data.fighters`).
- `avatarHtml(identity, size)` — photo `<img>` (object-fit cover, squared, hairline border) when `photo`, else upgraded medallion (initials + corner tint) with nickname strip. Used in card nav, fight header, tables, paper blotter.

**Steps:**
- [ ] Implement components; replace existing medallion call sites.
- [ ] Verify in browser (preview server): photos render, fallbacks render, no layout breaks in all three tabs.
- [ ] Commit: `feat: fighter avatars with photo + rich fallback identity`.

### Task 2.2: Per-fight pages (hash routing)

**Files:**
- Modify: `dashboard/app.js`, `dashboard/index.html`, `dashboard/styles.css`

**Interfaces:**
- Routes: `#fight/<event_ticker>` renders a dedicated fight page; back link returns to `#markets`. `renderFightPage(eventTicker)`.
- Page contents: tale-of-the-tape hero (photos/medallions, nickname, record, stance, reach, style tags; marquee_score ≥ 20 → cinematic large hero with cage-diamond texture), full phrase-market table for that fight (reusing row rendering + audit expansion), "fighter history" strip: each fighter's historical rates for the page's phrases (from `data.fighters`).

**Steps:**
- [ ] Implement routing (hashchange listener + render dispatch), fight page renderer, hero styles (v4 tokens).
- [ ] Browser-verify: navigate card → fight → back; marquee vs normal hero; empty-market fights show identity + "no open markets".
- [ ] Commit: `feat: dedicated per-fight pages with tale-of-the-tape heroes`.

### Task 2.3: Upcoming card preview

**Files:**
- Create: `scripts/data/fetch_upcoming_events.py`
- Modify: `ufc_mentions/build_dashboard_data.py`, `scripts/live/refresh_dashboard.py`, `dashboard/app.js`
- Test: `tests/test_upcoming_events.py`

**Interfaces:**
- Fetcher parses Wikipedia `List_of_UFC_events` scheduled-events table (via `action=parse&prop=wikitext`) → `data/processed/upcoming_events.json`: `[{name, date, venue, location}]`, future-dated only. Fail-soft; refreshed daily via marker `model_outputs/.upcoming_fetch_stamp`.
- `build_payload()` gains `"upcoming_events"`. Dashboard: when no live Kalshi cards, Markets tab shows "NEXT EVENT" panel — event name, venue, countdown (days/hours), plus lineup from Kalshi meta when available.

**Steps:**
- [ ] Failing tests: `test_parse_scheduled_events_wikitext` (fixture wikitext → rows), `test_future_only`, `test_fetch_error_keeps_old_file`.
- [ ] Implement fetcher + payload + daily hook.
- [ ] Implement UI panel; browser-verify with current between-cards state (this is live right now — perfect test).
- [ ] Suite green. Commit: `feat: upcoming card preview so the site is never empty`.

### Task 2.4: P/L performance visuals

**Files:**
- Modify: `ufc_mentions/build_dashboard_data.py`, `scripts/model/backtest_pl.py` (export per-phrase aggregates), `dashboard/app.js`, `dashboard/styles.css`
- Test: extend `tests/test_model_health.py`

**Interfaces:**
- `build_payload()` gains `"performance": {equity: [{date, cumulative_pnl, card_pnl}], by_phrase: [{phrase, trades, wins, pnl}]}` derived from `model_outputs/pl_backtest_trades.csv` (official trades, sorted by event date).
- Dashboard Paper tab: inline-SVG equity stepline + win-rate-by-phrase bars (mono numerals, red accent only for negative P/L semantics per v4; consult dataviz skill before coding the charts).

**Steps:**
- [ ] Failing test: `test_performance_payload_from_trades` (synthetic trades CSV → cumulative series + phrase aggregates).
- [ ] Implement payload; implement SVG charts; browser-verify both charts with real data (127 trades).
- [ ] Suite green. Commit: `feat: P/L equity curve and per-phrase performance visuals`.

### Task 2.5: Signal alerts ("new since last visit")

**Files:**
- Modify: `dashboard/app.js`, `dashboard/styles.css`, `dashboard/index.html`

**Interfaces:**
- localStorage key `ufc_last_seen_ts`. On load: WATCH rows with `snapshot_timestamp > lastSeen` get a `NEW` chip + a "Signals" feed strip at the top of Markets (timestamped, newest first). Tab badge shows new-signal count; watermark updates when Markets tab is viewed.

**Steps:**
- [ ] Implement; browser-verify by clearing localStorage and reloading.
- [ ] Commit: `feat: new-signal alerts and signal feed`.

### Task 2.6: Polish pass

**Steps:**
- [ ] Full-app browser review at desktop + mobile widths, dark canvas only; fix hierarchy/spacing/motion issues; ensure staggered entrances and reduced-motion guard still hold; screenshot proof.
- [ ] Commit: `style: broadcast-quality polish pass`.

---

## Phase 3 — Updates (speed + independence)

### Task 3.1: Adaptive publish cadence + LIVE indicator

**Files:**
- Modify: `scripts/live/refresh_dashboard.py`, `scripts/live/publish_site.py`, `dashboard/app.js`
- Test: extend `tests/test_publish_site.py`

**Interfaces:**
- `publish_interval_seconds(now, live_event_dates) -> int`: 60 when any open Kalshi event has `event_date == today`, else 600.
- Page header: `LIVE` pill when data < 3 min old and a card is live today; "updated Xs ago" ticker otherwise.

**Steps:**
- [ ] Failing test: `test_publish_interval_live_vs_idle`.
- [ ] Implement + UI indicator; suite green. Commit: `feat: 1-minute publishing during live cards with LIVE indicator`.

### Task 3.2: Public feed for the cloud runner

**Files:**
- Modify: `scripts/live/publish_site.py`
- Test: extend `tests/test_publish_site.py`

**Interfaces:**
- Publishing now also writes `feed/predictions.json` to gh-pages: per open market `{ticker, event_ticker, phrase, fighters, model_probability, probability_source, league_rate, fighter_rate, trust_ok, generated_at}` — enough for the runner to re-price edges. No raw dataset content.

**Steps:**
- [ ] Failing test: `test_predictions_feed_written`.
- [ ] Implement; suite green. Commit: `feat: publish model feed for cloud refresher`.

### Task 3.3: GitHub Actions freshness runner

**Files:**
- Create: `.github/workflows/freshen_site.yml`, `scripts/live/cloud_refresh.py`
- Test: `tests/test_cloud_refresh.py`

**Interfaces:**
- Workflow: cron every 10 min. Steps: checkout main, read published `data.js` `generated_at` — if < 10 min old, exit (Mac is handling it). Else run `cloud_refresh.py`: load `feed/predictions.json` from gh-pages, fetch current Kalshi prices (public endpoints via existing `kalshi_client` price path; auth optional secret `KALSHI_KEY`), recompute edge columns with `entry_rules` (same functions as live), rebuild `data.js` marked `"refreshed_by": "cloud"`, push to gh-pages. Never writes price history, paper entries, or main.
- `cloud_refresh.refresh(feed, price_fetcher, now) -> payload` pure core for tests.

**Steps:**
- [ ] Failing tests: `test_cloud_refresh_reprices_edges` (fake feed + fake prices → edge/watch recomputed via entry_rules), `test_stale_guard` (fresh generated_at → no-op), `test_no_history_writes`.
- [ ] Implement script + workflow; suite green.
- [ ] Push, then manually trigger the workflow (workflow_dispatch) and verify the public site updates. Confirm with user before adding any repo secret.
- [ ] Commit: `feat: cloud freshness runner keeps the site current while the Mac sleeps`.

---

## Phase 4 — Model (targeted, gated)

### Task 4.1: Entity + context features (leakage-safe)

**Files:**
- Modify: `ufc_mentions/kalshi_context_model.py`, `ufc_mentions/fighter_history_features.py`
- Test: extend `tests/test_fighter_history_features.py`

**Interfaces:**
- New per-row features, all computed from strictly earlier fights: `fighter_phrase_rate_prior` (per-fighter historical rate for the target phrase, shrunk to league), `event_tier` (PPV vs Fight Night from event_title), `year_bucket`, `location_home` (Kaggle location country == fighter country when available).
- Feature construction asserts `event_date < target_date` on every history row (hard leakage guard, mirroring existing pattern).

**Steps:**
- [ ] Failing tests: `test_fighter_phrase_rate_prior_uses_only_earlier_fights`, `test_event_tier_parsing`.
- [ ] Implement features behind a flag `feature_set="v2"` (v1 remains default until gated in 4.3).
- [ ] Suite green. Commit: `feat: leakage-safe entity/context features (v2, not yet default)`.

### Task 4.2: Calibration layer

**Files:**
- Modify: `ufc_mentions/kalshi_context_model.py`
- Test: new cases in `tests/test_kalshi_pricer.py`

**Interfaces:**
- Post-hoc recalibration fitted on chronological validation predictions (Platt with slope/intercept free, falling back to identity when validation rows < 200). Targets the known 40–60% overconfidence and >60% compression. Applied only in `feature_set="v2"`.

**Steps:**
- [ ] Failing test: `test_recalibration_expands_range` (synthetic compressed probs + labels → recalibrated spread wider, log loss lower).
- [ ] Implement; suite green. Commit: `feat: recalibration layer for v2 model`.

### Task 4.3: Head-to-head gate

**Files:**
- Modify: `scripts/model/backtest_context_model.py`, `scripts/model/walkforward_update.py`
- Test: extend `tests/test_walkforward.py`

**Interfaces:**
- Backtest runs v1 vs v2 on the identical chronological split + the walkforward held-out cards; writes `model_outputs/v2_gate_report.json` `{v1_log_loss, v2_log_loss, holdout_v1, holdout_v2, verdict}`.
- v2 becomes default ONLY if it wins both overall and holdout mean log loss; otherwise config stays v1 and the report says why. Config lives in `data/processed/model_update_config.json` (`feature_set` key beside `label_weight`).

**Steps:**
- [ ] Failing test: `test_gate_keeps_v1_when_v2_worse`, `test_gate_adopts_v2_when_better`.
- [ ] Implement, run the real comparison, apply the verdict honestly (either outcome is a success).
- [ ] Suite green. Commit: `feat: gated v1-vs-v2 model comparison; adopt winner`.

---

## Final

- [ ] Full suite + browser walkthrough of every tab and a fight page; screenshot set.
- [ ] Republish site; verify public URL renders the new UI.
- [ ] Update memory file with outcomes (photos coverage %, v2 gate verdict, new architecture notes).
- [ ] Push to origin (user has standing expectation of pushed work on this project).
