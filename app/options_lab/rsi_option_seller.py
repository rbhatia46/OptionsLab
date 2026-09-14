"""Directional option selling driven by RSI versus an SMA of RSI."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .data import index_source, load_day
from .engine import SECOND, Ticks
from .trend import TIMEFRAMES, build_bars

IST = 'Asia/Kolkata'
SYMBOL = re.compile(r'([CP])-BTC-(\d+)-(\d{6})')


@dataclass(frozen=True)
class RsiOptionConfig:
    data_root: Path
    output_dir: Path
    cache_dir: Path | None = None
    start: str = '2024-04-01'
    end: str = '2026-07-31'
    timeframes: tuple[str, ...] = ('5m', '10m', '15m', '30m', '1h')
    rsi_period: int = 14
    rsi_sma_period: int = 50
    quantity_btc: float = 1.0
    otm_pct: float = 1.0
    otm_tolerance_pct: float = 1.0
    min_hours_to_expiry: float = 16.0
    max_days_to_expiry: float = 7.0
    expiry_buffer_hours: float = 2.0
    expiry_time_ist: str = '17:30'
    slippage_pct: float = 1.0
    fee_pct: float = 0.01
    fee_cap_pct: float = 3.5
    tax_pct: float = 18.0
    latency_sec: float = 1.0
    max_execution_delay_min: float = 15.0
    entry_mark_max_age_sec: float = 300.0
    exit_price_max_age_sec: float = 21600.0
    underlying_max_age_sec: float = 60.0

    def validate(self) -> None:
        start = pd.Timestamp(self.start, tz=IST)
        end = pd.Timestamp(self.end, tz=IST)
        if start > end:
            raise ValueError('start must be on or before end')
        if not self.timeframes or any(x not in TIMEFRAMES for x in self.timeframes):
            raise ValueError(f'timeframes must come from {sorted(TIMEFRAMES)}')
        if self.rsi_period < 2 or self.rsi_sma_period < 2:
            raise ValueError('RSI and RSI-SMA periods must both be at least 2')
        if self.quantity_btc <= 0 or abs(self.quantity_btc/.001-round(self.quantity_btc/.001)) > 1e-7:
            raise ValueError('quantity_btc must be a positive multiple of 0.001 BTC')
        for name in ('otm_pct', 'otm_tolerance_pct', 'slippage_pct', 'fee_pct', 'fee_cap_pct', 'tax_pct'):
            if not 0 <= getattr(self, name) <= 100:
                raise ValueError(f'{name} must be between 0 and 100')
        if not 0 < self.min_hours_to_expiry < self.max_days_to_expiry*24:
            raise ValueError('minimum expiry hours must be positive and below maximum expiry days')
        if not 0 <= self.expiry_buffer_hours < self.min_hours_to_expiry:
            raise ValueError('expiry buffer must be nonnegative and below minimum expiry hours')
        if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', self.expiry_time_ist):
            raise ValueError('expiry_time_ist must be HH:MM')
        if min(self.max_execution_delay_min, self.entry_mark_max_age_sec,
               self.exit_price_max_age_sec, self.underlying_max_age_sec) <= 0:
            raise ValueError('execution delay and price-age limits must be positive')


def compute_rsi_signal(bars: pd.DataFrame, rsi_period: int, sma_period: int) -> pd.DataFrame:
    """Return Wilder RSI, its simple moving average, and the completed-bar state."""
    out = bars.copy()
    delta = out['close'].astype(float).diff()
    gain = delta.clip(lower=0).ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/rsi_period, adjust=False, min_periods=rsi_period).mean()
    denominator = gain+loss
    rsi = pd.Series(np.where(denominator > 0, 100*gain/denominator, 50.0), index=out.index)
    rsi[gain.isna() | loss.isna()] = np.nan
    rsi_sma = rsi.rolling(sma_period, min_periods=sma_period).mean()
    signal = np.where(rsi > rsi_sma, 1, np.where(rsi < rsi_sma, -1, 0)).astype(int)
    signal[rsi.isna() | rsi_sma.isna()] = 0
    out['rsi'] = rsi
    out['rsi_sma'] = rsi_sma
    out['signal'] = signal
    return out


def _expiry_ns(symbol: str, expiry_time_ist: str) -> tuple[str, float, int] | None:
    match = SYMBOL.fullmatch(str(symbol))
    if not match:
        return None
    hour, minute = map(int, expiry_time_ist.split(':'))
    local = pd.to_datetime(match[3], format='%d%m%y').tz_localize(IST)+pd.Timedelta(hours=hour, minutes=minute)
    return match[1], float(match[2]), int(local.tz_convert('UTC').value)


class Archive:
    """Lazy daily access to indexed options and futures source data."""
    def __init__(self, config: RsiOptionConfig, cache: Path, progress=print):
        self.c, self.cache, self.progress = config, cache, progress
        self._folders: dict[tuple[str, str], Path | None] = {}
        self.manifests: dict[tuple[str, str], dict] = {}
        self._days: dict[tuple[str, str], pd.DataFrame] = {}
        self.missing_source_months: set[str] = set()

    def _folder(self, kind: str, month: str) -> Path | None:
        key = kind, month
        if key in self._folders:
            return self._folders[key]
        prefix = 'BTCUSD' if kind == 'futures' else 'BTC'
        path = self.c.data_root/f'{kind}_data'/f'{prefix}_{month}.csv'
        if not path.exists():
            self._folders[key] = None
            self.missing_source_months.add(f'{kind}:{month}')
            return None
        self.progress(f'Indexing/checking {path.name}')
        folder, manifest = index_source(path, self.cache, self.progress)
        self._folders[key] = folder
        self.manifests[key] = manifest
        return folder

    def day(self, kind: str, date: str) -> pd.DataFrame:
        key = kind, date
        if key not in self._days:
            folder = self._folder(kind, date[:7])
            self._days[key] = load_day(folder, date) if folder else pd.DataFrame()
            # Keep memory bounded during a multi-year replay.
            same_kind = [k for k in self._days if k[0] == kind]
            if len(same_kind) > 10:
                del self._days[same_kind[0]]
        return self._days[key]

    @staticmethod
    def dates_between(start_ns: int, end_ns: int) -> list[str]:
        first = pd.Timestamp(start_ns, tz='UTC').normalize()
        last = pd.Timestamp(end_ns, tz='UTC').normalize()
        return [str(x.date()) for x in pd.date_range(first, last, freq='D')]

    def option_window(self, start_ns: int, end_ns: int, symbol: str | None = None) -> pd.DataFrame:
        frames = []
        for date in self.dates_between(start_ns, end_ns):
            frame = self.day('options', date)
            if frame.empty:
                continue
            selected = frame[(frame.timestamp_ns >= start_ns) & (frame.timestamp_ns <= end_ns)]
            if symbol is not None:
                selected = selected[selected.symbol == symbol]
            if not selected.empty:
                frames.append(selected)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def first_option_trade(self, symbol: str, start_ns: int, end_ns: int) -> tuple[int, float] | None:
        frame = self.option_window(start_ns, end_ns, symbol)
        if frame.empty:
            return None
        row = frame.sort_values('timestamp_ns', kind='stable').iloc[0]
        return int(row.timestamp_ns), float(row.price)

    def last_option_trade(self, symbol: str, at_ns: int, max_age_sec: float) -> tuple[int, float] | None:
        start = at_ns-int(max_age_sec*SECOND)
        frame = self.option_window(start, at_ns, symbol)
        if frame.empty:
            return None
        row = frame.sort_values('timestamp_ns', kind='stable').iloc[-1]
        return int(row.timestamp_ns), float(row.price)

    def entry_candidate(self, decision_ns: int, spot: float, direction: int) -> dict | None:
        start = decision_ns-int(self.c.entry_mark_max_age_sec*SECOND)
        frame = self.option_window(start, decision_ns)
        if frame.empty:
            return None
        symbols = []
        for symbol, group in frame.groupby('symbol', sort=False):
            parsed = _expiry_ns(str(symbol), self.c.expiry_time_ist)
            if parsed is None:
                continue
            kind, strike, expiry = parsed
            needed = 'P' if direction > 0 else 'C'
            if kind != needed:
                continue
            hours = (expiry-decision_ns)/SECOND/3600
            if not self.c.min_hours_to_expiry <= hours <= self.c.max_days_to_expiry*24:
                continue
            row = group.sort_values('timestamp_ns', kind='stable').iloc[-1]
            symbols.append(dict(symbol=str(symbol), kind=kind, strike=strike, expiry_ns=expiry,
                                mark_time_ns=int(row.timestamp_ns), mark_price=float(row.price)))
        if not symbols:
            return None
        expiry = min(x['expiry_ns'] for x in symbols)
        symbols = [x for x in symbols if x['expiry_ns'] == expiry]
        target = spot*(1-self.c.otm_pct/100) if direction > 0 else spot*(1+self.c.otm_pct/100)
        eligible = [x for x in symbols if (x['strike'] <= target if direction > 0 else x['strike'] >= target)]
        eligible = [x for x in eligible if abs(abs(x['strike']/spot-1)*100-self.c.otm_pct) <= self.c.otm_tolerance_pct]
        if not eligible:
            return None
        return min(eligible, key=lambda x: (abs(x['strike']-target), x['symbol']))


def _fee(config: RsiOptionConfig, quantity: float, underlying: float, premium: float) -> float:
    base = min(quantity*underlying*config.fee_pct/100, quantity*premium*config.fee_cap_pct/100)
    return base*(1+config.tax_pct/100)


def _execution(raw: float, side: str, config: RsiOptionConfig) -> float:
    return raw*(1-config.slippage_pct/100 if side == 'sell' else 1+config.slippage_pct/100)


def _spot(spots: Ticks, timestamp_ns: int, config: RsiOptionConfig) -> float | None:
    value = spots.asof(timestamp_ns, config.underlying_max_age_sec)
    return value[0] if value else None


def signal_changed_before_fill(signal_bars: pd.DataFrame, width_ns: int, decision_ns: int,
                               fill_ns: int, intended: int) -> bool:
    closes = signal_bars.t.to_numpy(np.int64)+width_ns
    signals = signal_bars.signal.to_numpy(np.int64)
    intervening = signals[(closes > decision_ns) & (closes <= fill_ns)]
    return bool(np.any((intervening != 0) & (intervening != intended)))


def _fill(archive: Archive, spots: Ticks, symbol: str, side: str, decision_ns: int,
          config: RsiOptionConfig, allow_stale_exit: bool, allow_future: bool = True) -> dict | None:
    begin = decision_ns+int(config.latency_sec*SECOND)
    deadline = begin+int(config.max_execution_delay_min*60*SECOND)
    observed = archive.first_option_trade(symbol, begin, deadline) if allow_future else None
    source = 'observed_option_trade_after_trigger'
    execution_ns = observed[0] if observed else (deadline if allow_future else decision_ns)
    if observed is None and allow_stale_exit:
        observed = archive.last_option_trade(symbol, execution_ns, config.exit_price_max_age_sec)
        source = 'bounded_stale_exit_price'
    if observed is None:
        return None
    quote_ns, raw = observed
    underlying = _spot(spots, execution_ns, config)
    if underlying is None:
        return None
    price = _execution(raw, side, config)
    return dict(timestamp_ns=execution_ns, timestamp_utc=pd.Timestamp(execution_ns, tz='UTC').isoformat(),
                timestamp_ist=pd.Timestamp(execution_ns, tz='UTC').tz_convert(IST).isoformat(),
                quote_time_utc=pd.Timestamp(quote_ns, tz='UTC').isoformat(), quote_age_sec=(execution_ns-quote_ns)/SECOND,
                price_source=source, side=side, raw_price=raw, price=price, underlying=underlying,
                fee=_fee(config, config.quantity_btc, underlying, price),
                slippage=config.quantity_btc*abs(price-raw))


def replay_timeframe(signal_bars: pd.DataFrame, timeframe: str, archive: Archive,
                     spots: Ticks, config: RsiOptionConfig, progress=print) -> tuple[list[dict], Counter]:
    width = TIMEFRAMES[timeframe]*SECOND
    start_ns = pd.Timestamp(config.start, tz=IST).tz_convert('UTC').value
    end_ns = (pd.Timestamp(config.end, tz=IST)+pd.Timedelta(days=1)).tz_convert('UTC').value-1
    trades, skips, position, trade_id, available_after = [], Counter(), None, 0, 0

    def close_position(trigger_ns: int, reason: str, allow_future: bool = True) -> int | None:
        nonlocal position, trade_id, available_after
        fill = _fill(archive, spots, position['symbol'], 'buy', trigger_ns, config, True, allow_future)
        if fill is None:
            skips['unresolved_exit'] += 1
            position['unresolved_reason'] = reason
            return None
        gross = config.quantity_btc*(position['entry']['price']-fill['price'])
        fees = position['entry']['fee']+fill['fee']
        net = gross-fees
        trades.append(dict(trade_id=trade_id, timeframe=timeframe,
            signal_direction='bullish' if position['direction'] > 0 else 'bearish',
            option_side_sold='put' if position['direction'] > 0 else 'call', symbol=position['symbol'],
            strike=position['strike'], expiry_utc=pd.Timestamp(position['expiry_ns'], tz='UTC').isoformat(),
            rsi_at_entry=position['rsi'], rsi_sma_at_entry=position['rsi_sma'],
            signal_time_ist=pd.Timestamp(position['signal_ns'], tz='UTC').tz_convert(IST).isoformat(),
            entry_time_ist=position['entry']['timestamp_ist'], exit_time_ist=fill['timestamp_ist'], exit_reason=reason,
            quantity_btc=config.quantity_btc, entry_raw_price=position['entry']['raw_price'],
            entry_exec_price=position['entry']['price'], exit_raw_price=fill['raw_price'], exit_exec_price=fill['price'],
            entry_price_source=position['entry']['price_source'], exit_price_source=fill['price_source'],
            exit_quote_age_sec=fill['quote_age_sec'], underlying_entry=position['entry']['underlying'],
            underlying_exit=fill['underlying'], entry_fees=position['entry']['fee'], exit_fees=fill['fee'],
            fees=fees, slippage=position['entry']['slippage']+fill['slippage'], gross_pnl=gross, net_pnl=net))
        trade_id += 1
        available_after = fill['timestamp_ns']
        position = None
        return fill['timestamp_ns']

    valid = signal_bars[(signal_bars.t+width >= start_ns) & (signal_bars.t+width <= end_ns)]
    for count, row in enumerate(valid.itertuples(index=False), 1):
        if count % 5000 == 0:
            progress(f'{timeframe}: processed {count:,}/{len(valid):,} signal bars')
        signal = int(row.signal)
        if signal == 0:
            continue
        decision = int(row.t)+width
        if decision <= available_after or (position is not None and decision <= position['entry']['timestamp_ns']):
            continue
        if position is not None:
            trigger = None
            reason = None
            buffer_ns = position['expiry_ns']-int(config.expiry_buffer_hours*3600*SECOND)
            if buffer_ns <= decision:
                trigger, reason = buffer_ns, 'expiry_buffer'
            elif signal != position['direction']:
                trigger, reason = decision, 'rsi_sma_flip'
            if trigger is not None:
                completed = close_position(trigger, reason)
                if completed is None:
                    break
                # Wait for a later completed signal bar before placing the next entry.
                continue
        if position is None:
            spot = _spot(spots, decision, config)
            if spot is None:
                skips['stale_underlying'] += 1
                continue
            candidate = archive.entry_candidate(decision, spot, signal)
            if candidate is None:
                skips['no_eligible_option'] += 1
                continue
            entry = _fill(archive, spots, candidate['symbol'], 'sell', decision, config, False)
            if entry is None or entry['timestamp_ns'] >= candidate['expiry_ns']:
                skips['entry_unfilled'] += 1
                continue
            if signal_changed_before_fill(signal_bars, width, decision, entry['timestamp_ns'], signal):
                skips['signal_changed_before_entry_fill'] += 1
                continue
            position = dict(direction=signal, symbol=candidate['symbol'], strike=candidate['strike'],
                            expiry_ns=candidate['expiry_ns'], signal_ns=decision, rsi=float(row.rsi),
                            rsi_sma=float(row.rsi_sma), entry=entry)
    if position is not None and 'unresolved_reason' not in position:
        trigger = min(end_ns, position['expiry_ns']-int(config.expiry_buffer_hours*3600*SECOND))
        close_position(trigger, 'sample_end' if trigger == end_ns else 'expiry_buffer', trigger != end_ns)
    return trades, skips


def performance(trades: list[dict], start: str, end: str) -> tuple[dict, pd.DataFrame]:
    dates = [str(x.date()) for x in pd.date_range(start, end, freq='D')]
    by_day = Counter()
    for trade in trades:
        by_day[str(pd.Timestamp(trade['exit_time_ist']).date())] += trade['net_pnl']
    daily = pd.DataFrame({'date': dates, 'net_pnl': [by_day[x] for x in dates]})
    daily['cumulative_pnl'] = daily.net_pnl.cumsum()
    daily['peak'] = np.maximum.accumulate(np.r_[0., daily.cumulative_pnl.to_numpy()])[1:]
    daily['drawdown'] = daily['peak']-daily['cumulative_pnl']
    pnl = np.array([x['net_pnl'] for x in trades], dtype=float)
    values = daily.net_pnl.to_numpy(float)
    sd = float(values.std(ddof=1)) if len(values) > 1 else 0.
    downside = math.sqrt(float(np.mean(np.minimum(values, 0)**2))) if len(values) else 0.
    wins = float(pnl[pnl > 0].sum()) if len(pnl) else 0.
    losses = -float(pnl[pnl < 0].sum()) if len(pnl) else 0.
    tail = np.sort(pnl)[:max(1, math.ceil(len(pnl)*.05))] if len(pnl) else np.array([])
    summary = dict(trades=len(trades), net_pnl=float(pnl.sum()) if len(pnl) else 0.,
        gross_pnl=sum(x['gross_pnl'] for x in trades), fees=sum(x['fees'] for x in trades),
        slippage=sum(x['slippage'] for x in trades), max_drawdown=float(daily.drawdown.max()) if len(daily) else 0.,
        sharpe=float(values.mean()/sd*math.sqrt(365)) if sd > 1e-12 else None,
        sortino=float(values.mean()/downside*math.sqrt(365)) if downside > 1e-12 else None,
        win_rate=float((pnl > 0).mean()*100) if len(pnl) else None,
        profit_factor=wins/losses if losses > 0 else None,
        average_trade=float(pnl.mean()) if len(pnl) else None,
        best_trade=float(pnl.max()) if len(pnl) else None,
        worst_trade=float(pnl.min()) if len(pnl) else None,
        expected_shortfall_95=float(tail.mean()) if len(tail) else None)
    return summary, daily


def _fmt(value: float | None) -> str:
    return '—' if value is None else f'{value:,.2f}'


def _money(value: float | None) -> str:
    if value is None:
        return '—'
    return ('−$' if value < 0 else '$')+f'{abs(value):,.2f}'


def write_report(config: RsiOptionConfig, summaries: list[dict], trades: list[dict],
                 daily_rows: list[pd.DataFrame], skips: dict, manifests: list[dict]) -> dict[str, Path]:
    out = config.output_dir
    out.mkdir(parents=True, exist_ok=True)
    summary_frame = pd.DataFrame(summaries)
    trades_frame = pd.DataFrame(trades)
    daily_frame = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    paths = dict(summary=out/'summary.csv', trades=out/'trades.csv', daily=out/'daily_pnl.csv',
                 report=out/'report.md', config=out/'config.json')
    summary_frame.to_csv(paths['summary'], index=False)
    trades_frame.to_csv(paths['trades'], index=False)
    daily_frame.to_csv(paths['daily'], index=False)
    payload = {**asdict(config), 'data_root': str(config.data_root), 'output_dir': str(config.output_dir),
               'cache_dir': str(config.cache_dir) if config.cache_dir else None,
               'skips': skips, 'source_manifests': manifests}
    paths['config'].write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
    lines = ['# RSI versus RSI-SMA directional option-selling report', '',
        f'Period: **{config.start} through {config.end} IST**  ',
        f'Variants: **{", ".join(config.timeframes)}**, each traded independently at **{config.quantity_btc:.3f} BTC**  ',
        f'Signal: Wilder RSI({config.rsi_period}) above/below SMA({config.rsi_sma_period}) of RSI  ',
        f'Options: sell {config.otm_pct:.2f}% OTM put in bullish state; sell {config.otm_pct:.2f}% OTM call in bearish state  ',
        f'Costs: {config.slippage_pct:.2f}% adverse premium slippage per fill; {config.fee_pct:.4f}% notional fee capped at {config.fee_cap_pct:.2f}% of premium; {config.tax_pct:.2f}% fee tax', '',
        '## Results', '', '| Variant | Trades | Net P&L | Max drawdown | Sharpe | Sortino | Win rate | Fees | Slippage |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in summaries:
        lines.append(f"| {row['variant']} | {row['trades']} | {_money(row['net_pnl'])} | {_money(row['max_drawdown'])} | {_fmt(row['sharpe'])} | {_fmt(row['sortino'])} | {_fmt(row['win_rate'])}% | {_money(row['fees'])} | {_money(row['slippage'])} |")
    lines += ['', '## Execution contract', '',
        f'- Signals use completed, IST-aligned futures bars. A state is bullish when RSI is above its {config.rsi_sma_period}-bar RSI SMA and bearish when below.',
        f'- Each timeframe is a separate strategy. The combined row sums them and can represent {len(config.timeframes)} simultaneous {config.quantity_btc:g} BTC short-option positions.',
        '- The selected option must have a fresh observed print before the signal, satisfy the OTM tolerance, and have at least the configured hours to expiry.',
        '- Entry uses the first observed option trade after the signal and latency within the execution-delay window. Source-print volume is ignored.',
        '- A position closes when the RSI state reverses, at the expiry buffer, or at sample end. Exit fills may use a bounded older observed trade and record that fact.',
        '- P&L is premium received minus premium paid, fees, fee tax, and adverse slippage. No funding, margin liquidation, order-book depth, bid/ask spread, assignment, or official settlement is modelled.',
        '- Drawdown and Sharpe use realized daily USD P&L at fixed BTC size. Open-position mark-to-market drawdown between exits is unavailable in this report.', '',
        '## Skipped events', '', '```json', json.dumps(skips, indent=2), '```', '',
        'Detailed evidence is in `trades.csv`; daily variant and combined paths are in `daily_pnl.csv`; exact settings and source fingerprints are in `config.json`.']
    paths['report'].write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return paths


def run(config: RsiOptionConfig, progress=print) -> tuple[pd.DataFrame, dict[str, Path]]:
    config.validate()
    cache = config.cache_dir or config.output_dir.parent/'options_lab_cache'
    archive = Archive(config, cache, progress)
    start_ist = pd.Timestamp(config.start, tz=IST)
    end_ist = pd.Timestamp(config.end, tz=IST)+pd.Timedelta(days=1)
    warmup_seconds = max(TIMEFRAMES[x] for x in config.timeframes)*(config.rsi_period+config.rsi_sma_period+5)
    load_start = start_ist.tz_convert('UTC')-pd.Timedelta(seconds=warmup_seconds)
    load_end = end_ist.tz_convert('UTC')
    frames, missing_futures = [], []
    for date in Archive.dates_between(load_start.value, load_end.value):
        frame = archive.day('futures', date)
        if frame.empty:
            missing_futures.append(date)
        else:
            frames.append(frame)
    if not frames:
        raise RuntimeError('No futures ticks were found for the requested period')
    futures = pd.concat(frames, ignore_index=True).sort_values('timestamp_ns', kind='stable')
    futures = futures[(futures.timestamp_ns >= load_start.value) & (futures.timestamp_ns <= load_end.value)]
    spots = Ticks.frame(futures)
    summaries, all_trades, daily_rows, skips = [], [], [], {}
    for timeframe in config.timeframes:
        progress(f'Building {timeframe} IST bars and RSI signals')
        bars = compute_rsi_signal(build_bars(futures, timeframe), config.rsi_period, config.rsi_sma_period)
        trades, skipped = replay_timeframe(bars, timeframe, archive, spots, config, progress)
        summary, daily = performance(trades, config.start, config.end)
        summary['variant'] = timeframe
        daily.insert(0, 'variant', timeframe)
        summaries.append(summary); daily_rows.append(daily); all_trades.extend(trades); skips[timeframe] = dict(skipped)
    combined, combined_daily = performance(all_trades, config.start, config.end)
    # performance(all_trades) already groups all timeframe exits on each day.
    combined['variant'] = 'combined'
    combined_daily.insert(0, 'variant', 'combined')
    summaries.append(combined); daily_rows.append(combined_daily)
    skips['missing_futures_utc_dates'] = missing_futures
    skips['missing_source_months'] = sorted(archive.missing_source_months)
    paths = write_report(config, summaries, all_trades, daily_rows, skips, list(archive.manifests.values()))
    return pd.DataFrame(summaries), paths
