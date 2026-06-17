# Market Price Integration

The model does **not** create odds. It estimates probabilities:

```text
P(literal phrase appears in the transcript)
```

Market APIs provide prices:

```text
real YES bid / ask / mid
```

The bettor-facing layer compares the two:

```text
edge_to_yes_ask = model_probability - real_yes_ask
```

If a real `yes_ask` is missing, the edge stays blank. The project should never make
up prices.

## Where Each Piece Fits

1. `train_baseline_models.py`
   - Trains probability models from historical fights.
   - Produces `model_outputs/baseline_predictions.csv`.

2. `search_oddpool_markets.py`
   - Searches Oddpool for real Polymarket/Kalshi markets.
   - Produces `market_data/oddpool_markets.csv`.

3. `market_data/market_mappings.csv`
   - Human-reviewed mapping from a market question to:
     - fight/transcript id
     - literal phrase target
     - exchange / market id / token id
   - Use `market_mappings.example.csv` as the template.

4. `fetch_oddpool_top_of_book.py`
   - Pulls real historical bid/ask/mid snapshots from Oddpool.
   - Produces `market_data/oddpool_top_of_book.csv`.

5. `build_edge_table.py`
   - Joins model probabilities to real quotes.
   - Produces `market_data/edge_table.csv`.

## Oddpool Setup

Create an Oddpool API key from the Oddpool dashboard, then run:

```bash
export ODDPOOL_API_KEY='oddpool_...'
```

Or keep it in a local ignored `.env` file:

```bash
cp .env.example .env
# edit .env and replace oddpool_your_api_key_here
```

Oddpool uses the `X-API-Key` header. Search and historical data are listed as free
in the public docs as of this project setup.

## Search Real Markets

Examples:

```bash
python3 search_oddpool_markets.py \
  --q "UFC mention" \
  --exchange polymarket \
  --status active
```

```bash
python3 search_oddpool_markets.py \
  --q "submission mentioned" \
  --exchange kalshi \
  --status closed \
  --sort-by volume
```

Review `market_data/oddpool_markets.csv`, then copy real markets into
`market_data/market_mappings.csv`.

## Mapping Markets

Mapping is intentionally manual/reviewed because a bad market-to-fight match creates
fake edge.

Required columns:

```text
transcript_id,event_date,fighter_1,fighter_2,phrase,exchange,market_id,asset_id,token_side,question,price_start_iso,price_end_iso,notes
```

Notes:

- `phrase` must be one of the strict targets: `submission`, `knockout`, `TKO`,
  `knocked out`, `split decision`, `unanimous decision`, or `doctor`.
- For Kalshi, `market_id` is the market ticker. `asset_id` can be blank.
- For Polymarket, `market_id` is the condition id. To compute a YES price, provide
  the YES token `asset_id` and set `token_side=YES`.
- `price_start_iso` and `price_end_iso` should cover the pre-event window you want
  to evaluate, such as the hour before the fight/card starts.

## Fetch Real Top-Of-Book Prices

Using the mapping file:

```bash
python3 fetch_oddpool_top_of_book.py \
  --markets market_data/market_mappings.csv \
  --granularity 5m
```

Direct one-off fetch:

```bash
python3 fetch_oddpool_top_of_book.py \
  --exchange kalshi \
  --market-id KXEXAMPLE-26JAN01-Y \
  --start 2026-01-01T00:00:00Z \
  --end 2026-01-01T01:00:00Z
```

## Build The Edge Table

```bash
python3 build_edge_table.py --profile prefight_odds
```

The output uses real `yes_ask` only:

```text
edge_to_yes_ask = model_probability - yes_ask
```

For example, if the model says 0.64 and the real YES ask is 0.52, the edge is
0.12. If there is no real ask, the edge is blank.

## Where Justin's Repo Helps

Justin's NFL project is useful for the market-data side, not because it changes the
UFC model. We want to learn:

- how he discovers mention markets
- how he maps market questions to games
- whether he uses pre-event ask, bid, mid, or trade history
- how he chooses the timestamp before event start
- how he backtests edge

Do not copy private code into this repo. Use it as a reference for design choices,
then keep this implementation independent.
