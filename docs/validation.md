# Validation record

Validated locally on 2026-09-13 using Python 3.13, NumPy 2.5.3, pandas 3.0.5, and PyArrow 25.0.1.

## Automated checks

`python -m unittest discover -s tests -v`: **31 tests passed**.

Coverage includes put/call parity, implied-volatility inversion, numerical delta/gamma checks, strict as-of prices, bounded stale exit evidence, OTM-distance tolerance, immunity to future-only strike listings, whole-contract volume participation, side-aware fills, cash-flow/fee accounting, delayed stop fills, custom-leg signs, partial-entry unwinds, unresolved exposure, fixed-BTC metrics, initial-capital drawdown, no-trade calendar dates, configuration validation, history deletion, strategy presets, duplicate/invalid-row ingestion, cache reuse, missing source dates, holdout-independent winner selection, IST bar alignment, next-bar trend execution, and multiple futures exits per day.

Python compilation and JavaScript syntax checks passed. The authored Markdown guide was rendered into the app's packaged HTML help pages.

## Real-archive checks

- Indexed the June 2026 source pair with explicit nanosecond timestamps and source SHA-256 fingerprints.
- The exact guide preset, June 1–7 at 0.01 BTC per leg, completed with seven closed positions and zero unresolved positions. Every closed position's P&L reconciled to its individual fill cash flows, including fees.
- The four-variant June 1–14 delta/stop experiment completed and selected its winner on development dates only. Holdout results remained separately visible.
- A stricter earlier size/time-window experiment produced partial entries and unresolved exposure; those positions were retained, later entries halted, and headline ratios suppressed.
- Checked health, app, guide, methodology, preset, and asset endpoints; rejected invalid API input; reconciled JSON and CSV exports to the selected result.
- Replayed the failing April 1–3, 2024 OTM strangle configuration from exported run `4ca435750579`: nearby-strike tolerance replaced the lopsided 73,200 call with a 70,200 call, the bounded exit-price fallback closed the remaining put from a 28.9-minute-old observed trade, and the result had one closed position with zero unresolved exposure.
- Replayed both trend models over June 1–7, 2026: each constructed 650 IST-aligned 15-minute bars from 2,753,210 BTCUSD ticks. The 20/50 EMA smoke produced six closed positions; Supertrend 10 × 3 produced sixteen. These results verify pipeline mechanics, not performance.

These are functionality checks, not strategy validation or a claim of trading profitability. Source data, actual trade evidence, and performance results remain in the local output directory and are excluded from this repository.

## Browser checks

- Inspected the working interface and a completed real-data result.
- Configured and submitted a parameter-grid experiment through the form.
- Verified the example-loading button changes the controls without submitting a run.
- Verified the guide renders all 13 sections, the detailed example, and every field-reference group.
- Verified the page's optional WebMCP configuration reader/stager in a supporting browser, including intentional rejection of an unknown field. WebMCP is feature-detected; ordinary browsers use the same visible controls.

## Remaining limits

The tests do not establish exchange execution fidelity, historical fee accuracy, live capital requirements, liquidation risk, official settlement values, or predictive performance. No overnight, rolling, hedging, settlement-to-expiry, or adaptive walk-forward simulation is claimed. See the methodology and usage guide for the full scope.


## BTC sizing and usability update (engine 1.2.0)

- 21 tests pass, including fixed-BTC capital independence, retained partial-fill limits, and recoverable history deletion with active-run protection.
- Browser checks: zero BTC produces a named validation error; 1 BTC starts immediately with a busy button, spinner and elapsed/ETA status; the guide preset completes one position with both 1 BTC legs fully entered and exited.
- The one-day guide uses June 1, 2026 ATM options, 100% volume participation and a 600-second fill timeout. This deliberately optimistic execution walkthrough is not a live-fill or performance claim. Seven-day checks at 1 BTC encountered unresolved exits; those outcomes remain explicit.
- Clear result view resets output; deleting a temporary validation run removes it from history and preserves its JSON in deleted_runs. Clearing all finished history is covered by an isolated test, without deleting the user's research history.
