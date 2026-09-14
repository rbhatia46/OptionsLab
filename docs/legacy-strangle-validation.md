# Legacy optimized strangle validation

OptionsLab includes a validation preset and script for the earlier `BitcoinOptionsAlphaStrat` optimized same-day short strangle. The benchmark covers 2024-04-01 through 2026-03-19 and uses:

- 2 BTC per leg
- same-day expiry at 17:30 IST
- entry checks at 13:00, 13:15, and 13:30 IST
- 0.75% OTM call and put strikes
- $125 minimum total credit
- 60% profit target and 200% stop, triggered on P&L before fees
- 17:00 IST time exit
- 1% adverse slippage per fill
- 0.01% notional fee capped at 3.5% of premium, plus 18% tax

Run the independent comparison with:

```sh
cd "/Users/rahulbhatia/Documents/ChatGPT/Quant Research Copilot/OptionsLab"
.venv/bin/python -u scripts/validate_legacy_strangle.py
```

The Research Workspace also contains **Validated 0.75% OTM strangle** under the **Validation** category. Unlike ordinary idea cards, this validation card deliberately loads the benchmark's 2 BTC position size and full historical date range.

The earlier report's Sharpe uses only days containing trades, and its maximum drawdown uses closed-trade equity. OptionsLab exposes those comparison metrics as `active_day_sharpe` and `closed_trade_max_drawdown`. Its main Sharpe includes every calendar day, while its main maximum drawdown includes observed intraday marked losses.
