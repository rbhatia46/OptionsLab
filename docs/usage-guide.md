# Options Lab usage guide

A practical guide to testing Bitcoin option-selling ideas, with one complete example and a reference for every control.

## 1. Open the app and confirm the data

1. Double-click **Start Options Lab.command** in your OptionsLab folder. The first launch creates an isolated Python environment and installs the dependencies if needed. Leave the Terminal window open while using the app. Press Control-C in that window to stop the server.
2. Open **http://127.0.0.1:8765/** in your browser. If the server is already running, the launcher opens it instead of starting a second copy.
3. Check the archive strip near the top. With the supplied archive it should show **28 monthly option files**, spanning **2024-04 through 2026-07**. This is the file range, not a guarantee that every day or strike is present.
4. Click **Data & coverage**. Check that the month you intend to test has both an options file and a futures file.
5. Return to **Strategy workbench**. The builder is on the left and results are on the right. On a smaller screen they stack vertically. Scroll inside the builder on a desktop to reach its lower sections.

The app automatically reads `~/Desktop/BitcoinFNOData/options_data/BTC_YYYY-MM.csv` and the matching `futures_data/BTCUSD_YYYY-MM.csv`. You do not upload files through the UI. To use a different directory, stop the app and launch it with `--data-root /path/to/BitcoinFNOData`.

The first run against a month indexes its full CSV files into a local cache. This can take longer than the actual replay. Further runs on that month reuse the cache, including when you change dates or strategy conditions. Data and runs remain on your computer.

## 2. The normal research workflow

1. Write a precise idea: which legs to sell/buy, when to enter, how much to trade, and what causes an exit.
2. Select a small date range and a single configuration to check that the rules mean what you intended.
3. Run the test, then inspect **Audit** and **Trade ledger** before judging P&L.
4. Confirm the selected strikes, decision Greeks, quantities, individual fills, and exit reasons.
5. Expand the date range and test different market periods. A seven-day example is a functionality check, not evidence of a durable trading edge.
6. Change one variable at a time, or use the built-in parameter grid for delta, stop, and profit target.
7. Compare development and holdout results. Save the configuration and export evidence for the variants you want to retain.

This version uses a structured builder. You do not need Python for standard or custom-leg strategies. It does not compile an arbitrary sentence into new strategy logic; conditions not represented by the controls require an engine extension.

### Start from the strategy library

At the top of **Strategy workbench**, use **Start with an idea**. The first three cards are visible immediately; **Show all 9 ideas** expands the library. Category buttons filter the cards, and **Hide ideas / Browse ideas** collapses or reopens the library.

1. Pick an idea and read its legs, exit rules, and caveat.
2. Click **Load strategy**. This replaces **every builder input**, including dates, size, filters, costs, custom legs, and experiment settings. Save your current configuration first if you want to keep it.
3. The page moves to the populated builder. Review **Session & sample**, **Exits & risk**, and **Execution & model assumptions**. Edit any rule you want to test.
4. Click **Run backtest**. Loading a card only stages inputs; it does not start a run. Any existing results remain labelled with their original run until the new result is ready.
5. For **Delta × stop comparison**, the Parameter experiment section opens automatically. Inspect **Compare** after completion.

| Starting idea | Preloaded rules | What to explore |
| --- | --- | --- |
| 20Δ short strangle | Sell 0.20-delta put and call; 50% profit target, 100% credit-loss stop. | Baseline two-sided premium selling. |
| 20Δ iron condor | Same shorts, with long wings $1,000 farther out. | Effect of protective wings and their fill costs. |
| Bullish put credit spread | Sell 0.25-delta put, buy a put $1,000 lower; trailing 1h move at least 0%. | Directional entry filtering. |
| 15Δ wider strangle | Sell 0.15-delta put and call, with 0.05 delta tolerance. | Lower target deltas under the same exits. |
| ATM short straddle | Sell a put and call at a common near-ATM strike; 25% target, 100% stop. | Near-ATM premium selling. Delta targets do not select its strike. |
| Bearish call credit spread | Sell 0.25-delta call, buy a call $1,000 higher; trailing 1h move at most 0%. | The opposite directional filter. |
| Delta-selected wings | Custom legs: sell 0.25-delta put/call, buy 0.10-delta put/call, ratios 1, tolerance 0.04. | Choosing protective legs by delta rather than strike distance. Custom margin uses the per-short reserve. |
| Weekend short strangle | Baseline 0.20-delta strangle on weekends, June 1–14, 2026. | Calendar filtering; the example has only four eligible calendar days. |
| Delta × stop comparison | Deltas 0.15/0.20, stops 100%/150%, target 50%, June 1–14; 70% development, Sharpe objective, minimum 3 development trades. | A four-variant experiment with a separate chronological holdout. |

All cards use 0.01 BTC per base leg, $10,000 initial capital, 0 DTE, a 06:00 UTC entry and an 11:30 UTC time exit. Single ideas default to June 1–7, 2026 unless noted above. Shared costs are 1% premium slippage, 10% participation, 1-second latency, a 300-second fill timeout, a 0.01% notional fee capped at 3.5% of premium, and 18% tax on fees. These are editable assumptions. Other shared controls follow the detailed example below.

These templates express research questions; they have not been selected as profitable strategies. A valid configuration can produce skipped entries, partial fills, or unresolved exits. Inspect Audit and extend the sample before interpreting performance. Switching to a standard idea resets the hidden custom editor to the default two short legs.

## 3. Complete example: sell a 0.20-delta intraday strangle

**Question:** What happened when I attempted to sell a roughly 0.20-delta put and call each day, at 0.01 BTC per leg, with a 50% credit profit target and a 100% credit loss stop?

This is an example of using the software, not a recommended trading strategy, fee schedule, or position size.

### Step 1 — Load a known starting configuration

Click **Load the guide example** in the app header. It fills the controls below and switches to a single run. It does not start the backtest or place orders.

Alternatively, download the example configuration from the guide page, open **Run history → Import configuration**, and select that JSON file. To enter the configuration manually, use every value in Steps 2–6; a previously saved browser draft may have different settings.

### Step 2 — Set the structure and size

| Field | Enter or select | Meaning in this example |
| --- | --- | --- |
| Strategy name | Guide example · 20-delta short strangle | A label for run history; it does not alter calculations. |
| Structure | Short strangle | Sell one put and one call of the same expiry. |
| Selection method | Absolute delta | Select by model-estimated delta, rather than a fixed strike distance. |
| Expiry target (DTE) | 0 | Aim for an option expiring on the entry date. |
| Call delta | 0.20 | Target an individual call delta of approximately +0.20. |
| Put delta | 0.20 | Enter the absolute value: target an individual put delta of approximately −0.20. |
| Delta tolerance | 0.08 | Each selected absolute delta must be within 0.08 of its target: 0.12–0.28 here. |
| OTM distance (%) | 1 | Ignored because this example uses Absolute delta. |
| Wing width (USD) | 1000 | Ignored because a short strangle has no protective wings. |
| BTC per leg | 0.010 | Ten 0.001-BTC contracts for each leg, if fully filled. This is not the premium paid or the capital balance. |

The option's quoted delta and the position's delta have different signs. Selling a +0.20-delta call creates negative exposure; selling a −0.20-delta put creates positive exposure. Equal sizes can approximately offset at entry, but that does not eliminate gamma, volatility, or tail risk. A 0.20 delta is not a guaranteed 20% probability or an 80% win rate.

### Step 3 — Set the date range and session

Open **Session & sample** and enter:

| Field | Value |
| --- | --- |
| From | 2026-06-01 |
| Through | 2026-06-07 |
| Entry decision | 06:00 |
| Time exit | 11:30 |
| Entry retry window (min) | 30 |
| Trade days | Every day |

Dates are inclusive. All times are **UTC**. For an India-based trader, 06:00 UTC is **11:30 IST**, and 11:30 UTC is **17:00 IST**. Enter the UTC values in the app; do not enter the IST equivalents into these fields.

At 06:00, the engine looks for eligible legs using only observations already available. If no configuration qualifies, it tries again once per minute through 06:30. Once any entry fills, the engine does not open another position that day. The 11:30 value is an exit decision time; actual close fills happen later according to latency and liquidity.

### Step 4 — Set exits, capital, and reserve

Open **Exits & risk**:

| Field | Value |
| --- | --- |
| Profit target (% credit) | 50 |
| Stop loss (% credit) | 100 |
| Minimum credit (USD) | 1 |
| Max loss per trade (USD) | 0 |
| Portfolio delta cap (BTC) | 0 |
| Initial capital (USD) | 10000 |
| Margin reserve (% notional) | 20 |
| Max capital allocated (%) | 80 |

Zero disables the optional cash-loss and delta exits. The percentage stop and target remain active.

For illustration, if the two legs actually collect **$10** of total entry credit, the target triggers when estimated net liquidation P&L reaches **+$5**, and the percentage stop triggers at **−$10**. This P&L includes fees and adverse closing slippage, so the trigger is not exactly the same as buying back the position at half or twice the original premium. Triggered orders can fill at worse prices; neither stop is a guaranteed loss ceiling.

The $10,000 capital is the denominator for returns and the basis for the reserve check. With a hypothetical $70,000 BTC price, two short legs of 0.01 BTC each and a 20% notional reserve require approximately **$280** of research reserve. That fits the 80% × $10,000 = **$8,000** allocation ceiling. This calculation is not Delta Exchange's actual margin or liquidation formula.

### Step 5 — Keep the entry filters broad

Open **Entry filters**:

| Field | Value |
| --- | --- |
| Minimum IV (%) | 0 |
| Maximum IV (%) | 500 |
| Min trailing 1h move (%) | −100 |
| Max trailing 1h move (%) | 100 |

The −100 to +100 move range disables the trend filter. The IV range permits valid model IVs up to 500%; it does not make missing or invalid IV observations eligible. Every selected leg still needs valid, fresh data.

### Step 6 — Enter explicit execution and model assumptions

Open **Execution & model assumptions**:

| Field | Value |
| --- | --- |
| Premium slippage (%) | 1 |
| Volume participation (%) | 10 |
| Latency (seconds) | 1 |
| Fill timeout (seconds) | 300 |
| Option max age (seconds) | 300 |
| Underlying max age (sec) | 60 |
| Fee (% notional / fill) | 0.01 |
| Fee cap (% premium) | 3.5 |
| Tax on fees (%) | 18 |
| Risk-free rate (%) | 0 |
| Expiry hour (UTC) | 12 |

A 1% slippage input makes a sell execute at 99% of a qualifying print's premium and a buy at 101%. It is a percentage of premium, not a one-dollar cost or one percent of BTC notional.

At 10% participation, a 100-contract print supplies capacity for 10 contracts; a 9-contract print supplies zero after rounding down to whole contracts. Orders may need several eligible prints. These settings deliberately allow partial fills rather than assuming the full position always trades.

The fee, cap, tax, and expiry inputs are explicit research assumptions. They are not automatically inferred or updated for each historical date.

Open **Parameter experiment** and select **Mode = Single configuration**. The grid fields do not affect this run.

### Step 7 — Run and watch progress

1. Click **Run backtest**.
2. The status changes to queued/running. The progress message names the month being indexed or the day being replayed.
3. Wait until **COMPLETED** appears. Only one job runs at a time. **Cancel run** requests cancellation at the next processing checkpoint; it does not publish a partial experiment as a finished result.
4. The validated example on the supplied archive completed with seven closed positions. Counts can differ if the data, configuration, or engine version changes. A closed position can be an early unwind of a partial entry; seven closed positions do not necessarily mean seven fully entered strangles.

### Step 8 — Inspect evidence before drawing conclusions

1. Open **Audit**. Check missing source dates, incomplete entries, invalid Greek observations, source fingerprints, and skipped-entry reasons. Some skip counters count minute-by-minute attempts, not days.
2. Open **Trade ledger**. Click a date. Read its decision time, last entry-fill time, and exit trigger time. Inspect which strikes were actually selected and their decision deltas; they need not be exactly 0.20.
3. Expand **Individual fill evidence & risk path**. Check `planned_legs` for requested versus filled BTC, including any leg that received no fills. Inspect each print's timestamp, role implied by buy/sell, raw price, adjusted price, quantity, and fee.
4. Check the exit reason. A profit target, stop, time exit, or partial-entry unwind represents a different path through the rules.
5. Open **Risk & Greeks**. Examine fresh-mark coverage, incomplete entries, unresolved positions, MAE/MFE, and portfolio Greek exposure.
6. Return to **Overview**. Now read net P&L, drawdown, win rate, costs, and the return ratios. A high win rate with a few large losses can still lose money.
7. Click **Save configuration** to download the current builder controls. Click **Full result + configuration** for the exact executed rules and evidence, or **Trade ledger CSV** for the currently viewed variant.

A warning about a small sample is expected for this example. If you see **UNRESOLVED EXPOSURE**, inspect the position rather than treating unavailable ratios as zero. The engine retains the exposure and stops later entries.

### Step 9 — Extend the same example into a parameter comparison

After checking the single run, change only these fields:

| Field | New value |
| --- | --- |
| Strategy name | Delta / stop experiment · June holdout |
| Through | 2026-06-14 |
| Mode | Parameter grid + chronological holdout |
| Symmetric deltas | 0.15, 0.20 |
| Stop loss values (%) | 100, 150 |
| Profit targets (%) | 50 |
| Objective | Sharpe |
| Development sample (%) | 70 |
| Min development trades | 3 |

Keep all other fields as in the example. Click **Run backtest**, then **Compare**. This produces **2 × 2 × 1 = 4 variants**. The first nine dates, June 1–9, form development; June 10–14 is the holdout. The split uses `floor(calendar days × development fraction)`.

A star identifies the eligible variant selected using **development Sharpe only**. Click any variant number to display its full-sample metrics and ledger. The comparison table continues to show its development and holdout statistics separately. A winner can have a negative Sharpe; the star means best on the chosen objective among eligible variants, not profitable or suitable to trade. If no variant qualifies, there is no winner.

Three development trades and a fourteen-day window are sufficient to demonstrate the controls, not to establish statistical confidence. For real research, use a larger sample, a meaningful minimum trade count, more than one market regime, and a holdout you do not repeatedly tune against.

## 4. Field reference: structure and leg selection

Values marked “ignored” are preserved in the form but do not affect that structure. Backend validation still checks that supplied numbers are in their allowed ranges.

| Field or option | What it does and when it applies |
| --- | --- |
| Strategy name | Human-readable run label, 1–80 characters. Names do not define strategy behavior. |
| Short strangle | Sell one call and one put with different, correctly ordered strikes. Same expiry and base BTC quantity. No protective long legs. |
| Short straddle | Sell the call and put at a common strike nearest the current futures-price proxy. Delta/OTM selection fields do not choose its strike. |
| Iron condor | Sell the selected call and put; buy a farther-out call and put at least the specified wing width away. Four independent leg orders. |
| Call credit spread | Sell a selected call and buy a higher-strike call at least one wing width away. |
| Put credit spread | Sell a selected put and buy a lower-strike put at least one wing width away. |
| Short call | Sell only the selected call. Put-delta and wing settings are ignored. |
| Short put | Sell only the selected put. Call-delta and wing settings are ignored. |
| Custom option legs | Build 1–6 same-expiry legs with the row editor. At least one leg must be short and estimated aggregate credit must be positive. Each leg always uses its own delta target. |
| Selection method: Absolute delta | Choose eligible short legs closest to their call/put absolute-delta targets within tolerance. Protective wings use strike distance. |
| Selection method: OTM distance (%) | Call strike must be at least the specified percent above the current underlying proxy; put strike at least that percent below. The nearest eligible strike satisfying the distance is selected. Delta targets and tolerance do not control these strikes. |
| Expiry target (DTE) | Integer calendar days, 0–30. Choose the first already-observed expiry on/after that target date, at most three days later. Even DTE 0 can use a later expiry if the target expiry has not been observed; check the ledger. All holdings remain intraday. |
| Call delta | Absolute target, 0.01–0.95. Used for standard delta-selected short calls. It is the option's delta before applying the short-position sign. |
| Put delta | Absolute target, 0.01–0.95; enter a positive number. Used for standard delta-selected short puts. |
| Delta tolerance | Maximum absolute distance from the desired delta, 0.005–0.30. Wider tolerance admits more strikes but changes what “0.20 delta” means. Applies to custom-leg delta targets too. |
| OTM distance (%) | 0–50, expressed as a percent of the current underlying proxy. Input 1 means 1%, not a $1 strike gap. Used only by standard OTM selection. |
| Wing width (USD) | Minimum strike-point distance from short strike to long protection, 1–100,000. Actual width may be larger when exact strikes or eligible quotes are unavailable. Used by condors and credit spreads. |
| BTC per leg | Base exposure, 0.001–100 BTC, in multiples of 0.001. Standard legs use this quantity; custom ratios multiply it. Capital does not automatically resize the quantity. |

### Custom-leg row controls

| Control | Meaning |
| --- | --- |
| Side: Sell / Buy | The direction of the option position. Sell collects premium; Buy pays premium. |
| Type: Put / Call | The option type for that row. |
| Absolute delta | Per-row target from 0.01 to 0.95. Uses the common Delta tolerance. |
| Ratio | Integer from 1 to 10; row BTC = base BTC per leg × ratio. For base 0.01 and ratio 2, request 0.02 BTC. |
| Add option leg | Add another editable leg, up to six. This stages a configuration; it does not run it. |
| Remove leg | Delete that row. At least one valid short leg is required to run. |

Legs are selected in row order. The same symbol cannot be selected twice, even for opposing rows; the engine does not net duplicated symbols into a single position. More legs increase the opportunities for partial fills. Custom structures do not enable overnight holding, different expiries per leg, rolling, or dynamic hedging.

## 5. Field reference: session and sample

| Field or option | Meaning |
| --- | --- |
| From / Through | Inclusive UTC calendar dates, in YYYY-MM-DD form. The range must be ordered and no longer than 1,095 days. Missing source dates are reported. |
| Entry decision | Earliest daily decision time, HH:MM UTC. Selection cannot use future prints. |
| Time exit | Submit closing orders at this time if no earlier exit has triggered. Actual exit fills occur later. |
| Entry retry window (min) | Integer 0–120. Retry eligibility once per minute from Entry decision through this many minutes later. Zero checks once. It is not an order-fill timeout and does not allow re-entry after a filled trade. |
| Every day | Consider all seven days of the week. |
| Weekdays | Consider Monday through Friday, using UTC dates. |
| Weekends | Consider Saturday and Sunday, using UTC dates. |

The entry window plus one latency/fill window must end before Time exit. Time exit must leave room for two fill windows and latency before the configured expiry hour for DTE 0, or before UTC midnight for longer DTE. Each actual order is also bounded by its contract's expiry and the session boundary. The validator uses conservative session timing; a configuration can be rejected even if some hypothetical days could fill faster.

## 6. Field reference: exits and risk

| Field | Meaning |
| --- | --- |
| Profit target (% credit) | 1–100. Close when estimated net liquidation P&L reaches this percent of actual aggregate entry credit. Applies to the whole structure, not separately to each leg. |
| Stop loss (% credit) | 1–1,000. Close when estimated net liquidation P&L falls to minus this percent of actual credit. Input 100 means lose one credit, not buy back at 100% of the entry premium. |
| Minimum credit (USD) | 0–10,000,000. Require at least this much estimated aggregate credit before entry. Credit must remain positive even when this field is zero. If completed fills change it below the threshold, unwind and retain the trade. |
| Max loss per trade (USD) | Optional absolute net-loss trigger, 0–1,000,000,000. Zero disables it. This is a per-position trigger, not a global account drawdown stop. |
| Portfolio delta cap (BTC) | Optional trigger on absolute signed net portfolio delta, 0–1,000 BTC. Zero disables it. Input 0.01 means 0.01 BTC portfolio exposure, not a 0.01 individual option delta. It closes the whole structure rather than hedging. |
| Initial capital (USD) | Starting equity, 100–10,000,000,000 USD. Used in returns, drawdown percentages, and reserve checks. Does not automatically determine order size. |
| Margin reserve (% notional) | 1–100. For naked/custom short structures, reserve this percentage of underlying notional for each short leg. Standard condors/spreads instead reserve the maximum wing width × quantity. This is a research allocation model. |
| Max capital allocated (%) | 1–100. Skip entry if the required reserve exceeds this fraction of current realized equity. It is not a max drawdown limit or automatic position scaling. |

If multiple risk rules fire at one event, the engine labels the exit in priority order **delta exit → cash stop → credit stop**; the profit target applies only if no risk exit fired. All qualifying triggers initiate the same independent closing-order process.

## 7. Field reference: entry filters

| Field | Meaning |
| --- | --- |
| Minimum IV (%) | 0–1,000. Lower bound on every selected leg's inferred annualized IV. Input 40 means 40% IV. |
| Maximum IV (%) | 1–1,000. Upper bound on every selected leg's IV. Must be at least the minimum. Applies to protective wings too. |
| Min trailing 1h move (%) | −100 to +100. Lower bound for the one-hour return of the futures-price proxy. For example, 0 admits non-negative moves when used with a broad upper bound. |
| Max trailing 1h move (%) | −100 to +100. Upper bound for the same prior one-hour return. Must be at least the minimum. |

The trend filter compares fresh as-of underlying prices at the decision and one hour earlier; it does not use the following hour. When active, insufficient history skips entry. This is a simple return filter, not Supertrend, an EMA crossover, IV rank, or implied-versus-realized volatility filtering. IV is inferred from observed prices; those other signals are not implemented.

## 8. Field reference: execution and model assumptions

| Field | Meaning |
| --- | --- |
| Premium slippage (%) | 0–50. Adverse adjustment to each source print's premium: reduce sells and increase buys. Costs are already included in net P&L and separately attributed. |
| Volume participation (%) | 1–100. Maximum fraction of each eligible print's contract volume available to the simulated order, rounded down to whole contracts. Each grid variant has its own counterfactual budget. |
| Latency (seconds) | 0–60. Wait after each decision before eligible fills begin; fills are strictly later than decision + latency, including when latency is zero. |
| Fill timeout (seconds) | 1–600. Time available after latency to accumulate a fill. Incomplete entries are unwound; incomplete exits receive one additional window. It does not extend the strategy entry-retry window. |
| Option max age (seconds) | 1–1,800. Maximum age of an as-of option print for selection and liquidation marks. Increasing it admits older information and can distort IV, triggers, and drawdown. |
| Underlying max age (sec) | 1–600. Maximum age of a futures tick used for IV, Greeks, marks, filters, and fill fees. Fills lacking a fresh underlying observation are ineligible. |
| Fee (% notional / fill) | 0–1. Per-fill fee rate on BTC quantity × underlying price. Input 0.01 means 0.01%, or one basis point. |
| Fee cap (% premium) | 0–100. Cap the fee at this percentage of traded premium; the smaller notional-based and premium-based fees is used. Zero makes the capped fee zero; it does not mean “no cap.” |
| Tax on fees (%) | 0–100. Multiplier applied to the capped fee, not to notional, premium, or P&L. Input 18 multiplies fees by 1.18. This does not model income tax on trading profits. |
| Risk-free rate (%) | −10 to 50. Continuous annual rate for Black–Scholes and annual excess-return benchmark for Sharpe/Sortino. Input 5 means 5%. It does not accrue cash interest to equity. |
| Expiry hour (UTC) | Integer 1–23. Assumed hour of expiry on the date encoded in the symbol. The example uses 12. No official settlement-price calculation occurs. |

The underlying input is BTCUSD futures used as a **spot-price proxy**. Greeks are estimates from European Black–Scholes with zero dividend yield and ACT/365 time. The model rejects invalid implied-volatility solves instead of inserting a fixed IV. Buyer-role prints proxy marketable sells and buys; there are no bid/ask quotes, queue positions, or guaranteed multi-leg fills in this dataset.

## 9. Field reference: parameter experiment

| Field or option | Meaning |
| --- | --- |
| Mode: Single configuration | Run the controls above once. Grid values, objective, and split do not select a winner. |
| Mode: Parameter grid + chronological holdout | Run the Cartesian product of the three grid lists, up to 36 combinations. Requires at least ten calendar days, standard delta selection, and a structure other than custom or straddle. |
| Symmetric deltas | Comma-separated targets, 0.01–0.95. Each value replaces both call and put targets for that variant. One-sided structures use only the relevant side. |
| Stop loss values (%) | Comma-separated credit-loss stops, 1–1,000. Override the single-run percentage stop. |
| Profit targets (%) | Comma-separated percentage-credit targets, 1–100. Override the single-run target. |
| Objective: Sharpe | Prefer the largest development daily-return Sharpe. Undefined values cannot win. |
| Objective: Net P&L | Prefer the largest development net dollars after execution costs. It does not impose a separate risk penalty. |
| Objective: Calmar | Prefer annualized return divided by observed maximum percentage drawdown. At least 30 development calendar days and nonzero drawdown are needed for a defined value. |
| Objective: Lowest drawdown | Prefer the smallest development observed dollar drawdown. It does not also maximize profit; inspect both. |
| Development sample (%) | 50–90. First fraction of all calendar dates used to rank variants; remaining dates form holdout. This splits dates, not number of filled trades. |
| Min development trades | Integer 1–10,000. Required closed positions on development dates. Closed partial-entry unwinds count as positions. |

Variants with missing development dates, unresolved development exposure, non-positive final development equity, too few trades, or an undefined objective cannot win. The holdout is never used for winner selection. Identical objective scores break ties by grid order.

All variants retain the original replay's sequential capital checks; holdout reporting rebases performance to initial capital but does not independently rerun it with a fresh account. The grid is not adaptive walk-forward retraining. The app does not simultaneously optimize return, Sharpe, and drawdown; choose one ranking objective and inspect the remaining columns.

## 10. What each result means

| Result or view | How to read it |
| --- | --- |
| Net P&L | Sum of closed entry/exit cash flows after fees and slippage. Suppressed when open exposure prevents a complete account valuation. |
| Return on starting capital | Net P&L divided by configured starting capital. Not return on margin. |
| Max drawdown | Largest observed peak-to-trough loss including the initial capital peak and available intraday marks. Missing/stale marks and execution windows can hide a larger actual loss. |
| Sharpe ratio | Mean daily excess return divided by sample standard deviation, multiplied by √365. All calendar dates are included, including zero-trade dates. No claim of statistical confidence is implied. |
| Sortino | Similar return measure using downside deviation across all daily returns. A blank value means undefined, not zero risk. |
| Win rate | Percentage of closed positions with strictly positive net P&L. Zero-P&L positions are not wins. |
| Profit factor | Sum of positive position P&Ls divided by absolute sum of negative position P&Ls. If no losses exist it is undefined and displayed as a dash, not a fabricated large number. |
| Average / best / worst trade | Net position P&L statistics, including closed partial-entry unwinds. |
| Total fees | Fees and configured fee tax across fills. |
| Slippage cost | Adverse fill adjustment from raw source premiums. It is already included in net P&L; do not subtract it again. |
| Monthly realized P&L | Closed-position net P&L grouped by UTC entry month. An unresolved position's remaining value is not included. |
| MAE | Most adverse observed net liquidation P&L during a position, also including its terminal closed P&L. Missing observations can hide worse excursions. |
| MFE | Most favorable observed net liquidation P&L, also including terminal closed P&L. No guarantee that the displayed mark could have been filled immediately. |
| Trade expected shortfall (95%) | Average of the worst 5% of closed positions, rounding the count up. It is not a daily portfolio VaR calculation. |
| Fresh mark coverage | Fraction of attempted risk events for which all necessary liquidation marks and underlying observations were fresh. Not the fraction of all seconds with valid quotes. |
| Peak reserve | Largest estimated entry collateral reserve across entered positions. Not the exchange's intraday margin high-water mark. |
| Portfolio delta | Signed BTC exposure from the selected option deltas and filled quantities. |
| Gamma | Signed portfolio sensitivity of delta to a USD change in the underlying proxy. |
| Theta / day | Signed model premium decay in USD per calendar day, scaled by filled quantities. |
| Vega / 1pt | Signed model value change in USD for a one-percentage-point change in IV, scaled by filled quantities. |
| Trade ledger | Position-level outcomes. Click a date for leg strikes, decision Greeks, and fill evidence. |
| Risk & Greeks | Excursions, tail statistics, mark coverage, reserves, incomplete/unresolved counts, and signed decision exposure. |
| Compare | Side-by-side development and holdout metrics for the grid. Clicking a row changes the active variant elsewhere in the results. |
| Audit | Source hashes/quality, exact executed configuration, missing dates, model limits, and skip counters. |

Per-leg Greeks shown in the ledger are per-option estimates at the decision. The portfolio table applies direction and filled BTC. The detailed JSON also contains sampled intratrade portfolio Greeks. A dash means the statistic cannot be calculated reliably under its definition or the position remains unresolved.

## 11. Saved configurations, history, and exports

| Action | What is saved or changed |
| --- | --- |
| Save configuration | Download the **current builder controls**. If you have edited them since the run, this can differ from the result's executed configuration. |
| Import configuration | Load a saved JSON configuration into the builder for review. It does not immediately run it. |
| Run history → Open result | Display that saved run. Does not overwrite your current builder draft. |
| Run history → Reuse rules | Copy that run's request into the builder. A sweep request stays a sweep unless you change Mode. |
| Full result + configuration | Download all variants, their exact executed settings, source fingerprints, trades, and audit information. |
| Trade ledger CSV | Export the currently viewed variant, including leg symbols, strikes, quantities, and decision Greeks. |
| Cancel run | Request cancellation of the current job at its next checkpoint. Does not create an apparently complete partial result. |
| Load the guide example | Replace the builder draft with the exact example preset. No job is submitted. |

Browser drafts persist locally in that browser. Executed runs persist in the server's local output directory and survive a server restart. If the server stops mid-run, that job is shown as interrupted on restart and can be rerun. Browser drafts are not automatically synchronized between browsers or machines.

## 12. Troubleshooting and interpretation

| What you see | Meaning and next action |
| --- | --- |
| Connection refused / failed to fetch | Start the app; keep its Terminal window open. Use the same port shown by the launcher. |
| No monthly files | Check the archive directory and required file names. Use `--data-root` if your directory differs. |
| Long indexing step | A selected month is being parsed, validated, and fingerprinted. Later runs reuse its daily cache. |
| No eligible short leg / custom leg / wing | Required strikes, valid IV, delta tolerance, or fresh role-specific prints were unavailable. Inspect assumptions before relaxing a filter. |
| Minimum credit | The selected structure's estimated total premium is below the threshold. The threshold is in total dollars at the configured BTC size. |
| Stale underlying / missing trend history | No sufficiently recent futures observation at a required as-of timestamp. Increasing max age trades freshness for availability. |
| Insufficient margin reserve | The configured size's reserve exceeds the allocation ceiling. The engine skips; it does not silently reduce size. |
| Partial entry unwind | Some requested leg quantity did not fill. Filled exposure was unwound and its actual costs/P&L retained. Inspect `planned_legs`. |
| Credit changed unwind | Complete entry fills produced non-positive or too-low credit. The engine unwound and retained the outcome. |
| Unresolved exposure | At least one exit could not finish within the two windows. Later entries stop and headline account metrics are unavailable. Inspect remaining quantities in the ledger. |
| Missing source dates | The chosen range includes absent daily/monthly pairs. Headline estimates describe an incomplete sample; development variants with missing dates cannot win. |
| No eligible winner | Check minimum development trades, missing dates, unresolved exposure, and whether the chosen ratio is defined. A short Calmar sample is a common cause. |
| Small-sample warning | Fewer than 20 closed positions. Increasing the sample can improve evidence, but does not guarantee a reliable strategy. |
| Error about entry/exit timing | Shorten the retry or fill windows, or move decision times so full entry and exit windows fit before expiry/midnight. |

Reduce size or increase execution time only when those are assumptions you actually want to test. Do not relax participation, freshness, costs, or missing-data handling simply to make a result look attractive.

## 13. Current scope and deliberate limits

The app currently supports intraday, same-expiry option-credit structures and the listed filters/exits. It does not implement overnight holding, multi-expiry calendars, settlement to expiry, rolling, automatic delta hedging, futures funding, exchange liquidation, a global drawdown kill switch, option-leg-specific stops, re-entry after a filled position, arbitrary technical indicators, or arbitrary natural-language strategy execution.

The chart is based on trade-print liquidation proxies. A stop is monitored after the entry has finished, and drawdown between individual fills may be unobserved. This is a research workbench for testing explicit assumptions, not proof of achievable live returns.

For formulas and accounting details, read [Methodology](methodology.md). For contract/pricing context, see [Delta's options guide](https://guides.delta.exchange/delta-exchange-user-guide/derivatives-guide/options-guide), [Delta's fee calculation explanation](https://www.delta.exchange/support/solutions?articleId=80001177864), and [OIC's option-price behavior reference](https://www.optionseducation.org/referencelibrary/faq/option-price-behavior).
