# ufc-mention-markets

Read-only tools for UFC Kalshi mention markets.

The goal is simple: for each listed fight, look at the exact phrase Kalshi is
offering, estimate how likely that phrase is to be said during that fight, then
compare that number with the live YES ask.

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

That refreshes once, opens `dashboard/index.html`, then keeps checking Kalshi
every 30 seconds. Leave that terminal window open while using the dashboard.

Refresh the live dashboard once:

```bash
python3 scripts/live/refresh_dashboard.py
```

Open:

```text
dashboard/index.html
```

Keep it updating:

```bash
python3 scripts/live/refresh_dashboard.py --poll-seconds 30
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

## How To Read The Dashboard

- `Our %`: the fight-level model's YES probability for that phrase.
- `YES price`: what buying YES currently costs.
- `NO price`: what buying NO currently costs.
- `Side`: the cheaper side according to our model.
- `Edge`: model chance for that side minus that side's buy price.
- `WATCH YES` / `WATCH NO`: research flag only. It means that side cleared the current checks.
- `WATCH YES DATA` / `WATCH NO DATA`: same idea, but fighter history was thin, so the row had to clear a higher bar.
- `LOW DATA`: the model ran, but there is not enough matching fighter history to trust it as a watch row.
- `PASS`: no edge worth flagging right now.

## Backtesting

Run the exact fight-level model backtest:

```bash
python3 scripts/model/backtest_context_model.py --initial-train-frac 0.30
```

Latest checked result:

- 15 current Kalshi phrase groups tested
- 50,520 old fight predictions
- 14 of 15 phrase groups scored better than the simple old average

That checks whether the model makes better guesses than a simple baseline. It
is not a profit backtest yet; we still need more resolved Kalshi markets before
claiming a trade-ready edge.

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
- `scripts/live/price_fight.py`: prices one fight.
- `scripts/model/backtest_context_model.py`: checks the fight-level model on old fights.
- `scripts/model/audit_grouped_rules.py`: checks grouped Kalshi phrases against transcripts.
- `scripts/data/build_match_csv.py`: rebuilds `fight_mentions.csv` from transcripts.
- `scripts/data/join_kaggle_outcomes.py`: joins transcript rows with UFC stats.
- `scripts/tracking/snapshot_card.py`: saves the current board before a card starts.
- `scripts/tracking/settle_card.py`: calculates paper P/L after results are filled in.

## Weekly Tracking

Before a card starts:

```bash
python3 scripts/live/refresh_dashboard.py
python3 scripts/tracking/snapshot_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
```

After the card, fill `data/tracking/<card>/outcomes.csv` with `yes` or `no`,
then run:

```bash
python3 scripts/tracking/settle_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
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
