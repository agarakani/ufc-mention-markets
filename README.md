# ufc-mention-markets

Research pipeline for UFC prediction markets that resolve on whether exact phrases
are mentioned in fight commentary.

The core idea is that a mention market is not the same thing as a fight-outcome
market. For example, a real market on the literal word `knockout` should not count
`KO`, `TKO`, or `knocked out`. This repo keeps those two concepts separate:

- **Strict market resolution:** exact literal phrase plus plural/possessive forms
  only.
- **Broad commentary patterns:** synonym groups, useful for understanding language
  but not for settling a real market.

## Data

Raw transcript data lives locally in `ufc_cleaned_export/`: 5,581 gzip-compressed
JSON files, one per fight, named by matchup
(for example, `AJ_Dobson_vs_Jacob_Malkoun_UFC_271.json.gz`).

That folder is **git-ignored** and is not part of the public repo.

Outcome data comes from Kaggle's `mdabbert/ultimate-ufc-dataset` dataset. It is also
kept out of the repo under `kaggle_data/`.

Ignored local outputs:

- `ufc_cleaned_export/`
- `kaggle_data/`
- `fight_mentions.csv`
- `joined_fights.csv`

## Pipeline

Build strict per-fight mention features:

```bash
python3 build_match_csv.py
```

Download the Kaggle outcome data locally:

```bash
kaggle datasets download mdabbert/ultimate-ufc-dataset \
  -p kaggle_data/ultimate_ufc_dataset \
  --unzip
```

Join transcript features to fight outcomes:

```bash
python3 join_kaggle_outcomes.py
```

Run the first outcome-vs-mention sanity report:

```bash
python3 analyze_outcome_mentions.py
```

Train leakage-safe baseline models:

```bash
/Users/aryog/anaconda3/bin/python train_baseline_models.py
```

Verify the strict market matcher:

```bash
python3 mention_counts.py --selftest
```

## Current Join Quality

Using unordered fighter last-name pair plus event date:

- Transcript fights: 5,578
- Exact Kaggle matches: 4,469 (80.1%)
- Ambiguous matches: 0
- Unmatched: 1,109 (19.9%)

This is intentionally conservative. The unmatched set appears to be mostly Kaggle
coverage gaps or name/date mismatches, not duplicate-match ambiguity.

## First Signal Check

On the 4,469 matched fights:

| strict phrase | phrase Yes rate | target outcome | P(phrase \| target) | P(target \| phrase) |
|---|---:|---|---:|---:|
| `knockout` | 34.2% | KO/TKO | 40.9% | 37.4% |
| `TKO` | 8.1% | KO/TKO | 15.5% | 59.8% |
| `knocked out` | 9.3% | KO/TKO | 8.7% | 29.3% |
| `submission` | 49.9% | SUB | 71.3% | 26.0% |
| `split decision` | 3.6% | S-DEC | 16.9% | 44.7% |
| `unanimous decision` | 8.3% | U-DEC | 20.2% | 93.3% |
| `doctor` | 5.2% | n/a | n/a | n/a |

Early interpretation:

- `unanimous decision` is highly precise when it appears: 93.3% of mentions come
  from actual U-DEC fights.
- `submission` appears in many non-submission fights because commentary talks about
  submission attempts, threats, and defense.
- `knockout`, `TKO`, and `knocked out` are separate literal markets and have very
  different base rates.
- `doctor` is useful as a standalone mention market, but this Kaggle file does not
  expose a clean current-fight doctor-stoppage outcome field.

## Baseline Modeling Status

`train_baseline_models.py` trains one calibrated logistic-regression baseline per
strict phrase target. It uses a chronological split:

- Train: 3,377 older matched fights
- Test: 1,092 later matched fights
- First test date: 2023-02-18

To avoid leakage, the model excludes transcript text, transcript duration, actual
winner, actual finish, finish round/time, and fight duration. It compares two
feature profiles:

- `stats_only`: pre-fight fighter/event stats, no betting odds
- `prefight_odds`: `stats_only` plus pre-fight moneyline/method odds from Kaggle

Current holdout results are promising but uneven:

| target phrase | best profile | AUC | test Yes rate | top-decile actual Yes rate | log-loss improvement vs base rate |
|---|---|---:|---:|---:|---:|
| `submission` | `prefight_odds` | 0.663 | 46.2% | 70.9% | +0.0425 |
| `knockout` | `prefight_odds` | 0.575 | 29.4% | 35.5% | +0.0125 |
| `knocked out` | `stats_only` | 0.596 | 9.2% | 13.6% | +0.0031 |
| `split decision` | `stats_only` | 0.579 | 3.0% | 6.4% | +0.0009 |
| `TKO` | `prefight_odds` | 0.496 | 7.1% | 5.5% | +0.0004 |
| `unanimous decision` | `prefight_odds` | 0.531 | 8.0% | 10.9% | -0.0010 |
| `doctor` | `prefight_odds` | 0.529 | 4.7% | 5.5% | -0.0029 |

Interpretation: `submission` is the first clearly modelable market; `knockout` and
`knocked out` show weaker but real signal; sparse markets like `doctor`, `TKO`, and
`unanimous decision` need better features or a different modeling approach before
they are usable for betting.
