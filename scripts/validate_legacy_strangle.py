#!/usr/bin/env python3
"""Reproduce and compare the documented BitcoinOptionsAlphaStrat strangle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.options_lab.engine import DEFAULTS, run_experiment

REFERENCE = dict(trades=453, net_pnl=35143.33, fees=9445.72, win_rate=84.55,
                 profit_factor=1.85, closed_trade_max_drawdown=2173.82,
                 active_day_sharpe=4.11)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Validate OptionsLab against the earlier optimized strangle.')
    p.add_argument('--data-root', type=Path, default=Path.home()/'Desktop/BitcoinFNOData')
    p.add_argument('--legacy-trades', type=Path,
        default=Path.home()/'Downloads/BitcoinOptionsAlphaStrat-main 2/optimized strangle/recommended_strategy_trades_simple.csv')
    p.add_argument('--output', type=Path, default=ROOT/'outputs/legacy_strangle_validation')
    return p


def config() -> dict:
    return {**DEFAULTS,
        'name': 'Validated legacy · 0.75% OTM short strangle',
        'sizing_mode': 'btc', 'execution_mode': 'price', 'strategy_family': 'options',
        'structure': 'strangle', 'selection': 'otm', 'dte': 0,
        'otm_pct': .75, 'otm_tolerance_pct': 10., 'quantity_btc': 2.,
        'start': '2024-04-01', 'end': '2026-03-19',
        'entry_time': '07:30', 'exit_time': '11:30', 'entry_window_min': 30,
        'entry_check_interval_min': 15, 'days': 'all',
        'take_profit_pct': 60., 'stop_loss_pct': 200., 'risk_trigger_basis': 'before_fees',
        'min_credit': 125., 'max_loss_usd': 0., 'delta_exit': 0.,
        'slippage_pct': 1., 'latency_sec': 0., 'fill_timeout_sec': 300.,
        'max_age_sec': 1800., 'exit_price_max_age_sec': 21600., 'spot_age_sec': 600.,
        'fee_pct': .01, 'fee_cap_pct': 3.5, 'tax_pct': 18., 'rate_pct': 0.,
        'expiry_hour': 12, 'mode': 'single'}


def main() -> None:
    args = parser().parse_args()
    out = args.output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    last_bucket = [-1]
    def progress(message: str, fraction: float) -> None:
        bucket = int(fraction*10)
        if bucket > last_bucket[0]:
            last_bucket[0] = bucket
            print(f'{fraction:6.1%} {message}', flush=True)

    result = run_experiment(config(), args.data_root.expanduser().resolve(),
                            ROOT/'data/options_lab_cache', progress)
    run = result['runs'][0]
    metrics = run['metrics']
    old = pd.read_csv(args.legacy_trades.expanduser().resolve())
    new = pd.DataFrame(dict(trade_date=t['date'], net_pnl_usd=t['net_pnl'],
        entry_time_ist=pd.Timestamp(t['decision_time']).tz_convert('Asia/Kolkata').isoformat(),
        short_call_option=next(l['symbol'] for l in t['legs'] if l['type']=='C'),
        short_put_option=next(l['symbol'] for l in t['legs'] if l['type']=='P'),
        exit_reason=t['exit_reason']) for t in run['trades'])
    overlap = old.merge(new, on='trade_date', suffixes=('_reference','_optionslab'))
    same_strikes = ((overlap.short_call_option_reference==overlap.short_call_option_optionslab) &
                    (overlap.short_put_option_reference==overlap.short_put_option_optionslab))
    comparison = [('Trades', REFERENCE['trades'], metrics['trade_count']),
        ('Net P&L', REFERENCE['net_pnl'], metrics['net_pnl']), ('Fees', REFERENCE['fees'], metrics['fees']),
        ('Win rate %', REFERENCE['win_rate'], metrics['win_rate']),
        ('Profit factor', REFERENCE['profit_factor'], metrics['profit_factor']),
        ('Closed-trade max drawdown', REFERENCE['closed_trade_max_drawdown'], metrics['closed_trade_max_drawdown']),
        ('Active-day Sharpe', REFERENCE['active_day_sharpe'], metrics['active_day_sharpe'])]
    frame = pd.DataFrame(comparison, columns=['metric','reference','optionslab'])
    frame['difference'] = frame.optionslab-frame.reference
    frame['difference_pct'] = np.where(frame.reference!=0, frame.difference/frame.reference*100, np.nan)
    evidence = dict(overlapping_dates=len(overlap),
        pnl_correlation=float(overlap.net_pnl_usd_reference.corr(overlap.net_pnl_usd_optionslab)),
        mean_absolute_pnl_difference=float((overlap.net_pnl_usd_optionslab-overlap.net_pnl_usd_reference).abs().mean()),
        same_strikes_pct=float(same_strikes.mean()*100),
        reference_only_dates=sorted(set(old.trade_date)-set(new.trade_date)),
        optionslab_only_dates=sorted(set(new.trade_date)-set(old.trade_date)),
        missing_data_dates=run['missing_days'], unresolved_count=metrics['unresolved_count'],
        calendar_day_sharpe=metrics['sharpe'], observed_intraday_max_drawdown=metrics['max_drawdown'])
    frame.to_csv(out/'comparison.csv', index=False)
    new.to_csv(out/'optionslab_trades.csv', index=False)
    (out/'evidence.json').write_text(json.dumps(evidence, indent=2))
    (out/'config.json').write_text(json.dumps(config(), indent=2))
    table = ['| Metric | Reference | OptionsLab | Difference | Difference % |',
             '| --- | ---: | ---: | ---: | ---: |']
    table.extend(f"| {row.metric} | {row.reference:.4f} | {row.optionslab:.4f} | {row.difference:.4f} | {row.difference_pct:.3f}% |"
                 for row in frame.itertuples(index=False))
    report = ['# Legacy optimized strangle validation', '', *table, '',
        '## Trade-level evidence', '', '```json', json.dumps(evidence, indent=2), '```', '',
        'The earlier report calculated Sharpe using trading days with positions and drawdown from closed-trade equity. '
        'OptionsLab also reports calendar-day Sharpe and intraday marked drawdown, which are stricter definitions.']
    (out/'report.md').write_text('\n'.join(report)+'\n')
    print('\nCOMPARISON')
    print(frame.to_string(index=False))
    print('\nTRADE EVIDENCE')
    print(json.dumps(evidence, indent=2))
    print(f'\nReport: {out/"report.md"}')


if __name__ == '__main__':
    main()
