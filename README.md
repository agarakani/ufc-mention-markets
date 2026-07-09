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

Kalshi prices are not fed into the model. They are only used after the model has
made its number.

## How To Use It

Install dependencies:

```bash
pip install -r requirements.txt
```

Easiest live mode on this Mac:

```bash
./start_live_dashboard.command
```

That starts a local read-only dashboard server, opens the browser, refreshes
once, then keeps checking Kalshi every 30 seconds. Leave that terminal window
open while using the dashboard. The page updates itself, and `Update now`
forces an immediate refresh.

To let it paper-track entries while it refreshes:

```bash
PAPER_CARD="UFC July 11 card" ./start_live_dashboard.command
```

That still cannot spend real money. It records one fake contract the first time
a market becomes `WATCH YES` or `WATCH NO`, using the live buy price at that
moment. It also keeps checking Kalshi for final results, fills outcomes when
Kalshi resolves a market, and recalculates paper P/L.

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

## Testing The Model On A Fight Card

The point of a live card is to find out whether the model's numbers hold up.
The steps, using the July 11 card as the example:

1. Sometime before the fights, start the dashboard with paper tracking on:

```bash
PAPER_CARD="UFC July 11 card" ./start_live_dashboard.command
```

2. Leave it running through the card. Every watch row gets logged as one
   pretend contract at the live price. Leans are logged separately. Nothing
   is bought for real.

3. Look around while it runs. Click fights in the left list, click any row to
   see exactly how its number was made, and check that the reasons make sense.

4. After Kalshi posts results (usually within a day), the tracker fills in
   yes/no outcomes and paper P/L by itself. Then fold the settled card into
   the money backtest:

```bash
python3 scripts/model/backtest_pl.py
```

The Model health section updates with the new settled trades. Judge the model
on that growing sample, not on any single fight.

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
- `WATCH YES` / `WATCH NO`: research flag only. It means that side cleared the current checks.
- `WATCH YES DATA` / `WATCH NO DATA`: same idea, but fighter history was thin, so the row had to clear a higher bar.
- `LOW DATA`: the model ran, but there is not enough matching fighter history to trust it as a watch row.
- `PASS`: no edge worth flagging right now.
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

2. Money backtest — would the watch rule have made paper money?

```bash
python3 scripts/model/backtest_pl.py
```

This replays the price snapshots the live refresher already saved, enters one
paper contract at the first snapshot where the live rule said WATCH, then
settles against the final Kalshi results (fetched read-only and cached).
No hindsight prices, no fabricated fills.

Latest result: from the one resolved card so far, the watch rule went 2 for 22
and lost $2.25 of paper money; the looser leans went 27 for 51 and made $2.89.
That is far below the 30 settled trades needed before the number means
anything, and it is not evidence of an edge either way. Both results show up
in the dashboard's Model health section.

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
