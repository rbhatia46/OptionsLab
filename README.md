# Options Lab

A local Bitcoin options and BTCUSD futures research workbench. Edit strategy conditions in a browser, replay the Desktop tick archive, inspect the results, and compare ideas without editing Python.

**This is an intraday research simulator using historical public trades, not an exchange execution simulator or a live trading system.** It does not silently settle an unclosed position or discard a partial fill.

## Start

Requires Python 3.11+ (validated on Python 3.13).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/run_options_lab.py
```

Open **http://127.0.0.1:8765/**. On macOS, double-click **Start Options Lab.command** to set up the environment if necessary and launch the app. Leave its Terminal window open while using the app; Control-C stops it. Launching again opens an already running Options Lab instance.

The default source is `~/Desktop/BitcoinFNOData`. Override it with:

```sh
.venv/bin/python scripts/run_options_lab.py --data-root /path/to/BitcoinFNOData --port 8765
```

The original `BitcoinOptionsAlgo` project is not a runtime dependency. No credentials, remote services, or trading accounts are needed. The font stylesheet is optional; system fonts work offline.

## Learn the app

Read the [complete usage guide](docs/usage-guide.md) for an exact 0.20-delta strangle example, every field and option, a four-variant holdout experiment, and explanations of the results. It is also available through **Usage guide** in the app. **Load the guide example** populates the exact controls without running them.

For the standalone multi-timeframe RSI-versus-RSI-SMA directional option seller, use [the script guide](docs/rsi-option-seller.md). It reports each timeframe independently and a combined portfolio without requiring the browser UI.

## What you can test

- Short strangles, straddles, iron condors, call/put credit spreads, naked calls/puts, and custom 1–6-leg net-credit structures.
- Absolute delta selection (for example, 0.20 delta calls and puts), OTM strike distance, wing widths, BTC quantity, and calendar DTE targets.
- OTM-distance tolerance prevents a missing nearby quote from silently selecting a materially farther strike.
- Intraday entry/exit times in IST, a minute-by-minute entry retry window, and weekday/weekend filters.
- Per-leg IV bounds and a trailing one-hour underlying-return filter.
- Portfolio profit targets and stop losses as a percentage of actual entry credit; optional cash-loss and net-delta exits.
- A full-size observed-price model for strategy research, plus strict trade-volume participation for execution-capacity tests; both support latency, stale-price limits, adverse slippage, fees, premium fee caps, and fee tax. The price model can use a separately bounded older observed trade for exits and records its source time and age.
- BTCUSD futures moving-average crossover and Supertrend studies on IST-aligned 30-second through weekly bars, with long/short direction controls, next-bar execution, optional price stops and targets, and fixed BTC size.
- BTC quantity controls position size; the current UI has no account-capital constraint. Legacy capital-mode runs remain reproducible.
- Up to 36 combinations of delta, stop, and target, ranked by development Sharpe, P&L, or dollar drawdown. The final chronological portion is reported separately as holdout.

DTE selects the first *observed* expiry on or after the target date, within three days. All positions close in the same IST session; choosing a longer-dated contract does not enable overnight holding. The straddle uses a common ATM strike. Condors and spreads buy wings at least the configured distance beyond their short strikes.

## Results

The UI includes cumulative dollar P&L and observed drawdown, fixed-size daily-P&L Sharpe/Sortino, profit factor, win rate, fees and slippage, monthly P&L, trade excursions, tail-loss summaries, and portfolio Greeks. Every trade exposes the selected legs, IV/Greeks at the decision, actual partial quantities, entry/exit prints and costs, and exit reasons.

- **Run history** persists results across restarts and lets you reuse the configuration.
- **Save configuration / Import configuration** provides portable JSON presets.
- **Trade ledger CSV** exports the currently viewed variant, including its leg identities and decision Greeks.
- **Full result + configuration** exports the entire experiment with source fingerprints and audit evidence.
- **Data & coverage** inventories local source files; each run audits the selected dates and source contents.

The example configuration is for functionality testing, not a recommended strategy. The default full-size price proxy ignores displayed print quantity and may use the latest observed option trade within the configured exit-age bound when no fresh exit print exists. Strict volume mode can produce incomplete entries or unclosed exits for large orders; these are results, not errors to hide.

## Data contract

```text
BitcoinFNOData/
  options_data/BTC_YYYY-MM.csv
  futures_data/BTCUSD_YYYY-MM.csv
```

Both CSV types require `product_symbol,price,size,timestamp,buyer_role`. Options use `C-BTC-STRIKE-DDMMYY` or `P-BTC-STRIKE-DDMMYY`; futures use `BTCUSD`. Naive timestamps are interpreted as UTC. Prices and contract sizes must be positive. Buyer role must be `maker` or `taker`.

First use indexes a selected month into daily Parquet partitions. Subsequent experiments reuse the partitions. Cache identities include absolute source path, byte size, modification time, and schema version. The source SHA-256 and quality counters are recorded at ingestion. Changing file size or modification time invalidates the cache; modifying bytes while deliberately preserving both requires clearing the cache manually.

Raw files are read only. Cache lives in `data/options_lab_cache/`; saved experiments live in `outputs/options_lab/runs/`. **Neither raw data, caches, nor generated results are committed to GitHub.**

## Research limits

See [the methodology](docs/methodology.md) for the accounting, no-lookahead contract, return definitions, and limitations. Main constraints:

- Trades are not bid/ask quotes, depth, queue position, or guaranteed fills.
- IV and Greeks use European Black–Scholes and BTCUSD futures as a **spot proxy**. No official spot/index series is supplied.
- Risk monitoring starts after entry completion. Drawdowns between fills and during stale intervals may be unobserved. Reported observed drawdown can understate actual risk.
- Unclosed exposure halts subsequent entries and suppresses headline return/risk ratios. Cash flows and fill evidence are retained.
- Margin is a research reserve, not exchange portfolio margin or liquidation modelling.
- Options positions are intraday only. Futures trend positions can cross days inside the chosen sample and close on a signal change, stop, target, or final bar. Funding, liquidation, expiry settlement, rolling, delta hedging, portfolio allocation, natural-language strategy compilation, and walk-forward retraining are not modelled.
- Short windows are unsuitable for ranking stable Sharpe ratios. A repeatedly inspected holdout is no longer an untouched test set.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check app/options_lab/web/app.js  # optional JavaScript syntax check
```

The tests exercise pricing identities, IV inversion, analytical Greeks against numerical sensitivities, as-of timing, whole-contract volume limits, fill costs, partial-entry unwinds, unresolved exposure, drawdown from starting capital, validation, and ingestion caching. Browser validation and real-data smoke results are documented in [validation notes](docs/validation.md).

The Research workspace includes a 13-idea strategy library: nine options ideas plus 15-minute and one-hour moving-average/Supertrend futures templates. Each loads rules for review while keeping your BTC size. The builder starts in simple mode with advanced settings available on demand. See the [usage guide](docs/usage-guide.md#3-start-from-a-strategy-idea).
