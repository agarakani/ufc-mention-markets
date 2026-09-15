# UFC Mention Markets

I built this to estimate which words UFC commentators will say during each
fight, then compare those chances with Kalshi's buy prices. It records paper
trades and checks their outcomes against Kalshi's settled results.

[Open the dashboard](https://agarakani.github.io/ufc-mention-markets/).
It is one scrolling page: **Night** shows each fight's phrases and saved prices;
**Book** breaks down paper profit; **Model** compares prediction quality;
**Record** lists the contracts. Open any word for its price history, or find a
fight with the search button or Cmd-K.

This is research tooling. It reads market data and **cannot place trades**.

## The record

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

For ongoing collection on macOS, `./install_autostart.command` installs the
recorder at login with a 30-second refresh interval. Its default port is 8765;
use `--port 8901` with `scripts/live/dashboard_server.py` when a separate port
is needed. Run one server per port. `./uninstall_autostart.command` removes the
service. When the recording Mac is offline, new recordings stop. The public
site stays available, and a cloud job can still reprice already published
markets. Check the footer timestamp and build hash.

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
