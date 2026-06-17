# ufc-mention-markets

Research tools for UFC prediction markets that resolve on whether a phrase is
said during the broadcast.

The main distinction is that a mention market is literal. A market on
`knockout` is different from a market on `KO`, `TKO`, or `knocked out`. The code
keeps those terms separate.

## Data

This repo expects two local datasets:

- `ufc_cleaned_export/`: gzip-compressed transcript JSON files, one per fight
- `kaggle_data/ultimate_ufc_dataset/`: Kaggle's `mdabbert/ultimate-ufc-dataset`

Both folders are gitignored. Generated CSVs and model outputs are also ignored.

## Workflow

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Build strict phrase labels from the transcripts:

```bash
python3 build_match_csv.py
```

Join transcript labels to Kaggle fight data:

```bash
python3 join_kaggle_outcomes.py
```

Run the first outcome/mention checks:

```bash
python3 analyze_outcome_mentions.py
```

Train baseline models:

```bash
python train_baseline_models.py
```

Predict phrase probabilities for an upcoming card:

```bash
python predict_upcoming_mentions.py
```

Search and classify real market candidates:

```bash
python3 search_oddpool_markets.py --q "UFC mention" --exchange polymarket
python3 classify_market_candidates.py market_data/oddpool_*.csv
```

Build an edge table once a market has been mapped and prices have been pulled:

```bash
python3 fetch_oddpool_top_of_book.py --markets market_data/market_mappings.csv
python3 build_edge_table.py --profile prefight_odds
```

## Phrase Targets

The phrase list lives in `market_phrases.txt`. Each phrase becomes a strict
True/False label, using exact-term matching plus plural/possessive forms.

Examples:

```text
submission
guillotine
choke
triangle
eye poke
championship
```

When real markets list a new phrase, add it to `market_phrases.txt` and rebuild
the labels/models.

## Current Dataset

The current joined dataset has:

- 5,578 valid transcript fights
- 4,469 fights matched to Kaggle rows
- 0 ambiguous matches

The join key is unordered fighter last-name pair plus event date.

## Current Model Notes

The baseline model uses pre-fight features only: fighter stats, event context,
odds, and historical performance fields. It excludes transcript text, fight
duration, winner, finish type, finish round/time, and any post-fight fields.

The strongest first-pass targets are:

| phrase | AUC | test Yes rate | top-decile Yes rate |
|---|---:|---:|---:|
| `championship` | 0.783 | 12.2% | 50.0% |
| `choke` | 0.684 | 30.5% | 54.5% |
| `submission` | 0.663 | 46.2% | 70.9% |
| `triangle` | 0.655 | 30.3% | 48.2% |
| `guillotine` | 0.629 | 22.6% | 36.4% |

These are baselines, not trade recommendations.

## Market Prices

The model estimates probabilities. Market prices come from Oddpool/Polymarket/
Kalshi data.

The edge calculation is:

```text
edge_to_yes_ask = model_probability - real_yes_ask
```

If a real ask price is missing, no edge is calculated.

Most announcer markets are event-level, so fight-level probabilities are
aggregated with:

```text
P(any fight mentions phrase) = 1 - product(1 - per_fight_probability)
```

See `MARKET_INTEGRATION.md` for the market-data workflow.
