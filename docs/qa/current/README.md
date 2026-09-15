# Current-card posters

Checked September 15, 2026, against the running local collector and the real
published payload. The screenshots here use the actual schedule, not fixtures.

- Ten upcoming cards were returned by UFC's official schedule. The first was
  UFC 331: Van vs Pantoja 2, September 19.
- A complete Kalshi scan returned no open UFC mention markets. The page shows
  the scheduled cards without invented fights, quotes, or paper entries.
- All ten official event images loaded. Headliners and title-bout labels came
  from the matching fight on the official event page. Numbered events without
  a confirmed title bout do not get a championship label.
- The local service was restarted with automatic paper tracking enabled and
  returned a successful status check. It continues checking every 30 seconds.
- Historical tapes, trades, P/L, and model files were preserved. The separate
  live paper log retained 111 recorded entries; this check added none.

## Checks

285 Python tests and 84 front-end tests passed. All 13 dashboard JavaScript
files passed syntax checks. Ruff and the whitespace check passed.

Chrome was checked at 375, 768, and 1440 pixels in both themes. The poster page
had no document overflow or automated WCAG violations. Current, Record, and
Model each kept one visible main heading. Firefox and WebKit passed mobile
navigation and keyboard opening/closing without page errors. The file preview
also loaded its real event art.

Separate synthetic-market tests covered changing prices, full-width phrase
details, old quotes, failed requests, focus retention, and local versus public
refresh behavior. Those fixtures were never written into the published data.
Poster tests cover failed images, unknown headliners, rematches, name suffixes,
and official billing that differs from Western name order, such as Wang Cong.

Native Safari, iOS hardware, and VoiceOver were not tested in this pass.
WebKit automation is not a substitute for those checks. No new performance or
profitability claim is made here.

## Screenshots

| | Dark | Light |
| --- | --- | --- |
| Desktop | [1440 px](desktop-dark.png) | [1440 px](desktop-light.png) |
| Mobile | [375 px](mobile-dark.png) | [375 px](mobile-light.png) |
