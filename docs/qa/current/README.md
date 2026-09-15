# Current-card page

Checked September 15, 2026, against the running local collector and the real
published payload. The screenshots here use the actual schedule, not fixtures.

- Ten upcoming cards were returned by UFC's official schedule. The first was
  UFC 331: Van vs Pantoja 2, September 19.
- A complete Kalshi scan returned no open UFC mention markets. The page shows
  the scheduled cards without invented fights, quotes, or paper entries.
- The local service was restarted with automatic paper tracking enabled.
  A browser refresh advanced its successful-check timestamp from 21:37:12 to
  21:37:38 UTC. A subsequent background check completed at 21:37:39 UTC.
- Historical tapes, trades, P/L, and model files were preserved. The separate
  live paper log retained 111 recorded entries; this check added none.

## Checks

268 Python tests and 66 front-end tests passed. All 13 dashboard JavaScript
files passed syntax checks. Ruff and the whitespace check passed.

Chrome was checked at 375 and 1440 pixels, in both themes, across Current,
Record, and Model. Each view had one visible main heading, no document overflow,
and no automated accessibility violations. Firefox and WebKit passed mobile
navigation and heading checks without page errors. Historical word links and
Escape still opened and closed the word pane correctly.

Separate synthetic-market tests covered changing prices, full-width phrase
details, old quotes, failed requests, focus retention, and local versus public
refresh behavior. Those fixtures were never written into the published data.

Native Safari, iOS hardware, and VoiceOver were not tested in this pass.
WebKit automation is not a substitute for those checks. No new performance or
profitability claim is made here.

## Screenshots

| | Dark | Light |
| --- | --- | --- |
| Desktop | [1440 px](desktop-dark.png) | [1440 px](desktop-light.png) |
| Mobile | [375 px](mobile-dark.png) | [375 px](mobile-light.png) |
