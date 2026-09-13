# Options Lab usage guide

Choose an idea, set the BTC quantity, select dates, and run. The basic builder keeps execution and model controls under **Show advanced settings**.

## 1. Start the app

1. Double-click **Start Options Lab.command** in the OptionsLab folder. Leave its Terminal window open.
2. Open **http://127.0.0.1:8765/**. Refresh an older tab to load the updated interface.
3. The archive strip should show the monthly files in **Desktop/BitcoinFNOData**. Use **Data & coverage** to inspect available months.
4. The engine reads local CSVs automatically and caches daily partitions. It never modifies the raw archive.

A cached replay can finish in seconds. It processes historical events as fast as the computer can, without waiting for market time to pass. The first run against a new month can take longer because it indexes the data.

## 2. Position size means BTC

**Position size (BTC per leg) = 1** means a 1 BTC position in each standard leg. A short strangle requests one 1 BTC put and one 1 BTC call. An iron condor requests four 1 BTC legs. Custom leg ratios multiply the base BTC size. One contract represents 0.001 BTC.

There is no research-capital input or capital-reserve eligibility check in the current UI. The normal **Full BTC size at a fresh observed price** model applies the requested quantity to a fresh observed option price, then applies slippage and fees. It ignores the size of the source print, so it is a price-path backtest rather than proof that 1 BTC could have filled live.

Cash P&L is reported in USD: premium change per BTC × filled BTC, less costs. The chart starts at zero cumulative P&L. Dollar drawdown measures the drop from its previous peak. Percentage account returns, percentage drawdown, CAGR and Calmar are not applicable without an account-capital denominator. Sharpe and Sortino in BTC-size mode use daily dollar P&L, including zero-trade calendar days, with a zero benchmark and √365 annualization. These are fixed-size P&L ratios, not returns on a funded account. The headline ratios are hidden below 20 closed positions; 20 is only a display threshold, not evidence of reliability.

Previously saved runs retain their original sizing mode and calculations. Reusing their rules in the current UI runs them in BTC-size mode, so old capital constraints no longer apply.

## 3. Start from a strategy idea

1. In **Start with an idea**, choose a card, or click **Show all 9 ideas**.
2. Filter by Neutral, With wings, Directional, Session study, or Experiments.
3. Click **Load strategy**. It loads rules, dates and execution assumptions while preserving your current BTC quantity.
4. Review the dates and session in the builder. Cards are templates, not preselected profitable strategies.
5. Click **Run backtest**. Loading a card alone never starts a run.

| Idea | Rules |
| --- | --- |
| 20Δ short strangle | Sell a 0.20-delta put and call; target 50% of credit, stop at a 100% credit loss. |
| 20Δ iron condor | Same shorts with long wings $1,000 farther out. |
| Bullish put credit spread | Sell a 0.25-delta put, buy a put $1,000 lower; require a nonnegative trailing-hour move. |
| 15Δ wider strangle | Sell 0.15-delta put and call, tolerance 0.05. |
| ATM short straddle | Sell put and call at a common near-ATM strike; target 25%, stop 100%. |
| Bearish call credit spread | Sell a 0.25-delta call, buy a call $1,000 higher; require a nonpositive trailing-hour move. |
| Delta-selected wings | Sell 0.25-delta put/call and buy 0.10-delta put/call; ratio 1 each, tolerance 0.04. |
| Weekend short strangle | Baseline strangle, weekends only, June 1–14, 2026. |
| Delta × stop comparison | Four variants: delta 0.15/0.20 and stop 100%/150%; June 1–14, 70% development, minimum 3 development trades. |

Standard cards generally use June 1–7, 2026, 0 DTE and 11:30–17:00 IST. They use the full-size observed-price proxy. To test historical execution capacity, choose **Show advanced settings → Fill model → Strict observed print volume**. In that mode, participation and the fill timeout apply; 1 BTC can produce partial fills or unresolved exposure.

## 4. Detailed running example: 1 BTC 20-delta short strangle

This is a one-day workflow walkthrough, not a profitability or robustness study. It uses the full-size observed-price proxy. Do not treat its fills as evidence that the historical market had enough depth for a live 1 BTC order.

1. Click **Load the guide example** in the app header. Unlike library cards, this button deliberately sets the exact example, including **1 BTC** quantity.
2. Confirm **Strategy name = Guide · 1 BTC 20-delta short strangle**.
3. Confirm **Structure = Short strangle**, **Selection method = Absolute delta**, **Call delta = 0.20**, **Put delta = 0.20**, **Delta tolerance = 0.08**, and **Position size (BTC per leg) = 1**. The engine separately selects a call near +0.20 delta and a put near −0.20 delta.
4. Under **Session & sample**, set **From = 2026-06-01**, **Through = 2026-06-01**, **Entry decision = 11:30**, **Time exit = 17:00**, and **Trade days = Every day**. All displayed session times are IST.
5. Under **Exits & risk**, confirm **Profit target = 50** and **Stop loss = 100**. These are percentages of net entry credit, not a percentage change in the BTC price.
6. Click **Show advanced settings**. The exact additional values are below; the guide button has already populated them.
7. Click **Run backtest**. The button changes immediately, a spinner appears, and the status shows the current operation, elapsed time and approximate ETA once there is enough progress to estimate it.
8. After completion, read **What this run actually tested**. Check requested size, complete entries, closed positions, unresolved exposure and net P&L. The run can lose money; that does not mean the calculation failed.
9. Open **Trade ledger**, click its date, and inspect the two symbols, filled BTC, entry Greeks and individual fills. Open **Audit** for data hashes and rejected-entry reasons.
10. Export **Full result + configuration** or **Trade ledger CSV**. For a research study, extend the sample and test stricter participation assumptions. Do not extrapolate this single trade's Sharpe or win rate.

With the supplied archive and engine version 1.3.0, this exact one-day run should produce the following reproducibility check. Small display-rounding differences are acceptable; different symbols, quantities, exit reason, or unresolved exposure are not.

| Verification item | Expected result |
| --- | --- |
| Runtime after the June cache exists | About 1 second; first use can take longer while indexing |
| Complete entries / closed / unresolved | 1 / 1 / 0 |
| Put selected | `P-BTC-72800-010626`, 1.000 BTC, decision delta about −0.19793, IV about 32.41% |
| Call selected | `C-BTC-73800-010626`, 1.000 BTC, decision delta about +0.20506, IV about 29.91% |
| Entry / exit shown in the UI | About 11:30:01 IST / 13:19:04 IST |
| Entry credit | $137.61 |
| Exit reason | Credit stop |
| Net P&L | About −$143.71 after $14.68 fees and $4.03 modeled slippage |
| Max observed drawdown | About $147.33 |
| Win rate | 0% from one closed position |
| Sharpe | Hidden as **Too few trades**, because the UI requires at least 20 closed positions |

For a second check, change only **Through** to **2026-06-07**. The cached run should take only a few seconds. Engine 1.3.0 produced 7 complete entries, 7 closed positions, 0 unresolved positions, 3 profit targets, 4 credit stops, net P&L about −$360.82, max observed drawdown about $396.31, win rate 42.86%, fees $93.75, slippage $26.07, and mark coverage 99.76%. The engine calculates a seven-day Sharpe, but the headline remains hidden because seven trades are too few.

Use durations in stages:

1. **One day** verifies selection, 1 BTC sizing, IST conversion, costs, and exit accounting against the figures above.
2. **Seven days** verifies repeated daily entry and both target and stop exits against the second check above.
3. **At least 90 calendar days** is a first research sample. Review missing days, complete entries, unresolved exposure, and monthly consistency before interpreting performance.
4. **The full available period** is the final single-rule replay. Use the chronological holdout experiment for comparisons and avoid choosing rules from the holdout result.

| Advanced control | Example value |
| --- | --- |
| Selection method | Absolute delta |
| Expiry target (DTE) | 0 |
| Call delta / Put delta / Delta tolerance | 0.20 / 0.20 / 0.08 |
| OTM distance / Wing width | 1% / $1,000; ignored for a delta-selected strangle |
| Entry retry window | 30 minutes |
| Minimum credit | $1 total entry premium |
| Max loss per trade / Portfolio delta cap | 0 / 0, both disabled |
| Minimum IV / Maximum IV | 0% / 500% |
| Min / Max trailing 1h move | −100% / 100%, filter disabled |
| Premium slippage | 1% adverse per fill |
| Fill model | Full BTC size at a fresh observed price |
| Volume participation | Ignored in the selected fill model; used only by strict observed-volume replay |
| Latency | 1 second |
| Fill timeout | 600 seconds per attempt |
| Option max age / Underlying max age | 300 / 60 seconds |
| Fee / Fee cap / Tax on fees | 0.01% notional / 3.5% premium / 18% |
| Risk-free rate / Expiry time | 0% / 17:30 IST |
| Mode | Single configuration |
| Grid deltas / Stops / Targets | 0.15, 0.2, 0.25 / 100, 150 / 50; ignored in single mode |
| Objective / Development sample / Minimum trades | Sharpe / 70% / 5; ignored in single mode |

The original small weekend example's −$0.34 came from 0.01 BTC per leg, two closed positions, ten excluded weekdays and two no-entry weekends. Its two net outcomes were approximately +$0.69 and −$1.03. The small sample and size explain the tiny P&L; it was not a meaningful strategy evaluation.

## 5. Every strategy and session control

The applicability banner below **Structure** updates as you edit the strategy. In simple mode, irrelevant controls are hidden. Under **Show advanced settings**, they remain visible but are dimmed and marked **NOT USED** with the exact reason, so a saved value cannot be mistaken for an active rule. Optional controls set to their disabling value are marked **OFF**. An amber banner identifies combinations the engine cannot run, such as an OTM-selected parameter grid.

| Control | Meaning |
| --- | --- |
| Strategy name | Your label in saved run history. |
| Structure | Strangle sells put and call at separate selected strikes; straddle uses one common ATM strike; condor adds long wings; spreads have one short and one long; short call/put is one-sided; custom uses the leg editor. |
| Position size (BTC per leg) | Requested quantity in BTC; multiples of 0.001. Partial fills may be smaller. |
| Selection method | Absolute delta or percentage distance out of the money. Custom legs always use delta; straddle uses ATM selection. |
| Call delta / Put delta | Positive absolute targets for the relevant short legs; 0.20 means call +0.20 or put −0.20 before applying the position side. |
| Delta tolerance | Maximum allowed difference between target and selected absolute delta. |
| Expiry target (DTE) | Calendar days to expiry. Uses the nearest observed expiry on/after the target, within three days. All positions are still closed intraday. |
| OTM distance (%) | Strike distance from underlying when OTM selection is active. |
| Wing width (USD) | Strike-price distance to protective long options for standard spreads/condors, not a position amount. |
| Custom leg Side / Type | Buy/sell and put/call for each of at most six legs. |
| Custom absolute delta / Ratio | Per-leg target and integer quantity multiplier, 1–10. At least one short leg and positive entry credit are required. |
| From / Through | Inclusive dates. Missing days are explicitly reported. |
| Entry decision / Time exit | IST times. Orders fill after decisions and configured latency. |
| Entry retry window | Retry selection each minute if no candidate qualifies, up to this many minutes. |
| Trade days | Every day, weekdays, or weekends. |

## 6. Exits and entry filters

| Control | Meaning |
| --- | --- |
| Profit target (% credit) | Close when marked net profit reaches this fraction of actual entry credit. |
| Stop loss (% credit) | Close when marked net loss reaches this fraction of credit. 100 means loss equal to one entry credit; actual fills may exceed it. |
| Minimum credit (USD) | Minimum total premium for the requested BTC quantity. A high threshold can prevent entries. |
| Max loss per trade (USD) | Additional dollar loss trigger; zero disables it. |
| Portfolio delta cap (BTC) | Close when absolute signed portfolio delta reaches the cap; zero disables it. This is exposure, not individual option delta or a hedge. |
| Minimum / Maximum IV (%) | Estimated IV bounds applied to every leg, including wings. |
| Min / Max trailing 1h move (%) | Prior-hour underlying price change filter. −100 to +100 disables the filter. Insufficient prior data otherwise skips selection. |

## 7. Execution and model settings

| Control | Meaning |
| --- | --- |
| Fill model | **Full BTC size** fills the requested quantity at a fresh observed option trade price and ignores source-print size. **Strict observed print volume** limits quantity to historical prints and can leave exposure unresolved. |
| Premium slippage (%) | Adverse adjustment to each observed fill premium. |
| Volume participation (%) | Strict-mode maximum fraction of each eligible trade print available to the simulated order, rounded down to whole contracts. Ignored by the full-size model. |
| Latency (seconds) | Fills must occur strictly after decision plus this delay. |
| Fill timeout (seconds) | Maximum fill window for each attempt. Incomplete entries are unwound; failed exits receive one retry. |
| Option max age (seconds) | Reject stale option observations beyond this age. |
| Underlying max age (seconds) | Maximum age of the futures-price proxy. |
| Fee (% notional / fill) | Rate on filled BTC × underlying price per fill. |
| Fee cap (% premium) | Limits the fee to this fraction of filled premium. |
| Tax on fees (%) | Additional percentage of the fee. Historical fee schedules are not in the data. |
| Risk-free rate (%) | Black–Scholes pricing input. Fixed-BTC P&L ratios use zero benchmark because no cash account is modelled. |
| Expiry time (IST) | Contract expiry assumption; all exit attempts must finish before expiry or day end. |

The archive contains trade prints, not an order book. The model uses buyer roles for eligible trade sides and futures as a spot proxy for inferred IV and Black–Scholes Greeks. There is no overnight carry, rolling, dynamic hedging, exchange liquidation or official settlement simulation. Risk is observed after entry completion and only at available fresh marks; reported drawdown may understate unobserved losses.

## 8. Parameter experiments

| Control | Meaning |
| --- | --- |
| Mode | Single configuration or parameter grid with chronological holdout. |
| Symmetric deltas | Comma-separated delta values; each replaces both standard short-leg targets. |
| Stop loss values / Profit targets | Comma-separated percentage values. |
| Objective | Development-period Sharpe, net P&L, or lowest dollar drawdown. |
| Development sample (%) | Initial fraction of dates used for selection; later dates are holdout. |
| Min development trades | Minimum closed positions required before a variant can rank. |

Use at least 10 calendar days, at most 36 combinations, and a standard delta-selected structure other than straddle. Custom/OTM/straddle delta sweeps are not supported. Missing development data, unresolved exposure or an undefined objective prevents a winner. Repeatedly tuning to the holdout compromises its independence. The comparison table retains descriptive ratios; evaluate sample size before interpreting them.

## 9. Progress, errors and cancellation

The Run button immediately displays **Backtest running…**. During a run, the results panel shows a spinner, current phase/date, elapsed time and approximate remaining time. ETA starts as **estimating** while indexing or before enough progress exists. It can change as daily tick counts and liquidity differ. Completion is never delayed merely to make it look slower.

If an input is invalid, a message near the Run button names the field and opens its section. If the server is unavailable, an explicit error replaces silent waiting. Start the launcher and try again. If progress communication fails, open **Run history → Open result** for the active run to reconnect before submitting another run.

**Cancel run** requests cancellation at the next engine checkpoint. Wait for confirmation before starting another. Reloading the page reconnects to the active run, but does not automatically reopen a finished result.

## 10. Clear results or delete saved runs

- **Clear result view** resets the visible output without deleting saved history or changing strategy inputs. Cancel an active run before clearing its progress.
- **Run history → Delete** removes one finished, failed, cancelled or interrupted run.
- **Run history → Delete all finished runs** clears all non-active history. Active runs are kept.
- Deleted run JSON files move to **outputs/options_lab/deleted_runs**. Raw data and indexed cache are unaffected. To recover a deleted run, stop the server, move its JSON back into **outputs/options_lab/runs**, then restart.
- **Save configuration** downloads the current rules; **Run history → Import configuration** loads a saved JSON file for review.

## 11. Read the results

**What this run actually tested** explains the sample, sizing, fills, rejected entries and P&L. Net P&L deducts fees and slippage. Dollar drawdown includes available intraday marks. Win rate counts closed positions, including partial-entry unwinds; complete-entry and unresolved counts are shown separately.

**Overview** includes profit factor, average/best/worst trade, fees, slippage and monthly realized P&L. **Trade ledger** shows positions, legs and individual fills. **Risk & Greeks** shows signed, BTC-scaled Greeks, excursions, mark coverage and the legacy reserve estimate as a diagnostic only. **Compare** shows development and holdout variants. **Audit** records assumptions, missing data, rejected-entry attempts and source hashes. Rejection counters count attempts, not necessarily distinct days.

If exits remain unresolved, headline total P&L and ratios are unavailable; realized closed P&L is retained separately. Do not treat the displayed path as a fully closed portfolio. See [Methodology](methodology.md) for the engine contract.

## 12. IST and stored timestamps

Session controls, run creation times, ledger timestamps, chart labels and displayed fill evidence use IST (UTC+05:30). Saved configurations, API requests and raw exports retain UTC for reproducibility; importing them converts their times to IST once. The guide therefore displays 11:30 entry, 17:00 exit and 17:30 expiry. Same-date intraday sessions from 05:30 IST onward are currently supported; earlier starts and sessions crossing IST midnight need a future cross-date replay extension. Expiry times after midnight refer to the following IST date when converted from the contract’s UTC expiry date.

## 13. Relationship to the earlier research engine

Options Lab can reproduce the main intraday short-strangle and iron-condor studies from `BitcoinOptionsAlgo`: fixed BTC per leg, delta or OTM selection, DTE, IST entry and exit, entry retry, wing distance, minimum credit, credit-based target and stop, fees, slippage, and per-trade audit data. It also adds saved runs, custom legs, IV/trend filters, Greeks, and chronological delta/stop/target comparisons.

Some specialized rules from the earlier scripts are not yet controls in this UI: Supertrend-generated directional entries and flip exits, overnight hold-to-expiry settlement, minimum-hours-to-expiry selection, and a single experiment grid spanning entry time, OTM distance, and wing-width multipliers. Test those as separate UI configurations for now; do not assume the generic parameter experiment varies them.
