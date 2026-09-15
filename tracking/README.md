# Paper Tracking

This records simulated entries, not real orders. New paper entries stay separate
from the dashboard's historical test results.

Start the local collector:

```bash
PAPER_CARD=auto ./start_live_dashboard.command
```

The installed login service already uses automatic paper tracking. Run one
collector, not both. The public cloud price updater cannot record paper entries.

## Entries

Every local refresh checks for a model signal that clears the entry rule. The
market must be open, with a real buy quote no older than 90 seconds. The tracker
saves one contract at that side's buy price and does not add another just because
the signal remains. The original price, model estimate, and timestamp are kept
in `data/tracking/<card>/`.

New entries stop when the card starts, even if Kalshi still allows trading. The
cutoff comes from the official UFC schedule. If it cannot be verified, the
tracker blocks new entries. Missing quotes or model estimates also block
entry. A scheduled fight without a mention market creates no position.

## Results

Keep the collector running, or restart it later. It checks Kalshi's results for
saved positions and fills outcomes automatically:

- `open`: no final result, and the market is still open.
- `pending`: the market closed or the fight date passed, but no final result is available.
- `yes` / `no`: Kalshi posted a result.

Unresolved positions are not counted as wins or losses. Settled profit is the
contract payout minus its recorded cost, **before fees**. The entry rule's fee
allowance does not deduct actual fees from these totals. Quoted prices are
simulated fills, so this log is not proof of executable profit.
