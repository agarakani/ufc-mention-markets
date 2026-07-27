# UFC Mention Markets

**Prices the words, not the fight.**

Kalshi runs markets on what the commentators will *say* during a UFC fight —
"choke", "knockout", "Dana" — and this prices them. A model trained on 5,578
fight transcripts estimates how likely each exact phrase is to be said during
each listed fight, compares that with the live bid and ask, and flags the gap.

Every signal is paper-traded and settled against Kalshi's own results, so the
record is public and honest.

**Live board:** https://agarakani.github.io/ufc-mention-markets/

> Research tooling. It reads Kalshi and cannot place an order — the client has
> no write path at all.

---

## Where it stands

Four settled cards, replayed from recorded live snapshots against final Kalshi
results. No hindsight prices, no fabricated fills.

| | trades | wins | P/L | return |
|---|---|---|---|---|
| Watch calls | 134 | 80 | +$9.33 | +13.2% |
| Leans (below the bar) | 228 | 124 | −$3.07 | −2.4% |

**Read that carefully.** Three of the four cards lost money; the entire profit
came from one night (Jul 11, +$13.24). Trades inside a card move together, so
four cards is the real sample size, not 134 trades. This is not a proven edge.

The model does beat guessing — 0.502 log loss against 0.595 for the base rate
on the most recent card — but the market beat the model on that same card
(0.129). Prices here still carry more information than the model does.

---

## How a number gets made

1. **Find the markets.** Every open Kalshi UFC mention market, with its exact
   resolution rules, including grouped phrases like `Choke / Choked / Chokehold`.
2. **Price the phrase for that fight.** A model trained per phrase group on
   historical transcripts, using pre-fight information only — records, reach,
   stance, style, era, card tier.
3. **Compare with the book.** Model YES against the live YES ask, model NO
   against the NO ask.
4. **Call it.** `WATCH` when a side clears the edge bar, `LEAN` when it is
   positive but short of it, `PASS` otherwise.

Kalshi prices never enter the model. They are used only after the number exists.

### What the rule refuses to do

Three guardrails, each added after losing money without it:

- **Edge cap (0.15).** On settled cards, disagreements larger than 15 points
  were almost always the model's mistake. Those are marked `BIG GAP` and never
  traded.
- **Phrase trust.** Groups that showed no real skill in the historical
  prediction test can lean, never watch.
- **Thin-data bar.** When a fighter's history is sparse, the row must clear a
  larger edge and is flagged.

---

## The model improves itself

Every settled Kalshi market is ground truth for exactly what the model predicts:
was this phrase said in this fight, yes or no. Those answers are collected
automatically after each card into `data/processed/kalshi_results_labels.csv`.

A walk-forward gate re-runs whenever a settled card is missing from it. Each
candidate is scored on cards it has never seen, and any correction is fitted
only on cards *before* the one being scored:

| candidate | what it changes |
|---|---|
| `v1` / `v2` | feature set — v2 adds event tier |
| `+calib` | one global recalibration fitted on settled results |
| `+group` | a per-phrase-group shift, shrunk by that group's own sample size |

**A candidate ships only if it beats plain v1 on held-out cards.** The gate has
already reversed itself once: it adopted a global calibration in July, then
dropped it a week later when a third held-out card showed it was pushing every
prediction too low. That reversal is the system working, not a bug.

The current verdict lives in `model_outputs/walkforward_report.json`; the live
model reads `data/processed/model_update_config.json`.

---

## Using it

The dashboard runs as a background service. There is nothing to start.

- **Desktop:** double-click **UFC Dashboard**
- **Browser:** http://127.0.0.1:8765
- **Anywhere else:** https://agarakani.github.io/ufc-mention-markets/

It refreshes prices every 30 seconds, paper-trades new watch rows at the live
price, fills in outcomes when Kalshi posts them, folds finished cards into the
money record, and republishes the public site. It starts itself at login.

On a new machine:

```bash
pip install -r requirements.txt
./install_autostart.command
```

Stop the service, or stop publishing:

```bash
./uninstall_autostart.command
UFC_PUBLISH=0 ./install_autostart.command
```

One honest limit: the public site is only as fresh as this Mac. Asleep or
offline, the page stays up showing its last snapshot, timestamped in the corner.

---

## Reading the board

**The stage** names the card, counts down to first bell, and shows the best edge
on it.

**The card** gives each fight a tile: its market count, its best edge, and the
phrase driving it.

**The disagreement grid** is the whole card at once — fights down, phrases
across, each cell coloured by how far the model sits from the market. Green
means we say more likely, red means less.

**The book** is the detail. Each row draws one market on a shared logit price
axis: brackets at the bid and the ask, the untraded space between them, and a
white mark for the model's number. Logit rather than linear, because these
markets live at 3–12¢ and 88–97¢ where a linear bar shows nothing.

Click any row for a plain-English account of how that number was made.

---

## Commands

All optional — the service does every one of these on its own.

```bash
python3 scripts/live/refresh_dashboard.py                  # one refresh
python3 scripts/live/price_fight.py --event-ticker <TICKER> --show-all
python3 scripts/model/backtest_pl.py                       # money record
python3 scripts/model/backtest_context_model.py            # model on old fights
python3 scripts/model/walkforward_update.py                # re-run the gate
python3 scripts/data/build_match_csv.py                    # rebuild training data
```

## Layout

```text
dashboard/           the board: index.html, app.js, styles.css, generated data.js
ufc_mentions/        the library — model, Kalshi client, phrase matching, corpus
scripts/live/        refresh prices, serve the board, publish the public site
scripts/model/       backtests, the walk-forward gate, rule audits
scripts/data/        rebuild training tables from transcripts and stats
scripts/tracking/    paper card snapshots and settlement
tests/               the test suite
market_phrases.txt   phrase list used when rebuilding training data
```

Datasets and generated files are gitignored: `ufc_cleaned_export/`,
`kaggle_data/`, `data/processed/`, `market_data/`, `model_outputs/`.

## Credentials

Public Kalshi reads work unauthenticated. For authenticated reads, put a
read-only key in a gitignored `.env`:

```text
KALSHI_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=/absolute/path/to/private-key.pem
```

There is no order-placement code path, authenticated or otherwise.
