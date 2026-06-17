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
