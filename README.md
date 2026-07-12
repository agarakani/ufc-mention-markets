# ufc-mention-markets

Read-only tools for UFC Kalshi mention markets.

The goal is simple: for each listed fight, look at the exact phrase Kalshi is
offering, estimate how likely that phrase is to be said during that fight, then
compare that number with the live YES and NO buy prices.

This repo does not place trades.

## What The App Does

1. Finds open Kalshi UFC mention markets.
2. Reads the exact phrase rules, including grouped phrases like `Choke / Choked / Chokehold`.
3. Builds a fight-level probability for that exact phrase and that exact fight.
4. Compares the model's YES chance with the live YES buy price, and the model's NO chance with the live NO buy price.
5. Marks a row `WATCH YES` or `WATCH NO` when that side clears the required edge.
6. If fighter history is thin, the row can still be a watch, but it has to clear a bigger edge bar and is flagged as data-risk.
7. Refuses to watch when the edge is too big. On settled cards, disagreements
   with the market over 15 points were almost always the model's mistake, so
   those rows are flagged `BIG GAP` and never paper-traded.
8. Refuses to watch phrase groups that show no real skill in the old-fight
   prediction test. Those can lean, nothing more.

Kalshi prices are not fed into the model. They are only used after the model has
made its number.

## How To Use It

The dashboard runs as a background service on this Mac — nothing to start,
no terminal. Open it like a website:

- Double-click **UFC Dashboard** on the Desktop, or
- go to **http://127.0.0.1:8765** in any browser.

It refreshes Kalshi prices every 30 seconds on its own, paper-tracks every
card automatically (one pretend contract per new WATCH row — it cannot spend
real money), fills in outcomes when Kalshi posts results, and folds finished
cards into the money backtest. It starts by itself when the Mac starts.

Set it up once (already done on this machine), or after moving to a new Mac:

```bash
pip install -r requirements.txt
./install_autostart.command
```

To turn the background service off:

```bash
./uninstall_autostart.command
```

If you prefer running it by hand in a terminal instead, the old way still
works (with optional PAPER_CARD="auto" or a custom card name):

```bash
./start_live_dashboard.command
```

Refresh the live dashboard once:

```bash
python3 scripts/live/refresh_dashboard.py
```

Open:

```text
http://127.0.0.1:8765/
```

Keep it updating:

```bash
python3 scripts/live/refresh_dashboard.py --poll-seconds 30
```

Keep it updating and paper-track live entries:

```bash
python3 scripts/live/refresh_dashboard.py \
  --poll-seconds 30 \
  --paper-card "UFC July 11 card"
```

Price one listed fight by event ticker:

```bash
python3 scripts/live/price_fight.py \
  --event-ticker KXFIGHTMENTION-26JUN20KAPHOR \
  --show-all
```

Or find the fight by names/date:

```bash
python3 scripts/live/price_fight.py \
  --fighter-1 "Manel Kape" \
  --fighter-2 "Kyoji Horiguchi" \
  --date 2026-06-20 \
  --show-all
```

## Sharing The Site

The dashboard also publishes as a public website:

  https://agarakani.github.io/ufc-mention-markets/

That page is a read-only mirror anyone can open — no setup, no Mac required
on their end. This machine's background service pushes a fresh snapshot every
few minutes while it runs, and the page re-reads the data by itself. The
public copy has no refresh button and, like everything else here, cannot
place trades.

Sharing is on by default. Turn it off (or back on) by reinstalling the
service:

```bash
UFC_PUBLISH=0 ./install_autostart.command   # stop publishing
UFC_PUBLISH=1 ./install_autostart.command   # start again
```

One honest limit: the public page is only as fresh as this Mac. If the Mac
is asleep or offline, the site stays up but shows the last published
snapshot, with its timestamp in the corner.

## Testing The Model On A Fight Card

The point of a live card is to find out whether the model's numbers hold up.
Since the dashboard runs by itself and paper tracking is automatic, there is
nothing to start. On fight weekend:

1. Open the dashboard (Desktop shortcut or http://127.0.0.1:8765) any time
   before or during the card. Every watch row is already being logged as one
   pretend contract at the live price; leans are logged separately. Nothing
   is bought for real.

2. Look around. Click fights in the left list, click any row to see exactly
   how its number was made, and check that the reasons make sense.

3. After Kalshi posts results (usually within a day), everything settles by
   itself: the tracker fills in yes/no outcomes and paper P/L, and the money
   backtest folds the finished card in and updates Model health. There is
   nothing to run by hand.

Judge the model on that growing settled sample, not on any single fight.

## How To Read The Dashboard

- Cards are grouped by the fight-event date Kalshi publishes. If Kalshi has not
  published a card name, the dashboard does not guess one.
- Click a card folder to see the fights Kalshi has listed for that date.
- Click a fight to see only that fight's mention-market prices.
- `TBD odds` means Kalshi has listed the fight event, but no tradable mention
  odds are available yet.
- `Our %`: the fight-level model's YES probability for that phrase.
- `YES price`: what buying YES currently costs.
- `NO price`: what buying NO currently costs.
- `Side`: the cheaper side according to our model.
- `Edge`: model chance for that side minus that side's buy price.
- `WATCH YES` / `WATCH NO`: research flag only. That side's edge cleared the
  entry bar (spread + fee buffer, plus an extra buffer when data is thin).
- `LEAN YES` / `LEAN NO`: positive edge, but under the entry bar — or a phrase
  group the prediction test does not trust enough to watch.
- `BIG GAP`: the edge is over the 15% cap. A disagreement that large was
  almost always the model's mistake on settled cards, so it is flagged, not
  traded.
- `PASS`: no positive edge on either side.
- `NO PRICES`: Kalshi has not posted a live YES/NO book yet.
- `NO MODEL`: no fight-level model number; the row shows a rough history
  average and can never become a watch.
- A dashed `thin data` tag next to the call means fighter history is small.
  Those rows must clear a higher bar, and a very large edge on a thin-data row
  is more likely a model gap than free money.
- Click any price row to expand "How this number was made": which model produced
  the number, what it trained on, the fighter history behind it, the prices it
  compared against, and the exact entry bar it had to clear.
- The "Model health" section shows the old-fight prediction backtest (rows
  tested, phrase groups that beat the simple baseline, weakest phrase) and the
  money-backtest status. It says clearly when there are not enough settled
  trades to claim anything about profit.

## Backtesting

There are two checks, and they answer different questions.

1. Prediction quality — does the model guess better than a simple average?

```bash
python3 scripts/model/backtest_context_model.py --initial-train-frac 0.30
```

Latest result: 13 current Kalshi phrase groups, 43,784 old fight predictions,
12 of 13 groups beat the simple baseline. This says nothing about profit.
The same run grades each phrase group; groups that fail it, or show almost no
ranking skill (AUC under 0.55), are barred from producing watch rows.

2. Money backtest — would the watch rule have made paper money?

```bash
python3 scripts/model/backtest_pl.py
```

This replays the price snapshots the live refresher already saved, enters one
paper contract at the first snapshot where the live rule said WATCH, then
settles against the final Kalshi results (fetched read-only and cached).
No hindsight prices, no fabricated fills.

Latest result, two settled cards in: 97 recorded trades, 60 wins, +$10.99 on
$49.01 staked. Today's tightened rule (edge cap + phrase trust) replayed on
the same snapshots takes 54 trades, 39 wins, +$7.15. The 30-trade minimum is
met, so the dashboard now says "enough sample to review" — but two cards is
still a small number of independent events, and the first card lost money
before the second one won more back. Judge it card by card as the sample
grows. Both results show up in the dashboard's Model health section.

## Learning From Settled Cards

Every settled Kalshi mention market is a ground-truth answer to exactly what
the model predicts: was this phrase group said during this fight. The
refresher collects those answers automatically after each card and writes
them to `data/processed/kalshi_results_labels.csv` (one row per settled
market: date, fighters, phrase group, yes/no).

This matters because the transcript corpus stops in the past, while these
labels cover live cards and current broadcast teams. Retraining the model on
them is the planned next step; today they are collected and reported but do
not change live predictions yet. Broadcast transcripts themselves cannot be
downloaded automatically (they are licensed recordings), so this is the
honest automated path.

## Project Layout

```text
.
├── dashboard/          local browser dashboard
├── data/processed/     generated CSVs, kept out of git
├── scripts/
│   ├── live/           refresh Kalshi prices and price one fight
│   ├── model/          backtests and phrase-rule checks
│   ├── data/           rebuild the training tables
│   └── tracking/       weekly paper P/L tracker
├── tracking/           how to track weekly results
├── ufc_mentions/       reusable model, Kalshi, phrase, and transcript code
├── tests/              focused checks for the current Kalshi flow
├── market_phrases.txt  phrase list used when rebuilding training data
└── start_live_dashboard.command
```

The main commands live in `scripts/`:

- `scripts/live/refresh_dashboard.py`: refreshes all open Kalshi UFC fight markets.
- `scripts/live/dashboard_server.py`: serves the dashboard and keeps it auto-updating.
- `scripts/live/price_fight.py`: prices one fight.
- `scripts/model/backtest_context_model.py`: checks the fight-level model on old fights.
- `scripts/model/backtest_pl.py`: replays saved snapshots against final results for paper P/L.
- `scripts/model/audit_grouped_rules.py`: checks grouped Kalshi phrases against transcripts.
- `scripts/data/build_match_csv.py`: rebuilds `fight_mentions.csv` from transcripts.
- `scripts/data/join_kaggle_outcomes.py`: joins transcript rows with UFC stats.
- `scripts/tracking/snapshot_card.py`: saves the current board before a card starts.
- `scripts/tracking/live_paper.py`: records live paper entries when WATCH rows appear.
- `scripts/tracking/settle_card.py`: calculates paper P/L after results are filled in.

## Weekly Tracking

Before a card starts:

```bash
python3 scripts/live/refresh_dashboard.py
python3 scripts/tracking/snapshot_card.py --card "UFC July 11 card"
```

For live paper entries instead, leave this running before the fights:

```bash
python3 scripts/live/refresh_dashboard.py \
  --poll-seconds 30 \
  --paper-card "UFC July 11 card"
```

The live tracker buys nothing for real. It logs one paper contract when a row
first becomes `WATCH`, then ignores that same market on later refreshes.

When Kalshi posts a final result, the tracker fills `yes` or `no` on its own.
Rows show as `pending` when the fight date has passed but Kalshi has not posted
the final result yet.

The settlement command is still available if you need to recalculate manually:

```bash
python3 scripts/tracking/settle_card.py --card "UFC July 11 card"
```

This tracks two numbers:

- `official`: only rows the model marked `WATCH`.
- `leans`: rows where either YES or NO had positive model edge but did not clear the full watch bar.

## Data

Local data folders are gitignored:

- `ufc_cleaned_export/`: fight transcript JSON files
- `kaggle_data/ultimate_ufc_dataset/`: Kaggle UFC stats
- `data/processed/`: generated CSVs used by the model
- `data/tracking/`: generated weekly paper-trading files
- `market_data/`: live Kalshi snapshots and price history
- `model_outputs/`: model and backtest outputs

## Limits

The Kalshi client supports GET requests only. There is no order-placement method.

Public Kalshi reads currently work without credentials. If authenticated reads
are needed, put a read-only key in a gitignored `.env`:

```text
KALSHI_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=/absolute/path/to/private-key.pem
```

Do not claim the model is trade-ready until there are enough resolved Kalshi cards in paper tracking.
