# Methodology and accounting

## Timeline and information set

1. For each configured UTC date, locate the indexed option and futures partitions. Missing pairs are explicitly recorded.
2. Consider entry once per minute in the configured entry window. Each candidate expiry and strike must already have an observed tick at the decision. Later-listed strikes cannot alter past selection.
3. Each leg requires a fresh entry-side print. Use the latest underlying tick at or before that option print to infer volatility; use the latest fresh underlying at the decision to evaluate its Greeks.
4. Apply selection, IV/return filters, estimated net credit, using only this past information. Capital-mode requests also apply collateral eligibility; the current UI uses fixed BTC sizing without that filter.
5. Submit independent leg orders. A sell uses maker-buyer prints; a buy uses taker-buyer prints. Only prints strictly after decision plus latency qualify.
6. Per-print capacity is `floor(contracts × participation_fraction)`, converted with `0.001 BTC / contract`. Sizes are whole contracts. Weighted fill prices include adverse premium slippage. Every fill incurs the configured fee and tax.
7. On complete entry, monitor fresh liquidation-side marks at each relevant option event. When delta exits are enabled, underlying trade events also trigger checks. Net liquidation P&L includes all entry fees, adverse closing slippage, and estimated closing fees.
8. A trigger submits close orders after latency; fills may be worse than the trigger. A partially filled exit gets one additional fill window. No post-expiry or next-session prints can fill an order.
9. An incomplete entry is not erased: cancel the remainder at its timeout and attempt to unwind the filled exposure. A failed unwind/exit is an unresolved position and halts later entries.

One entry opportunity window and at most one entered position per date; no re-entry after a filled position. The model does not simulate stops during the initial leg-filling interval or reconcile a missed stop retrospectively.

## Pricing and Greeks

Black–Scholes European options, ACT/365 time to expiry, zero dividend yield, configurable continuous risk-free rate. Implied volatility is a bounded monotonic solve between 0.0001 and 10.0. Premiums at/below discounted intrinsic value or at/above their no-arbitrage upper bound are rejected. There is no invented volatility fallback.

BTCUSD futures is a spot proxy. This is neither an official spot-index Greek nor an expiry-matched Black-76 forward Greek. Futures basis, asynchronous trades, spreads, and jumps can distort IV and delta. Each selection reports the observed option timestamp and age.

Per-leg delta is dimensionless; signed portfolio delta is BTC exposure. Gamma is signed premium curvature per USD underlying move squared, scaled by BTC quantity. Theta is USD per calendar day; vega is USD per one percentage-point volatility move. The ledger's entry Greeks are estimates at the **decision**, scaled by filled quantity. Intratrade Greek samples are stored approximately once per minute; actual risk checks are not restricted to that chart sampling rate.

## Cash accounting and return statistics

For each fill, cash flow is `+quantity × premium − fee` for a sell and `−quantity × premium − fee` for a buy. A closed position's net P&L is the sum of every entry and exit cash flow. Gross P&L adds back fees; it still includes execution slippage. Slippage is separately attributed as the adverse difference from source-print premiums, not subtracted a second time.

The fee for each fill is:

```text
min(BTC quantity × underlying × notional fee rate,
    BTC quantity × premium × premium cap rate) × (1 + fee tax rate)
```

Fee schedules are fixed user assumptions for the selected interval. Neither historical fee tier changes nor tax-law changes are inferred from the archive.

The current UI uses fixed BTC size: cumulative P&L begins at zero, and dollar drawdown includes the initial zero peak. Daily USD P&L ratios use a zero benchmark and √365 annualization; capital return percentages, CAGR and Calmar are absent. The legacy capital mode described below remains supported for reproducibility. In that mode, equity begins at starting capital, so a first losing trade contributes to drawdown. Intraday observed liquidation P&L and actual closing P&L enter the risk path. Ratios use UTC calendar daily returns, including zero-trade days, annualized over 365 days. Sharpe subtracts the configured annual rate divided by 365; Sortino uses the RMS negative excess returns across all days. Undefined ratios return null. CAGR requires at least 365 days; Calmar requires 30 days. Trade expected shortfall averages the worst `ceil(5% × closed trade count)` trades; it is not daily portfolio VaR.

An unresolved position suppresses headline metrics for affected periods. The sum of already closed trades is available separately; it does not represent the value of remaining exposure. Missing-source days remain flagged, and metrics on the rest of a run are partial-sample estimates. Development ranking rejects configurations with missing development dates, unresolved exposure, too few closed trades, or an undefined objective.

## Margin and multi-leg exposure

Defined-width condors/spreads reserve the maximum wing width multiplied by base BTC quantity, without offsetting estimated premium. Other structures reserve configured notional margin for every short leg. Only legacy capital mode requires reserve to fit the chosen fraction of current realized equity. In the current BTC-size UI, this reserve is a diagnostic; it does not block entries or resize positions. Long-leg offsets, changing collateral requirements, cross-margin, liquidation, and interim unhedged margin while legs fill are not modelled.

## Experiment selection

Grid axes are symmetric target delta, percentage credit stop, and percentage credit target. Configurations share the same data and execution assumptions. The date split is chronological. The objective is calculated only on development dates; the selected configuration's later-period results remain separately visible. No winner is assigned if every variant fails eligibility. Grid variants are counterfactual alternatives, not simultaneously executed portfolios; each gets its own participation budget.

Holdout P&L retains the original replay's sizing and entry decisions, then rebases reporting to initial capital. Prior development losses can affect holdout capital checks only in legacy capital mode; BTC-size mode applies no capital checks. This is a sequential strategy continuation, not an independently reset account or a walk-forward retraining exercise.

## Data provenance

Original CSVs remain unchanged. Ingestion rejects malformed/invalid observations, converts timestamps explicitly to nanoseconds, deduplicates identical rows within a UTC day, sorts stably, and writes Parquet partitions. Without unique trade IDs, identical legitimate prints may be removed conservatively. Source hashes, quality counters, coverage, exact configuration, engine version, and fill evidence accompany each exported experiment.

## References

- [Delta options guide: symbols, expiry and settlement](https://guides.delta.exchange/delta-exchange-user-guide/derivatives-guide/options-guide)
- [Delta fee calculation and contract lot sizing](https://www.delta.exchange/support/solutions?articleId=80001177864)
- [Options Industry Council: option price behavior](https://www.optionseducation.org/referencelibrary/faq/option-price-behavior)

These references explain conventions; they do not establish historical parameter values for each archive date. The simulator intentionally closes before expiry because the official settlement index is absent.
