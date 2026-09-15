# UFC Mention Markets

I built this to estimate which words UFC commentators will say during each
fight, then compare those chances with Kalshi's buy prices. It records paper
trades and checks their outcomes against Kalshi's settled results.

[Open the dashboard](https://agarakani.github.io/ufc-mention-markets/).
**Current** starts with upcoming UFC cards. Open a card, choose a fight, and
compare the model with Kalshi's YES and NO buy prices. A scheduled card can
appear before its phrases go on sale. No mention market means no odds or paper
entry, not a made-up estimate.

The live paper log is separate from the historical test. **Past cards** holds
saved price histories; **Model** shows prediction tests; **Record** starts with
the collector's paper entries, followed by the earlier backtest.

This is research tooling. It reads market data and **cannot place trades**.

## The historical test

The saved record covers June 20, July 11, July 18, and July 25, 2026:

| Paper contracts | Wins | Profit before fees | Return on entry cost |
| --- | --- | --- | --- |
| 134 | 80 | +$9.33 | +13.2% |

Three nights lost money. July 11 made +$13.24 and carries the overall result.
Contracts within a card share fighters and commentary, so **four nights is the
sample**. This does not establish a profitable strategy. Entries use recorded
buy quotes; they are simulated fills, and the totals exclude fees.

On the same 364 pre-fight markets, average log loss was **0.4918 for the model,
0.4770 for Kalshi, and 0.5435 for the base rate**. Lower is better. This base
rate uses the observed said rate in that same sample. The model beat that
constant prediction and trailed the market. Expected calibration error was
**0.066 for the model and 0.045 for Kalshi**; this measures the gap
between predicted chances and observed outcomes, grouped by probability.

These figures come from `model_outputs/pl_backtest_summary.json` and
`model_outputs/calibration_report.json`. The dashboard receives them through
`ufc_mentions/build_dashboard_data.py`.

## How a number gets made

1. Find UFC mention markets on Kalshi and read the exact phrase forms each
   contract covers, such as `Choke / Choked / Chokehold`.
2. Match those words against a corpus of 5,578 fight transcripts. Fit a logistic
   regression for the phrase using earlier fighter history and fight details.
   The selected version also uses event tier.
3. Estimate a YES chance for that individual fight. Kalshi prices do not enter
   this calculation.
4. Compare that chance with the YES buy price, and its complement with the NO
   buy price. The entry rule accounts for the spread, a fee allowance, limited
   fighter history, and the phrase's historical test results.

The paper record uses one contract at the first saved quote that passed the
entry rule then in use. Later rule changes do not replace that recorded signal
with a hindsight decision. An edge cap rejects unusually large disagreements;
the rule and model still need more independent cards to prove themselves.

## Keeping future information out

Training and validation follow date order. A fighter's history uses earlier
fights only. The model-selection gate tests candidates on later cards, fits
corrections using earlier cards, and selects the lowest held-out log loss.

The calibration comparison takes each market's last saved prediction and price
at or before **noon UTC on fight day**. It uses the YES bid-ask midpoint when
both quotes exist, with a single-quote fallback. It excludes prices recorded
during the fight, when the answer may already be known. The current rule was
developed after the first settled card, so that card cannot independently
validate those changes.

## Run it

Use Python 3.11 and a current Node.js release. The Makefile installs pinned
Python dependencies from `requirements.lock` and front-end test dependencies
with `npm ci`:

```bash
make install
make test
make lint
```

Preview an existing dashboard payload locally:

```bash
make preview
```

Open `http://127.0.0.1:8766`. The data files are excluded from git, so a fresh
clone needs the local datasets and generated `dashboard/data.js`; the public
site includes the published payload.

To collect prices and paper trade upcoming cards:

```bash
PAPER_CARD=auto ./start_live_dashboard.command
```

This opens `http://127.0.0.1:8765`, checks Kalshi every 30 seconds, and saves one
paper contract when an eligible market first clears the entry rule. New entries
stop at the card's verified start time. Without a verified start time, no new entries are allowed.
Leave the process running; Control-C stops it. The launcher without
`PAPER_CARD=auto` updates prices but leaves paper tracking off.

For automatic startup on macOS, run `./install_autostart.command` once. It starts
the collector at login with paper tracking on. Do not start a second collector
on the same port. `./uninstall_autostart.command` removes the login service.

The public site's cloud job is scheduled every 10 minutes. It discovers cards
and mention listings and updates quotes, but **does not record paper trades**.
New listings need the local model before they get a model price. When the Mac
is asleep or offline, local recording stops. The page checks for updated data
every 30 seconds. On the local server, the refresh button also asks the
collector for a new check; on the public site, it loads the latest published
data. Check the update time and collector status before treating a quote as
current.

Public Kalshi reads need no credentials. Optional read credentials belong in
the gitignored `.env`. There is no order-placement code path.

## Repo map

```text
dashboard/           ordered JavaScript modules, styles, static page
ufc_mentions/        phrase model, fighter history, Kalshi client, payload
scripts/live/        refresh, local server, publish
scripts/model/       prediction tests, calibration, model selection, paper P/L
scripts/data/        training tables and per-night price recordings
scripts/tracking/    paper entries and settlement
tests/               Python and front-end checks
```

Generated data lives outside git in `data/processed/`, `market_data/`,
`model_outputs/`, and `dashboard/data.js`. The dashboard keeps its plain,
ordered script loader and has no build step.
