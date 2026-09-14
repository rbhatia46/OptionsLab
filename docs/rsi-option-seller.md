# RSI versus RSI-SMA directional option seller

The standalone script `scripts/rsi_option_seller_backtest.py` tests five independent option-selling variants:

- 5-minute BTCUSD bars
- 10-minute BTCUSD bars
- 15-minute BTCUSD bars
- 30-minute BTCUSD bars
- 1-hour BTCUSD bars

For each timeframe, it calculates Wilder RSI(14) from completed IST-aligned futures bars and then calculates a 50-bar simple moving average of those RSI values. When RSI is above its RSI-SMA, the strategy sells a put. When RSI is below its RSI-SMA, it sells a call. It closes and changes sides when the state reverses. It also closes two hours before option expiry or at the end of the requested sample.

Each timeframe is backtested separately. The `combined` result sums all five variants, so it can represent five concurrent 1 BTC short-option positions. Do not interpret the combined row as a single 1 BTC strategy.

## Full-history command

From the OptionsLab directory, run:

```sh
.venv/bin/python -u scripts/rsi_option_seller_backtest.py \
  --data-root /Users/rahulbhatia/Desktop/BitcoinFNOData \
  --start 2024-04-01 \
  --end 2026-07-31 \
  --timeframes 5m,10m,15m,30m,1h \
  --rsi-period 14 \
  --rsi-sma-period 50 \
  --quantity-btc 1 \
  --otm-pct 1 \
  --otm-tolerance-pct 1 \
  --min-hours-to-expiry 16 \
  --max-days-to-expiry 7 \
  --expiry-buffer-hours 2 \
  --expiry-time-ist 17:30 \
  --slippage-pct 1 \
  --fee-pct 0.01 \
  --fee-cap-pct 3.5 \
  --tax-pct 18 \
  --latency-sec 1 \
  --max-execution-delay-min 15 \
  --entry-mark-max-age-sec 300 \
  --exit-price-max-age-sec 21600 \
  --model-exit-iv-max-age-sec 604800 \
  --underlying-max-age-sec 60 \
  --risk-free-rate-pct 0 \
  --output outputs/rsi_option_seller
```

The script reuses `data/options_lab_cache` by default. First-time months are indexed and fingerprinted; later runs reuse them.

## Outputs

The output directory contains:

| File | Contents |
| --- | --- |
| `report.md` | Human-readable strategy definition, results table, skipped events, and limitations. |
| `summary.csv` | Per-timeframe and combined market P&L before costs, net P&L, drawdown, Sharpe, Sortino, win rate, fees, and slippage. |
| `trades.csv` | Every option symbol, signal, strike, entry/exit timestamp, observed and executed premium, costs, P&L, and price source. |
| `daily_pnl.csv` | Daily realized P&L, cumulative P&L, and drawdown for every timeframe and the combined portfolio. |
| `config.json` | Exact configuration, skipped-event counters, and source-file fingerprints. |

## Default execution assumptions

- Position size is 1 BTC for each timeframe.
- The put or call strike targets 1% OTM and must remain within one percentage point of that requested distance.
- The selected contract must have at least 16 hours and no more than seven days to expiry.
- Entry uses a fresh option observation available before the signal for selection, followed by the first observed option trade after the signal plus latency within 15 minutes.
- If the RSI state changes before a pending entry fills, that entry is cancelled.
- Source-print volume is ignored. This is the full-size observed-price research model.
- Entry and exit premiums receive 1% adverse slippage.
- Each fill pays 0.01% of BTC notional, capped at 3.5% of option premium, plus 18% tax on that fee.
- An exit without a later observed print may use the latest observed option trade within six hours. If that also fails, Black-Scholes estimates the exit from the latest valid implied volatility observed within seven days, falling back to the entry implied volatility, and the futures price at the exit trigger. The trade ledger labels these cases `bounded_stale_exit_price` or `black_scholes_exit_proxy` and records the quote age.
- `summary.csv` and `report.md` show `status` and `tested_through_ist`. If an exit still cannot be valued, the timeframe is marked incomplete and its headline performance is left blank instead of presenting a partial replay as a full-history result.
- RSI warm-up data is loaded before the requested start where the archive permits. Trades never begin before the requested start.

Drawdown is based on realized daily P&L because this standalone report does not construct a continuous option mark-to-market path. The data contains trades rather than an order book, so the results do not establish that 1 BTC could have filled at the reported prices. Funding, spread, depth, margin liquidation, assignment, and official settlement are not modelled.
