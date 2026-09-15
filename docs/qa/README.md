# Verification, September 15, 2026

This branch fixes navigation, accessibility, empty states, and publication
checks. It does not change model calculations or the recorded trades.
**It is not ready for an unconditional release.** The saved feed fails the new
identity check, the live speed target is unmet, and native screen-reader testing
is still outstanding.

## Work order

- [ ] 1. Browser QA: Chrome, Firefox, and WebKit checked locally and publicly;
  native Safari and iOS Safari unavailable. See the matrix and screenshots below.
- [ ] 2. Performance: scrub target met in the measured desktop run; live mobile
  Lighthouse performance is 86, below the requested 95.
- [ ] 3. Accessibility: automated checks and keyboard paths covered; actual
  VoiceOver use could not be verified in this environment.
- [x] 4. README: current page, corrected pre-fight results, limitations, commands,
  and repo map. Removed `docs/superpowers/`.
- [x] 5. CI: Python 3.11, pinned dependencies, Ruff, JavaScript syntax and behavior,
  publisher asset coverage. Existing scheduled refresh workflow unchanged.
- [x] 6. Python: public-function annotations, scoped unused-import cleanup,
  dependency lock, and Makefile.
- [x] 7. Integrity and edge states: reject missing identities and inconsistent
  equity before either publisher writes; render missing data and pending results.
- [x] 8. Copy: captions follow the payload, missing scores stay unavailable, and
  absent trades do not imply that the entry rule never fired.
- [x] 9. Tests: selectors, routing, focus, syntax discovery, publication races,
  and pagination against two recorded Kalshi event pages.

## Browser coverage

Chrome 152.0.7977.84, Firefox 146.0.1, and WebKit 26.0 were run headlessly on
macOS. WebKit is an engine check, **not a claim of testing native Safari**.
Safari remote automation was disabled, native app control permission was not
available, and no iOS simulator was installed. Nothing here substitutes for a
VoiceOver walkthrough or a physical touch device.

For each engine, the local and public pages were checked at 375, 768, 1024, and
1440 pixels wide, in both themes, on all four recorded nights. The resulting
192 cases per pass are in [before-matrix.json](before-matrix.json) and
[after-matrix.json](after-matrix.json). The attached screenshot comparisons use
July 11, the largest board, to keep the evidence small. Full-resolution captures
of the other matrix cases were also taken during the run.

| Engine | Width | Dark | Light |
| --- | --- | --- | --- |
| Chrome | 375 | [Before](before/chrome-local-375-dark-26JUL11.png) / [After](after/chrome-local-375-dark-26JUL11.png) | [Before](before/chrome-local-375-light-26JUL11.png) / [After](after/chrome-local-375-light-26JUL11.png) |
| Chrome | 768 | [Before](before/chrome-local-768-dark-26JUL11.png) / [After](after/chrome-local-768-dark-26JUL11.png) | [Before](before/chrome-local-768-light-26JUL11.png) / [After](after/chrome-local-768-light-26JUL11.png) |
| Chrome | 1024 | [Before](before/chrome-local-1024-dark-26JUL11.png) / [After](after/chrome-local-1024-dark-26JUL11.png) | [Before](before/chrome-local-1024-light-26JUL11.png) / [After](after/chrome-local-1024-light-26JUL11.png) |
| Chrome | 1440 | [Before](before/chrome-local-1440-dark-26JUL11.png) / [After](after/chrome-local-1440-dark-26JUL11.png) | [Before](before/chrome-local-1440-light-26JUL11.png) / [After](after/chrome-local-1440-light-26JUL11.png) |
| Firefox | 375 | [Before](before/firefox-local-375-dark-26JUL11.png) / [After](after/firefox-local-375-dark-26JUL11.png) | [Before](before/firefox-local-375-light-26JUL11.png) / [After](after/firefox-local-375-light-26JUL11.png) |
| Firefox | 768 | [Before](before/firefox-local-768-dark-26JUL11.png) / [After](after/firefox-local-768-dark-26JUL11.png) | [Before](before/firefox-local-768-light-26JUL11.png) / [After](after/firefox-local-768-light-26JUL11.png) |
| Firefox | 1024 | [Before](before/firefox-local-1024-dark-26JUL11.png) / [After](after/firefox-local-1024-dark-26JUL11.png) | [Before](before/firefox-local-1024-light-26JUL11.png) / [After](after/firefox-local-1024-light-26JUL11.png) |
| Firefox | 1440 | [Before](before/firefox-local-1440-dark-26JUL11.png) / [After](after/firefox-local-1440-dark-26JUL11.png) | [Before](before/firefox-local-1440-light-26JUL11.png) / [After](after/firefox-local-1440-light-26JUL11.png) |
| WebKit | 375 | [Before](before/webkit-local-375-dark-26JUL11.png) / [After](after/webkit-local-375-dark-26JUL11.png) | [Before](before/webkit-local-375-light-26JUL11.png) / [After](after/webkit-local-375-light-26JUL11.png) |
| WebKit | 768 | [Before](before/webkit-local-768-dark-26JUL11.png) / [After](after/webkit-local-768-dark-26JUL11.png) | [Before](before/webkit-local-768-light-26JUL11.png) / [After](after/webkit-local-768-light-26JUL11.png) |
| WebKit | 1024 | [Before](before/webkit-local-1024-dark-26JUL11.png) / [After](after/webkit-local-1024-dark-26JUL11.png) | [Before](before/webkit-local-1024-light-26JUL11.png) / [After](after/webkit-local-1024-light-26JUL11.png) |
| WebKit | 1440 | [Before](before/webkit-local-1440-dark-26JUL11.png) / [After](after/webkit-local-1440-dark-26JUL11.png) | [Before](before/webkit-local-1440-light-26JUL11.png) / [After](after/webkit-local-1440-light-26JUL11.png) |

The baseline is commit `1058a36`. The after pass uses this branch. The captured
payloads differ in refresh metadata, but their `tapes`, `trades`, `performance`,
`fighters`, and `model_health` values are identical. The existing recorder
published some in-progress assets before it was paused, so the public page is
not a pristine baseline and its footer hash alone does not prove asset parity.
The branch has not been intentionally published over that page.

## Interaction checks

The local matrix had no horizontal document overflow, clipped tested labels,
navigation failures, or uncaught script errors. Two baseline night-button
clicks failed at 768 pixels in Chrome and Firefox; the corrected navigation
keeps every night reachable.

Mouse scrubbing and Home, End, and arrow keys selected the expected snapshots.
Word details opened from a tile, a record row, search, and a direct link. Previous
and next stayed within the fight. Escape closed search without also closing the
pane. Tab stayed inside the active dialog. Direct Model and Record links were
also checked with normal motion after their deferred sections finished loading.

The extra checks are in [state-checks.json](state-checks.json). Their synthetic
long-name and phrase examples are clearly labelled and exist only in the test
browser, never in the feed. Examples:

- [Long names and phrase forms](states/chrome-375-light-synthetic.png)
- [Empty search](states/chrome-empty-search.png)
- [Missing recordings](states/chrome-missing-tapes.png)
- [Font service unavailable](states/chrome-font-fallback.png)
- [Phone word detail](states/chrome-phone-pane.png)
- [Phone record](states/ledger-phone.png)
- [Emulated touch scrub](states/touch-scrub.png)

The record had two additional phone bugs: the header overlapped the first row,
and the tall table could remain invisible while waiting for its scroll reveal.
The header now starts at the table's own top and rows show immediately.
[Hidden table before](states/ledger-hidden-before.png) /
[visible table after](states/ledger-phone.png).

## Accessibility

The local board returned no axe violations in either theme in all three
engines. Synthetic tile checks also passed at 11 quote levels, for both result
colors and both themes, in all three engines (132 checks). Visible tile text
remains its accessible name; a separate description
provides the exact phrase, both fighters, result state, YES price in cents, and
model percentage. Keyboard regression tests cover focus return and trapping.
Automated checks do not establish what VoiceOver actually announces.

The remaining native walkthrough is: switch all four nights, adjust the price
slider, open a word, move to the next word, open search over the pane, dismiss
search, return to the originating tile, and open a trade from the record.
Check the spoken units, result state, focus position, and announcement frequency.

## Performance

| Run | Performance | Accessibility | First paint | Largest paint | Blocking time | Layout shift |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public, Sep 12 | 85 | 96 | 3.11 s | 3.11 s | 0 ms | 0 |
| Public, Sep 15 | 86 | 100 | 3.23 s | 3.23 s | 0 ms | 0 |
| Local preview, Sep 15 | 78 | 100 | 1.05 s | 6.05 s | 0 ms | 0.001 |

These are Lighthouse 12.8.2 default mobile runs, not desktop scores. The local
server is Python's uncompressed static server. The public runs are observations
of the deployed assets, not a before/after proof of this complete branch.
Lighthouse's accessibility score covers its default view; separate light-theme
checks on the older public assets still found contrast problems.

Raw reports: [public before](lighthouse-live-before.report.json),
[public later](lighthouse-live-final.json), [local](lighthouse-local-final.json).
The live performance target of 95 remains unmet.

The [scrub measurement](scrub-performance.json) used 120 July 11 tiles and
239 measured frame intervals: median 16.7 ms, 95th percentile 16.7 ms,
maximum 16.8 ms, with no JavaScript long tasks over 50 ms. The emulated touch
drag reached snapshot 68. An earlier run while other browser checks were active
had a 116.6 ms worst frame, so this is not a guarantee across devices or loads.

## Data and release blockers

`make validate` currently stops at:

```text
KXFIGHTMENTION-26JUN20BAGMAG-BLOO: Murtazali Magomedov is missing from fighters
```

Twenty referenced fighter names lack directory entries. The complete list and
feed checksum are in [validation.json](validation.json). Some could be aliases;
they must be checked against real identities before adding or linking records.
The validator checks the exact bytes the local publisher stages, and the cloud
refresh checks its candidate before replacing the existing feed. Tests cover
concurrent source changes and preserving the old file after a rejected refresh.

I left the protected datasets, models, and saved P/L alone. Resolving identity
gaps can affect fight ordering and the displayed title, so that is a separate
data correction. I also left contract sizing at its recorded one-contract rule;
confidence-based sizing needs a separate test and must not rewrite this record.

## Test results

The final local run passed 219 Python tests and 40 front-end tests. Ruff and
syntax checks passed for all 12 local JavaScript files, including `data.js`.
The pinned environment was tested independently from the existing environment.
Without ignored local datasets, the Python run passes 217 tests and skips two
existing data-dependent checks. CI checks the 11 tracked JavaScript files and
will include any additional JavaScript files added anywhere in the dashboard.

Reproduce the source checks with `make install`, `make test`, and `make lint`.
`make validate` is intentionally separate and currently fails on the missing
identities listed above; green code tests do not mean that feed is publishable.

Automatic collection is paused. Restarting the recorder immediately updates
generated data, which conflicts with this work order's freeze. Resume by
restarting it with the new code only after that update is approved; resuming the
old stopped process would retain the old publisher in memory.
