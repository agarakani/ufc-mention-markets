# Paper Tracking

Use this to track the model without risking money.

There are two ways to track:

- `snapshot`: save one board before the card starts.
- `live`: let the board keep ticking and save an entry only when a market first becomes `WATCH`.

Before a card starts:

```bash
python3 scripts/live/refresh_dashboard.py
python3 scripts/tracking/snapshot_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
```

That saves the model numbers, Kalshi YES/NO prices, official paper trades, and leans in
`data/tracking/<card>/`.

Live paper tracking:

```bash
python3 scripts/live/refresh_dashboard.py \
  --poll-seconds 30 \
  --paper-card "UFC Vegas 119 Kape vs Horiguchi main card"
```

The live tracker checks Kalshi every refresh. If a row becomes `WATCH YES` or
`WATCH NO`, it records one fake contract at the current buy price. If that same
market stays a watch later, it does not add another entry.

After the fights:

Keep the refresher running, or run it again later with the same `--paper-card`.
It checks Kalshi for final results. Once Kalshi resolves a market, the tracker
fills `yes` or `no` and recalculates paper P/L.

Rows can show three outcome states:

- `open`: still normal/open.
- `pending`: the fight date has passed, but Kalshi has not posted the final result.
- `yes` / `no`: Kalshi has resolved it.

Manual recalculation is still available:

```bash
python3 scripts/tracking/settle_card.py --card "UFC Vegas 119 Kape vs Horiguchi main card"
```

The tracker keeps two scores:

- `official`: only rows the model marked `WATCH`.
- `leans`: rows where YES or NO had positive model edge but did not clear the full watch bar.

Rows marked `data-risk watch` had thin fighter history, so they cleared a higher
edge bar before being tracked as official.

If official P/L stays flat because there are no WATCH rows, leans tell us
whether the model is close on price or whether the prices are simply not good.
