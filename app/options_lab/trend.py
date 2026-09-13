"""No-lookahead BTCUSD futures trend replay built from the local tick archive."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .data import index_source, load_day

SECOND = 1_000_000_000
IST_OFFSET = int(5.5 * 3600 * SECOND)
TIMEFRAMES = {
    '30s': 30, '1m': 60, '2m': 120, '3m': 180, '5m': 300, '10m': 600,
    '15m': 900, '30m': 1800, '1h': 3600, '90m': 5400, '2h': 7200,
    '4h': 14400, '6h': 21600, '12h': 43200, '1D': 86400,
    '3D': 259200, '1W': 604800,
}


def _iso(ns):
    return pd.Timestamp(int(ns), tz='UTC').isoformat()


def build_bars(ticks, timeframe):
    """Build fixed, IST-aligned OHLCV bars. Weekly bars start Monday 00:00 IST."""
    if ticks.empty:
        return pd.DataFrame(columns=['t', 'open', 'high', 'low', 'close', 'volume', 'ticks'])
    width = TIMEFRAMES[timeframe] * SECOND
    local = ticks.timestamp_ns.to_numpy(np.int64) + IST_OFFSET
    anchor = 4 * 86400 * SECOND if timeframe == '1W' else 0  # 1970-01-05 was Monday.
    bucket = ((local - anchor) // width) * width + anchor - IST_OFFSET
    frame = ticks.assign(bucket=bucket).sort_values('timestamp_ns', kind='stable')
    bars = frame.groupby('bucket', sort=True).agg(
        open=('price', 'first'), high=('price', 'max'), low=('price', 'min'),
        close=('price', 'last'), volume=('size', 'sum'), ticks=('price', 'size')).reset_index()
    return bars.rename(columns={'bucket': 't'})


def _ma_signal(close, kind, fast, slow):
    series = pd.Series(close, dtype=float)
    if kind == 'ema':
        a = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
        b = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    else:
        a, b = series.rolling(fast).mean(), series.rolling(slow).mean()
    signal = np.where(a > b, 1, np.where(a < b, -1, 0)).astype(int)
    signal[np.isnan(a) | np.isnan(b)] = 0
    return signal, a.to_numpy(), b.to_numpy()


def _supertrend_signal(bars, period, multiplier):
    high, low, close = (bars[k].to_numpy(float) for k in ('high', 'low', 'close'))
    previous = np.r_[np.nan, close[:-1]]
    tr = np.nanmax(np.vstack([high-low, np.abs(high-previous), np.abs(low-previous)]), axis=0)
    atr = pd.Series(tr).ewm(alpha=1/period, adjust=False, min_periods=period).mean().to_numpy()
    middle = (high+low)/2
    basic_upper, basic_lower = middle+multiplier*atr, middle-multiplier*atr
    upper, lower = basic_upper.copy(), basic_lower.copy()
    signal = np.zeros(len(close), dtype=int)
    for i in range(1, len(close)):
        if np.isnan(atr[i]):
            continue
        if not np.isnan(upper[i-1]) and not (basic_upper[i] < upper[i-1] or close[i-1] > upper[i-1]):
            upper[i] = upper[i-1]
        if not np.isnan(lower[i-1]) and not (basic_lower[i] > lower[i-1] or close[i-1] < lower[i-1]):
            lower[i] = lower[i-1]
        prior = signal[i-1] or 1
        signal[i] = -1 if prior == 1 and close[i] < lower[i] else 1 if prior == -1 and close[i] > upper[i] else prior
    return signal, atr, np.where(signal >= 0, lower, upper)


def replay_bars(bars, c):
    if c['trend_strategy'] == 'ma_crossover':
        signal, fast_line, slow_line = _ma_signal(bars.close, c['trend_ma_type'], c['trend_fast'], c['trend_slow'])
        indicator = dict(fast=fast_line, slow=slow_line)
    else:
        signal, atr, line = _supertrend_signal(bars, c['supertrend_period'], c['supertrend_multiplier'])
        indicator = dict(atr=atr, supertrend=line)
    if c['trend_direction'] == 'long_only': signal = np.maximum(signal, 0)
    if c['trend_direction'] == 'short_only': signal = np.minimum(signal, 0)
    qty, slip = c['quantity_btc'], c['slippage_pct']/100
    fee_rate = c['fee_pct']/100 * (1+c['tax_pct']/100)
    trades, path, realized, position = [], [], 0., None

    def execution(raw, side):
        fill = raw*(1+slip if side == 'buy' else 1-slip)
        return fill, abs(fill-raw)*qty, abs(fill*qty)*fee_rate

    def close_position(raw, ns, reason):
        nonlocal realized, position
        side = 'sell' if position['direction'] == 1 else 'buy'
        fill, exit_slip, exit_fee = execution(raw, side)
        gross = position['direction']*qty*(fill-position['entry_fill'])
        fees = position['entry_fee']+exit_fee
        pnl = gross-fees
        realized += pnl
        exit_local = pd.Timestamp(ns, tz='UTC').tz_convert('Asia/Kolkata')
        trades.append(dict(
            date=str(exit_local.date()), decision_time=_iso(position['signal_time']), entry_time=_iso(position['entry_time']),
            exit_time=_iso(ns), exit_trigger=_iso(ns), exit_reason=reason, status='closed', entry_complete=True,
            entry_credit=None, net_pnl=pnl, gross_pnl=gross, fees=fees,
            slippage=position['entry_slip']+exit_slip, margin_reserve=abs(position['entry_fill']*qty),
            underlying_entry=position['entry_fill'], underlying_exit=fill, direction='long' if position['direction']==1 else 'short',
            quantity_btc=qty, mae=position['mae'], mfe=position['mfe'], mark_events=position['marks'], fresh_marks=position['marks'],
            invalid_greek_events=0, mark_coverage_pct=100., entry_greeks=dict(delta=position['direction']*qty,gamma=0.,theta=0.,vega=0.),
            legs=[], planned_legs=[], unresolved=[], path=[], execution_model='next-bar BTCUSD futures open with configured slippage',
            execution_window_risk='Signal uses a completed bar and executes at the next bar open. If a stop and target occur inside one bar, the stop is assumed to occur first.'
        ))
        position = None

    def liquidation_pnl(raw):
        side = 'sell' if position['direction'] == 1 else 'buy'
        fill, _, exit_fee = execution(raw, side)
        return position['direction']*qty*(fill-position['entry_fill'])-position['entry_fee']-exit_fee

    for i in range(1, len(bars)):
        bar = bars.iloc[i]; desired = int(signal[i-1]); ns = int(bar.t); raw_open = float(bar.open)
        if position and desired != position['direction']:
            close_position(raw_open, ns, 'signal_flip' if desired else 'signal_flat')
        if not position and desired:
            side = 'buy' if desired == 1 else 'sell'; fill, entry_slip, entry_fee = execution(raw_open, side)
            position = dict(direction=desired, entry_raw=raw_open, entry_fill=fill, entry_time=ns,
                            signal_time=int(bars.iloc[i-1].t)+TIMEFRAMES[c['trend_timeframe']]*SECOND,
                            entry_slip=entry_slip, entry_fee=entry_fee, mae=0., mfe=0., marks=0)
        if position:
            d = position['direction']; entry = position['entry_fill']
            adverse = liquidation_pnl(float(bar.low) if d==1 else float(bar.high))
            favorable = liquidation_pnl(float(bar.high) if d==1 else float(bar.low))
            position['mae'] = min(position['mae'], adverse)
            position['mfe'] = max(position['mfe'], favorable); position['marks'] += 1
            stop = c['trend_stop_loss_pct']/100; target = c['trend_take_profit_pct']/100
            stop_hit = stop>0 and (float(bar.low)<=entry*(1-stop) if d==1 else float(bar.high)>=entry*(1+stop))
            target_hit = target>0 and (float(bar.high)>=entry*(1+target) if d==1 else float(bar.low)<=entry*(1-target))
            if stop_hit:
                raw = min(raw_open,entry*(1-stop)) if d==1 else max(raw_open,entry*(1+stop))
                close_position(raw, ns+TIMEFRAMES[c['trend_timeframe']]*SECOND-1, 'price_stop')
            elif target_hit:
                raw = max(raw_open,entry*(1+target)) if d==1 else min(raw_open,entry*(1-target))
                close_position(raw, ns+TIMEFRAMES[c['trend_timeframe']]*SECOND-1, 'profit_target')
        mark = realized
        if position:
            mark += liquidation_pnl(float(bar.close))
        path.append((int(bar.t)+TIMEFRAMES[c['trend_timeframe']]*SECOND-1, mark))
    if position and len(bars):
        last = bars.iloc[-1]; close_position(float(last.close), int(last.t)+TIMEFRAMES[c['trend_timeframe']]*SECOND-1, 'sample_end')
        path.append((int(last.t)+TIMEFRAMES[c['trend_timeframe']]*SECOND-1, realized))
    return trades, path, indicator


def run_trend_experiment(c, data_root: Path, cache: Path, progress, metrics, version):
    start_ist = pd.Timestamp(c['start'], tz='Asia/Kolkata')
    end_ist = pd.Timestamp(c['end'], tz='Asia/Kolkata') + pd.Timedelta(days=1)
    first_utc, last_utc = start_ist.tz_convert('UTC').normalize(), end_ist.tz_convert('UTC').normalize()
    utc_days = [str(x.date()) for x in pd.date_range(first_utc, last_utc, freq='D')]
    frames, sources, missing = [], [], []
    months = sorted({d[:7] for d in utc_days})
    for mi, month in enumerate(months):
        source = data_root/'futures_data'/f'BTCUSD_{month}.csv'
        selected = [d for d in utc_days if d.startswith(month)]
        if not source.exists():
            missing.extend(selected); continue
        progress(f'Preparing BTCUSD {month}', mi/max(len(months),1))
        folder, manifest = index_source(source, cache, lambda message: progress(message, mi/max(len(months),1)))
        sources.append(manifest)
        frames.extend(frame for day in selected if not (frame := load_day(folder, day)).empty)
    if frames:
        ticks = pd.concat(frames, ignore_index=True).sort_values('timestamp_ns', kind='stable')
        ticks = ticks[(ticks.timestamp_ns>=start_ist.tz_convert('UTC').value)&(ticks.timestamp_ns<end_ist.tz_convert('UTC').value)]
    else:
        ticks = pd.DataFrame()
    progress(f'Building {c["trend_timeframe"]} IST-aligned bars', .72)
    bars = build_bars(ticks, c['trend_timeframe'])
    trades, pnl_path, indicator = replay_bars(bars, c) if len(bars) else ([], [], {})
    days = [str(x.date()) for x in pd.date_range(c['start'], c['end'], freq='D')]
    absolute_path = [(start_ist.tz_convert('UTC').value, c['capital'])] + [(t,c['capital']+p) for t,p in pnl_path]
    summary = metrics(trades, days, c['capital'], 0, absolute_path, False, 'btc')
    progress('Calculating trend metrics', .98)
    warmup = c['trend_slow'] if c['trend_strategy']=='ma_crossover' else c['supertrend_period']
    run = dict(index=0, config=c, metrics=summary, development=None, holdout=None, trades=trades,
               skips=dict(Counter({'insufficient_warmup_bars':1}) if len(bars)<=warmup else {}), missing_days=missing,
               quality=dict(incomplete_entries=0, invalid_greek_events=0, source_ticks=len(ticks), bars=len(bars), warmup_bars=warmup))
    return dict(engine_version=version, source_root=str(data_root), sources=sources, runs=[run], selected_index=0,
                winner_selected=False, split_date=None, trend=dict(timeframe=c['trend_timeframe'], bars=len(bars), indicator=c['trend_strategy']),
                assumptions=['BTCUSD futures trade ticks are aggregated into fixed OHLC bars aligned to IST; weekly bars start Monday 00:00 IST.',
                    'Signals use completed bars and execute at the next bar open, preventing same-bar lookahead.',
                    'Futures fills use the full requested BTC quantity with configured adverse slippage; historical order-book depth is unavailable.',
                    'Stop and target collisions inside one OHLC bar are resolved conservatively in favor of the stop.',
                    'Fees use the configured notional rate and tax. Option premium fee caps do not apply to futures.',
                    'Positions close on a signal change, configured stop/target, or the final bar; no funding, margin liquidation, or exchange basis is modelled.'])
