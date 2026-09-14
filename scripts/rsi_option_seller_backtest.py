#!/usr/bin/env python3
"""Run RSI-versus-RSI-SMA directional Bitcoin option-selling research."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.options_lab.rsi_option_seller import RsiOptionConfig, run


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Sell BTC puts when RSI is above its RSI-SMA; sell calls when below.')
    p.add_argument('--data-root', type=Path, default=Path.home()/'Desktop/BitcoinFNOData')
    p.add_argument('--output', type=Path, default=ROOT/'outputs/rsi_option_seller')
    p.add_argument('--cache', type=Path, default=ROOT/'data/options_lab_cache')
    p.add_argument('--start', default='2024-04-01')
    p.add_argument('--end', default='2026-07-31')
    p.add_argument('--timeframes', default='5m,10m,15m,30m,1h')
    p.add_argument('--rsi-period', type=int, default=14)
    p.add_argument('--rsi-sma-period', type=int, default=50)
    p.add_argument('--quantity-btc', type=float, default=1.0)
    p.add_argument('--otm-pct', type=float, default=1.0)
    p.add_argument('--otm-tolerance-pct', type=float, default=1.0)
    p.add_argument('--min-hours-to-expiry', type=float, default=16.0)
    p.add_argument('--max-days-to-expiry', type=float, default=7.0)
    p.add_argument('--expiry-buffer-hours', type=float, default=2.0)
    p.add_argument('--expiry-time-ist', default='17:30')
    p.add_argument('--slippage-pct', type=float, default=1.0)
    p.add_argument('--fee-pct', type=float, default=0.01)
    p.add_argument('--fee-cap-pct', type=float, default=3.5)
    p.add_argument('--tax-pct', type=float, default=18.0)
    p.add_argument('--latency-sec', type=float, default=1.0)
    p.add_argument('--max-execution-delay-min', type=float, default=15.0)
    p.add_argument('--entry-mark-max-age-sec', type=float, default=300.0)
    p.add_argument('--exit-price-max-age-sec', type=float, default=21600.0)
    p.add_argument('--underlying-max-age-sec', type=float, default=60.0)
    return p


def main() -> None:
    args = parser().parse_args()
    config = RsiOptionConfig(data_root=args.data_root.expanduser().resolve(), output_dir=args.output.expanduser().resolve(),
        cache_dir=args.cache.expanduser().resolve(),
        start=args.start, end=args.end, timeframes=tuple(x.strip() for x in args.timeframes.split(',') if x.strip()),
        rsi_period=args.rsi_period, rsi_sma_period=args.rsi_sma_period, quantity_btc=args.quantity_btc,
        otm_pct=args.otm_pct, otm_tolerance_pct=args.otm_tolerance_pct,
        min_hours_to_expiry=args.min_hours_to_expiry, max_days_to_expiry=args.max_days_to_expiry,
        expiry_buffer_hours=args.expiry_buffer_hours, expiry_time_ist=args.expiry_time_ist,
        slippage_pct=args.slippage_pct, fee_pct=args.fee_pct, fee_cap_pct=args.fee_cap_pct,
        tax_pct=args.tax_pct, latency_sec=args.latency_sec,
        max_execution_delay_min=args.max_execution_delay_min,
        entry_mark_max_age_sec=args.entry_mark_max_age_sec,
        exit_price_max_age_sec=args.exit_price_max_age_sec,
        underlying_max_age_sec=args.underlying_max_age_sec)
    summary, paths = run(config, lambda message: print(message, flush=True))
    print('\nRESULTS (USD)')
    print(summary[['variant','trades','net_pnl','max_drawdown','sharpe','win_rate','fees','slippage']].to_string(index=False))
    print('\nREPORT FILES')
    for name, path in paths.items():
        print(f'{name}: {path}')


if __name__ == '__main__':
    main()
