# Market Integration

This project separates probability estimates from market prices.

- The model estimates `P(phrase is said)`.
- Oddpool/Polymarket/Kalshi provide the market price.
- The edge table compares the two.

No market price is inferred by the model.

## Setup

Create an Oddpool API key and store it locally:

```bash
cp .env.example .env
```

Then edit `.env`:

```text
ODDPOOL_API_KEY=...
```

`.env` is gitignored.

## Market Search

Search for candidate markets:

```bash
python3 search_oddpool_markets.py \
  --q "UFC mention" \
  --exchange polymarket \
  --status active
```

Classify the results:

```bash
python3 classify_market_candidates.py market_data/oddpool_*.csv \
  --out market_data/classified_markets.csv
```

The classifier separates:

- `mention_announcers`
- `mention_unrelated_speaker`
- `fight_outcome_submission`
- `other`

It also flags market structure:

- `simple_binary`: phrase appears at least once
- `threshold`: phrase must appear N+ times
- `or`: multiple phrases can satisfy the market
- `or_threshold`: both complications

The current model is for `simple_binary` markets.

## Phrase List

If a useful market phrase is found, add it to:

```text
market_phrases.txt
```

Then rebuild:

```bash
python3 build_match_csv.py
python3 join_kaggle_outcomes.py
python train_baseline_models.py
```

## Upcoming Cards

For event-level markets such as:

```text
Will the announcers say "Guillotine" during UFC 250?
```

run:

```bash
python predict_upcoming_mentions.py
```

This writes:

```text
model_outputs/upcoming_fight_predictions.csv
model_outputs/upcoming_event_predictions.csv
```

## Prices and Edge

After mapping a real market in `market_data/market_mappings.csv`, fetch quotes:

```csv
scope,transcript_id,event_date,location,fighter_1,fighter_2,phrase,exchange,market_id,asset_id,token_side,question,price_start_iso,price_end_iso,notes
fight,upcoming_2026_04_04_renato_moicano_vs_chris_duncan,2026-04-04,"Las Vegas, Nevada, USA",Renato Moicano,Chris Duncan,guillotine,polymarket,0x...,YES_TOKEN_ID,YES,"Will announcers say Guillotine during Moicano vs Duncan?",,,
event,,2026-04-04,"Las Vegas, Nevada, USA",,,guillotine,polymarket,0x...,YES_TOKEN_ID,YES,"Will announcers say Guillotine during the UFC event?",,,
```

Use:

- `scope=fight` for fight-specific markets
- `scope=event` for card/event-wide markets

Then fetch quotes:

```bash
python3 fetch_oddpool_top_of_book.py \
  --markets market_data/market_mappings.csv
```

Then build the edge table:

```bash
python3 build_edge_table.py --profile prefight_odds
```

For a YES position:

```text
edge_to_yes_ask = model_probability - yes_ask
```

Rows without a real `yes_ask` are left blank.

## Historical Backtest

The historical workflow uses separate authoritative sources:

- Polymarket supplies YES/NO token IDs, event time, and official resolution.
- Oddpool supplies timestamped historical asks for each token.
- The UFC model is refit using only fights before each market's event date.

Run the complete workflow with the Python environment that has the project
requirements installed:

```bash
python3 refresh_historical_backtest.py
```

Or run each audit stage separately:

```bash
python3 fetch_polymarket_metadata.py
python3 build_historical_market_ledger.py
python3 predict_historical_markets.py
python3 fetch_oddpool_top_of_book.py \
  --markets market_data/historical_market_ledger.csv \
  --out market_data/historical_top_of_book.csv \
  --pages 100
python3 backtest_historical_markets.py
```

The backtest uses the latest real ask no more than 30 minutes old at a cutoff
60 minutes before the event. It does not substitute midpoint, last trade, or a
derived complementary price. Fee and slippage assumptions are explicit CLI
arguments. Results remain labeled `insufficient_sample` until at least 30 trades
qualify.
