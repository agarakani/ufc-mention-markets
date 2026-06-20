# Paper Tracking

Use this to track the model without risking money.

Before a card starts:

```bash
python3 scripts/live/refresh_dashboard.py
python3 scripts/tracking/snapshot_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
```

That saves the model numbers, Kalshi prices, official paper trades, and leans in
`data/tracking/<card>/`.

After the fights:

1. Open `data/tracking/<card>/outcomes.csv`.
2. Put `yes` or `no` in the `outcome` column for each phrase.
3. Run:

```bash
python3 scripts/tracking/settle_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
```

The tracker keeps two scores:

- `official`: only rows the model marked `WATCH`.
- `leans`: rows the model liked but did not clear the safety bar.

If official P/L stays flat because there are no WATCH rows, leans tell us
whether the model is too cautious or whether the prices are simply not good.
