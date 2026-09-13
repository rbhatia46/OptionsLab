"""Deterministic intraday option portfolio replay over local trade prints."""
from __future__ import annotations

import itertools
import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import index_source, load_day
from .pricing import YEAR_NS, implied_vol, greeks

VERSION = 'options-lab-1.3.0'
SECOND = 1_000_000_000
DEFAULTS = dict(sizing_mode='capital', execution_mode='volume', name='20Δ short strangle', structure='strangle', selection='delta', dte=0,
    call_delta=.2, put_delta=.2, delta_tolerance=.08, otm_pct=1., wing_width=1000., quantity_btc=.01,
    start='2026-06-01', end='2026-06-07', entry_time='06:00', exit_time='11:30', entry_window_min=30,
    days='all', take_profit_pct=50., stop_loss_pct=100., min_credit=1., max_loss_usd=0., delta_exit=0.,
    capital=10000., margin_pct=20., allocation_pct=80., min_iv=0., max_iv=500., min_move_pct=-100.,
    max_move_pct=100., slippage_pct=1., participation_pct=10., latency_sec=1., fill_timeout_sec=300.,
    max_age_sec=300., spot_age_sec=60., fee_pct=.01, fee_cap_pct=3.5, tax_pct=18., rate_pct=0.,
    expiry_hour=12, mode='single', grid_delta='0.15, 0.2, 0.25', grid_stop='100, 150', grid_tp='50',
    objective='sharpe', train_pct=70., min_trades=5)
BOUNDS = dict(dte=(0,30),call_delta=(.01,.95),put_delta=(.01,.95),delta_tolerance=(.005,.3),otm_pct=(0,50),
    wing_width=(1,100000),quantity_btc=(.001,100),entry_window_min=(0,120),take_profit_pct=(1,100),
    stop_loss_pct=(1,1000),min_credit=(0,1e7),max_loss_usd=(0,1e9),delta_exit=(0,1000),capital=(100,1e10),
    margin_pct=(1,100),allocation_pct=(1,100),min_iv=(0,1000),max_iv=(1,1000),min_move_pct=(-100,100),
    max_move_pct=(-100,100),slippage_pct=(0,50),participation_pct=(1,100),latency_sec=(0,60),
    fill_timeout_sec=(1,600),max_age_sec=(1,1800),spot_age_sec=(1,600),fee_pct=(0,1),fee_cap_pct=(0,100),
    tax_pct=(0,100),rate_pct=(-10,50),expiry_hour=(1,23),train_pct=(50,90),min_trades=(1,10000))


def validate_request(payload):
    if not isinstance(payload, dict):
        raise ValueError('Configuration must be a JSON object.')
    unknown = set(payload)-set(DEFAULTS)-{'legs'}
    if unknown:
        raise ValueError('Unknown configuration fields: '+', '.join(sorted(unknown)))
    c = {**DEFAULTS, **payload}
    for key,(lo,hi) in BOUNDS.items():
        value=c[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError(f'{key} must be a number between {lo} and {hi}.')
    for key in ('dte','expiry_hour','min_trades','entry_window_min'):
        if int(c[key]) != c[key]:
            raise ValueError(f'{key} must be an integer.')
        c[key] = int(c[key])
    if abs(c['quantity_btc']/.001-round(c['quantity_btc']/.001))>1e-6:
        raise ValueError('BTC quantity must be a multiple of the 0.001 BTC contract.')
    choices = dict(sizing_mode=['capital','btc'], execution_mode=['price','volume'],
                   structure=['strangle','straddle','condor','call_spread','put_spread','short_call','short_put','custom'],
                   selection=['delta','otm'],days=['all','weekdays','weekends'],mode=['single','sweep'],
                   objective=['sharpe','net_pnl','calmar','drawdown'])
    for key,values in choices.items():
        if c[key] not in values:
            raise ValueError(f'Invalid {key}. Choose from {values}.')
    if not isinstance(c['name'],str) or not 1<=len(c['name'].strip())<=80:
        raise ValueError('Provide a strategy name of 1–80 characters.')
    for key in ('start','end'):
        if not isinstance(c[key],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',c[key]):
            raise ValueError('Dates must be YYYY-MM-DD.')
    start,end=pd.Timestamp(c['start'],tz='UTC'),pd.Timestamp(c['end'],tz='UTC')
    if start>end or (end-start).days>1095:
        raise ValueError('Select an ordered date range no longer than three years.')
    for key in ('entry_time','exit_time'):
        if not isinstance(c[key],str) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',c[key]):
            raise ValueError(f'{key} must be a UTC HH:MM time.')
    minute=lambda s:int(s[:2])*60+int(s[3:])
    if minute(c['entry_time'])+c['entry_window_min']+(c['latency_sec']+c['fill_timeout_sec'])/60>=minute(c['exit_time']):
        raise ValueError('Entry window plus fill timeout must finish before the time exit.')
    if minute(c['exit_time'])+(c['latency_sec']+2*c['fill_timeout_sec'])/60>=min(1440,c['expiry_hour']*60 if c['dte']==0 else 1440):
        raise ValueError('Allow two fill windows after time exit, before expiry or UTC midnight.')
    if c['min_iv']>c['max_iv'] or c['min_move_pct']>c['max_move_pct']:
        raise ValueError('Filter minimum cannot exceed maximum.')
    if c['structure']=='custom':
        legs=c.get('legs')
        if not isinstance(legs,list) or not 1<=len(legs)<=6:
            raise ValueError('Custom structures require 1–6 legs.')
        for leg in legs:
            if not isinstance(leg,dict) or set(leg)!={'type','side','delta','ratio'}:
                raise ValueError('Each leg needs exactly type, side, delta, ratio.')
            if leg['type'] not in ('C','P') or leg['side'] not in ('buy','sell'):
                raise ValueError('Leg type must be C/P and side buy/sell.')
            if type(leg['delta']) not in (int,float) or not math.isfinite(leg['delta']) or not .01<=leg['delta']<=.95:
                raise ValueError('Leg absolute delta must be 0.01–0.95.')
            if type(leg['ratio']) is not int or not 1<=leg['ratio']<=10:
                raise ValueError('Leg ratio must be an integer from 1 to 10.')
        if not any(l['side']=='sell' for l in legs):
            raise ValueError('This credit-strategy engine requires at least one short leg.')
    if c['mode']=='sweep':
        if c['structure'] in ('custom','straddle') or c['selection']!='delta':
            raise ValueError('Delta sweeps require a delta-selected standard structure other than straddle.')
        if (end-start).days<9:
            raise ValueError('A chronological holdout needs at least 10 calendar days.')
        grids=[]
        for name,lo,hi in [('grid_delta',.01,.95),('grid_stop',1,1000),('grid_tp',1,100)]:
            if not isinstance(c[name],str):
                raise ValueError(f'{name} must be comma-separated values.')
            values=list(dict.fromkeys(float(x.strip()) for x in c[name].split(',')))
            if not values or any(not math.isfinite(x) or not lo<=x<=hi for x in values):
                raise ValueError(f'{name} values must be between {lo} and {hi}.')
            grids.append(values)
        if math.prod(map(len,grids))>36:
            raise ValueError('Limit the experiment to 36 combinations.')
    return c


def iso(t):
    return pd.Timestamp(int(t),tz='UTC').isoformat()


@dataclass
class Ticks:
    t: np.ndarray
    p: np.ndarray
    size: np.ndarray

    @classmethod
    def frame(cls,f):
        return cls(f.timestamp_ns.to_numpy(dtype=np.int64),f.price.to_numpy(float),f['size'].to_numpy(float))

    def asof(self,t,age):
        i=int(np.searchsorted(self.t,t,side='right'))-1
        if i<0 or t-int(self.t[i])>age*SECOND:
            return None
        return float(self.p[i]),int(self.t[i])


@dataclass
class Book:
    symbol: str
    kind: str
    strike: float
    expiry: int
    roles: dict


def build_books(options,expiry_hour):
    books={}
    for symbol, f in options.groupby('symbol',sort=False):
        match=re.fullmatch(r'([CP])-BTC-(\d+)-(\d{6})',str(symbol))
        if not match:
            continue
        try:
            expiry=(pd.to_datetime(match[3],format='%d%m%y',utc=True)+pd.Timedelta(hours=expiry_hour)).value
        except ValueError:
            continue
        books[symbol]=Book(symbol,match[1],float(match[2]),expiry,
                          {r:Ticks.frame(f[f.role==r]) for r in ('maker','taker')})
    return books


def role(side):
    return 'maker' if side=='sell' else 'taker'


def opposite(side):
    return 'buy' if side=='sell' else 'sell'


def model(book,quote,spot_ticks,t,c):
    if quote is None:
        return None
    premium,quote_time=quote
    then=spot_ticks.asof(quote_time,c['spot_age_sec'])
    now=spot_ticks.asof(t,c['spot_age_sec'])
    if then is None or now is None or book.expiry<=t:
        return None
    vol=implied_vol(book.kind,then[0],book.strike,(book.expiry-quote_time)/YEAR_NS,c['rate_pct']/100,premium)
    if vol is None:
        return None
    result=greeks(book.kind,now[0],book.strike,(book.expiry-t)/YEAR_NS,c['rate_pct']/100,vol)
    return dict(**result,quote_time=iso(quote_time),quote_age_sec=(t-quote_time)/SECOND) if result else None


def select_legs(books,spots,t,c):
    spot=spots.asof(t,c['spot_age_sec'])
    if spot is None:
        return None,'stale_underlying'
    if c['min_move_pct']>-100 or c['max_move_pct']<100:
        old=spots.asof(t-3600*SECOND,c['spot_age_sec'])
        if old is None:
            return None,'missing_trend_history'
        move=(spot[0]/old[0]-1)*100
        if not c['min_move_pct']<=move<=c['max_move_pct']:
            return None,'trend_filter'
    target=(pd.Timestamp(t,tz='UTC').normalize()+pd.Timedelta(days=c['dte'],hours=c['expiry_hour'])).value
    # Even contract availability must be as-of: an afternoon-only strike cannot alter morning selection.
    observed=[b for b in books.values() if any(len(ticks.t) and ticks.t[0]<=t for ticks in b.roles.values())]
    expiries=sorted({b.expiry for b in observed if target<=b.expiry<=target+3*86400*SECOND and b.expiry>t})
    if not expiries:
        return None,'missing_expiry'
    candidates=[b for b in observed if b.expiry==expiries[0]]
    used=set()
    def choose(kind,side,target_delta=None,target_strike=None,wing=None,qty=None):
        ranked=[]
        for b in candidates:
            if b.kind!=kind or b.symbol in used:
                continue
            if wing is not None and ((kind=='C' and b.strike<wing) or (kind=='P' and b.strike>wing)):
                continue
            q=b.roles[role(side)].asof(t,c['max_age_sec'])
            g=model(b,q,spots,t,c)
            if g is None or not c['min_iv']<=g['iv']*100<=c['max_iv']:
                continue
            if target_delta is not None:
                score=abs(abs(g['delta'])-target_delta)
                if score>c['delta_tolerance']:
                    continue
            else:
                score=abs(b.strike-target_strike)
            ranked.append((score,b.symbol,b,q,g))
        if not ranked:
            return None
        _,_,b,q,g=min(ranked,key=lambda x:(x[0],x[1]))
        used.add(b.symbol)
        return dict(book=b,side=side,quantity=qty or c['quantity_btc'],signal_price=q[0],greeks=g)
    legs=[]
    structure=c['structure']
    if structure=='custom':
        for spec in c['legs']:
            leg=choose(spec['type'],spec['side'],target_delta=spec['delta'],qty=c['quantity_btc']*spec['ratio'])
            if leg is None:
                return None,'no_eligible_custom_leg'
            legs.append(leg)
    else:
        kinds={'strangle':'PC','straddle':'PC','condor':'PC','call_spread':'C','put_spread':'P','short_call':'C','short_put':'P'}[structure]
        atm_strike=None
        if structure=='straddle':
            common={b.strike for b in candidates if b.kind=='C'} & {b.strike for b in candidates if b.kind=='P'}
            if not common:
                return None,'no_common_straddle_strike'
            atm_strike=min(common,key=lambda k:abs(k-spot[0]))
        for kind in kinds:
            if atm_strike is not None:
                leg=choose(kind,'sell',target_strike=atm_strike)
                if leg and leg['book'].strike!=atm_strike:
                    leg=None
            elif c['selection']=='delta':
                leg=choose(kind,'sell',target_delta=c['call_delta' if kind=='C' else 'put_delta'])
            else:
                target_strike=spot[0]*(1+(1 if kind=='C' else -1)*c['otm_pct']/100)
                # For OTM mode, don't drift towards an ITM strike when the intended strike is absent.
                leg=choose(kind,'sell',target_strike=target_strike,wing=target_strike)
            if leg is None:
                return None,'no_eligible_short_leg'
            legs.append(leg)
        if structure in ('strangle','condor') and legs[0]['book'].strike>=legs[1]['book'].strike:
            return None,'inverted_short_strikes'
        if structure in ('condor','call_spread','put_spread'):
            for short in list(legs):
                kind=short['book'].kind
                target_strike=short['book'].strike+(1 if kind=='C' else -1)*c['wing_width']
                long=choose(kind,'buy',target_strike=target_strike,wing=target_strike)
                if long is None:
                    return None,'no_eligible_wing'
                legs.append(long)
    slip=c['slippage_pct']/100
    credit=sum((1 if l['side']=='sell' else -1)*l['quantity']*l['signal_price']*(1-slip if l['side']=='sell' else 1+slip) for l in legs)
    if credit<=0 or credit<c['min_credit']:
        return None,'minimum_credit'
    # Use full wing loss reserve for defined risk; conservative notional reserve for other shorts.
    if structure in ('condor','call_spread','put_spread'):
        widths=[abs(next(l['book'].strike for l in legs if l['side']=='buy' and l['book'].kind==s['book'].kind)-s['book'].strike)*s['quantity'] for s in legs if s['side']=='sell']
        reserve=max(widths) # Do not offset collateral with an unfilled credit.
    else:
        reserve=sum(l['quantity']*spot[0]*c['margin_pct']/100 for l in legs if l['side']=='sell')
    return dict(legs=legs,credit=credit,reserve=reserve,spot=spot[0]),None


def fill_order(book,side,qty,decision,spots,c,deadline=None):
    begin=decision+int(c['latency_sec']*SECOND)
    end=min(begin+int(c['fill_timeout_sec']*SECOND),book.expiry-1,deadline if deadline else book.expiry-1)
    if c['execution_mode']=='price':
        # Full-size research proxy: use the freshest print already known when
        # latency expires, regardless of buyer role. If none is fresh, use the
        # first subsequent print inside the fill window. Size is intentionally
        # ignored; strict capacity testing is the separate volume mode.
        quotes=[]
        for source in book.roles.values():
            quote=source.asof(begin,c['max_age_sec'])
            if quote is not None:
                quotes.append((int(quote[1]),float(quote[0])))
        if quotes:
            _,raw=max(quotes,key=lambda q:q[0]);t=begin
        else:
            future=[]
            for source in book.roles.values():
                i=int(np.searchsorted(source.t,begin,side='right'))
                if i<len(source.t) and int(source.t[i])<=end:
                    future.append((int(source.t[i]),float(source.p[i])))
            if not future:
                return [],qty,end
            t,raw=min(future,key=lambda q:q[0])
        underlying=spots.asof(t,c['spot_age_sec'])
        if underlying is None:
            return [],qty,end
        price=raw*(1+(-1 if side=='sell' else 1)*c['slippage_pct']/100)
        fee=min(qty*underlying[0]*c['fee_pct']/100,qty*price*c['fee_cap_pct']/100)*(1+c['tax_pct']/100)
        fill=dict(timestamp_ns=t,time=iso(t),side=side,quantity_btc=qty,price=price,raw_price=raw,
                  fee=fee,slippage=qty*abs(price-raw),underlying=underlying[0])
        return [fill],0.,t
    ticks=book.roles[role(side)]
    first=int(np.searchsorted(ticks.t,begin,side='right'))
    last=int(np.searchsorted(ticks.t,end,side='right'))
    remaining=qty
    fills=[]
    for i in range(first,last):
        t=int(ticks.t[i])
        underlying=spots.asof(t,c['spot_age_sec'])
        if underlying is None:
            continue
        # Contracts are indivisible. Fractional participation is rounded down per print.
        capacity=math.floor(float(ticks.size[i])*c['participation_pct']/100+1e-10)*.001
        take=min(remaining,capacity)
        if take<=1e-12:
            continue
        raw=float(ticks.p[i]);price=raw*(1+(-1 if side=='sell' else 1)*c['slippage_pct']/100)
        fee=min(take*underlying[0]*c['fee_pct']/100,take*price*c['fee_cap_pct']/100)*(1+c['tax_pct']/100)
        fills.append(dict(timestamp_ns=t,time=iso(t),side=side,quantity_btc=take,price=price,raw_price=raw,
                          fee=fee,slippage=take*abs(price-raw),underlying=underlying[0]))
        remaining-=take
        if remaining<=1e-10:
            break
    return fills,max(remaining,0),end


def fill_cash(fills):
    return sum((1 if f['side']=='sell' else -1)*f['quantity_btc']*f['price']-f['fee'] for f in fills)


def marks(legs,spots,t,c,with_greeks=False):
    close_cost=0; exposure=dict(delta=0.,gamma=0.,theta=0.,vega=0.); valid_greeks=True
    spot=spots.asof(t,c['spot_age_sec'])
    if spot is None:
        return None
    for l in legs:
        b=l['book'];side=opposite(l['side']);q=b.roles[role(side)].asof(t,c['max_age_sec'])
        if q is None:
            return None
        price=q[0]*(1+(1 if side=='buy' else -1)*c['slippage_pct']/100)
        fee=min(l['quantity']*spot[0]*c['fee_pct']/100,l['quantity']*price*c['fee_cap_pct']/100)*(1+c['tax_pct']/100)
        close_cost+=(1 if side=='buy' else -1)*l['quantity']*price+fee
        if with_greeks:
            g=model(b,q,spots,t,c)
            if g is None:
                valid_greeks=False
            else:
                for k in exposure:
                    exposure[k]+=(1 if l['side']=='buy' else -1)*l['quantity']*g[k]
    return close_cost,exposure if valid_greeks else None


def replay_day(date,books,spots,c,equity,progress):
    midnight=pd.Timestamp(date,tz='UTC').value
    at=lambda clock:midnight+(int(clock[:2])*3600+int(clock[3:])*60)*SECOND
    entry=at(c['entry_time']);scheduled=at(c['exit_time']);last_entry=entry+c['entry_window_min']*60*SECOND
    skip=Counter();candidate=None
    for t in range(entry,last_entry+1,60*SECOND):
        candidate,reason=select_legs(books,spots,t,c)
        if candidate:
            if c['sizing_mode']=='capital' and candidate['reserve']>max(0,equity)*c['allocation_pct']/100:
                reason='insufficient_margin_reserve';candidate=None
            else:
                break
        skip[reason]+=1
    if candidate is None:
        return None,dict(skip)
    legs=candidate['legs'];decision=t;entry_fills=[];complete=True;deadline=0
    for leg in legs:
        fills,remaining,end=fill_order(leg['book'],leg['side'],leg['quantity'],decision,spots,c,scheduled-1)
        leg['entry_fills']=fills;leg['filled_qty']=sum(f['quantity_btc'] for f in fills)
        entry_fills+=fills;complete &= remaining<=1e-10;deadline=max(deadline,end)
    if not entry_fills:
        return None,dict(skip,entry_unfilled=1)
    completion=max(f['timestamp_ns'] for f in entry_fills)
    # Preserve partially filled structures; never use future fill success to erase existing exposure.
    credit=sum((1 if f['side']=='sell' else -1)*f['quantity_btc']*f['price'] for f in entry_fills)
    cash=fill_cash(entry_fills)
    active=[{**l,'quantity':l['filled_qty']} for l in legs if l['filled_qty']>1e-10]
    paths=[];observations=0;fresh=0;invalid_greeks=0;reason='time_exit';trigger=scheduled
    greek_at_entry={k:sum((1 if l['side']=='buy' else -1)*l['filled_qty']*l['greeks'][k] for l in active) for k in ('delta','gamma','theta','vega')}
    if not complete:
        reason='partial_entry_unwind';trigger=deadline
    elif credit<=0 or credit<c['min_credit']:
        reason='credit_changed_unwind';trigger=completion
    else:
        arrays=[]
        for leg in active:
            ticks=leg['book'].roles[role(opposite(leg['side']))].t
            arrays.append(ticks[(ticks>=completion)&(ticks<=scheduled)])
        if c['delta_exit']>0:
            arrays.append(spots.t[(spots.t>=completion)&(spots.t<=scheduled)])
        events=np.unique(np.concatenate([*arrays,np.array([completion,scheduled],dtype=np.int64)]))
        last_greek=0;last_exposure=greek_at_entry
        for idx,tick in enumerate(events):
            tick=int(tick)
            if idx%4000==0:
                progress(f'Replaying {date}: {idx:,}/{len(events):,} risk events')
            observations+=1
            calculate_greeks=c['delta_exit']>0 or tick-last_greek>=60*SECOND
            m=marks(active,spots,tick,c,calculate_greeks)
            if m is None:
                continue
            fresh+=1;close_cost,g=m;pnl=cash-close_cost
            if calculate_greeks:
                last_greek=tick;last_exposure=g
                if g is None:
                    invalid_greeks+=1
            delta=last_exposure['delta'] if last_exposure else None
            # Net liquidation P&L includes entry/estimated exit fees and adverse slippage.
            hit=None
            if pnl<=-credit*c['stop_loss_pct']/100:
                hit='credit_stop'
            if c['max_loss_usd']>0 and pnl<=-c['max_loss_usd']:
                hit='cash_stop'
            if c['delta_exit']>0 and delta is not None and abs(delta)>=c['delta_exit']:
                hit='delta_exit'
            if hit is None and pnl>=credit*c['take_profit_pct']/100:
                hit='profit_target'
            # Keep exact risk extrema separately; chart sampling cannot change metrics.
            paths.append(dict(t=tick,pnl=pnl,delta=delta,gamma=last_exposure['gamma'] if last_exposure else None,
                              theta=last_exposure['theta'] if last_exposure else None,vega=last_exposure['vega'] if last_exposure else None))
            if hit:
                trigger=tick;reason=hit;break
    exit_fills=[];unresolved=[];exit_completion=trigger
    for leg in active:
        fills,remaining,end=fill_order(leg['book'],opposite(leg['side']),leg['quantity'],trigger,spots,c,
                                       midnight+86400*SECOND-1)
        # Retry an outstanding exit once. The first attempt's volume is never reused.
        if remaining>1e-10:
            retry,left,_=fill_order(leg['book'],opposite(leg['side']),remaining,end,spots,c,
                                   midnight+86400*SECOND-1)
            fills+=retry;remaining=left
        leg['exit_fills']=fills;exit_fills+=fills
        if fills:
            exit_completion=max(exit_completion,max(f['timestamp_ns'] for f in fills))
        if remaining>1e-10:
            unresolved.append(dict(symbol=leg['book'].symbol,side=leg['side'],quantity_btc=remaining))
    net= cash+fill_cash(exit_fills) if not unresolved else None
    if net is not None:
        paths.append(dict(t=exit_completion,pnl=net,delta=0.,gamma=0.,theta=0.,vega=0.))
    fees=sum(f['fee'] for f in entry_fills+exit_fills)
    slip=sum(f['slippage'] for f in entry_fills+exit_fills)
    minp=min([0.]+[p['pnl'] for p in paths]);maxp=max([0.]+[p['pnl'] for p in paths])
    # Retain every running peak/trough for exact drawdown; keep minute-level Greek charts.
    path_equity=[(p['t'],p['pnl']) for p in paths]
    compact=[];last_bucket=None
    for p in paths:
        bucket=p['t']//(60*SECOND)
        if bucket!=last_bucket:
            compact.append(p);last_bucket=bucket
    if paths and (not compact or compact[-1]!=paths[-1]):
        compact.append(paths[-1])
    serialized=[]
    for leg in active:
        serialized.append(dict(symbol=leg['book'].symbol,type=leg['book'].kind,strike=leg['book'].strike,
            expiry=iso(leg['book'].expiry),side=leg['side'],quantity_btc=leg['quantity'],greeks=leg['greeks'],
            entry_fills=leg['entry_fills'],exit_fills=leg['exit_fills']))
    planned=[dict(symbol=l['book'].symbol,side=l['side'],requested_btc=l['quantity'],filled_btc=l['filled_qty'],
                  selection_greeks=l['greeks']) for l in legs]
    row=dict(date=date,decision_time=iso(decision),entry_time=iso(completion),exit_time=iso(exit_completion) if not unresolved else None,
        exit_trigger=iso(trigger),exit_reason=reason,status='unresolved' if unresolved else 'closed',
        entry_complete=complete,entry_credit=credit,net_pnl=net,gross_pnl=net+fees if net is not None else None,
        fees=fees,slippage=slip,margin_reserve=candidate['reserve'],underlying_entry=candidate['spot'],
        mae=minp,mfe=maxp,mark_events=observations,fresh_marks=fresh,invalid_greek_events=invalid_greeks,
        mark_coverage_pct=100*fresh/observations if observations else None,
        entry_greeks=greek_at_entry,legs=serialized,planned_legs=planned,unresolved=unresolved,path=compact,
        execution_model=('full requested BTC at a fresh observed option price' if c['execution_mode']=='price'
                         else 'independent side-aware volume-constrained trade-print fills'),
        execution_window_risk='Stops monitored after all entry fills; drawdown between individual fills may be unobserved.')
    return (row,path_equity),dict(skip)


def metrics(trades,days,capital,rate,path,unresolved=False,sizing_mode='capital'):
    closed=[t for t in trades if t['net_pnl'] is not None]
    pnls=np.array([t['net_pnl'] for t in closed],dtype=float)
    daily_map={t['date']:t['net_pnl'] for t in closed}
    daily=[];eq=capital
    for date in days:
        pnl=daily_map.get(date,0.)
        ret=pnl/eq if eq>0 else None
        eq+=pnl
        daily.append(dict(date=date,pnl=pnl,equity=eq,return_pct=ret*100 if ret is not None else None))
    returns=np.array([d['return_pct']/100 for d in daily if d['return_pct'] is not None])
    valid_return=len(returns)==len(days) and eq>0
    excess=returns-rate/100/365
    sd=float(np.std(excess,ddof=1)) if len(excess)>1 else 0
    down=math.sqrt(float(np.mean(np.minimum(excess,0)**2))) if len(excess) else 0
    peak=capital;maxdd=0.;maxddpct=0.;curve=[]
    for t,e in path:
        peak=max(peak,e);dd=peak-e;ddpct=dd/peak*100 if peak>0 else 0
        maxdd=max(maxdd,dd);maxddpct=max(maxddpct,ddpct)
        curve.append(dict(time=iso(t),equity=e,drawdown=-dd,drawdown_pct=-ddpct))
    wins=float(pnls[pnls>0].sum());losses=-float(pnls[pnls<0].sum())
    count=len(pnls);duration=max(len(days),1)
    annualized=(math.exp(math.log(eq/capital)*365/duration)-1)*100 if eq>0 and abs(math.log(eq/capital)*365/duration)<700 else None
    obs=sum(t['mark_events'] for t in trades);fresh=sum(t['fresh_marks'] for t in trades)
    worst=float(pnls.min()) if count else None
    tail=np.sort(pnls)[:max(1,math.ceil(count*.05))]
    result=dict(trade_count=count,unresolved_count=sum(t['status']=='unresolved' for t in trades),
        net_pnl=float(pnls.sum()),realized_closed_pnl=float(pnls.sum()),return_pct=(eq/capital-1)*100,
        final_equity=eq,max_drawdown=maxdd,max_drawdown_pct=maxddpct,
        sharpe=float(np.mean(excess)/sd*math.sqrt(365)) if sd>1e-12 and valid_return else None,
        sortino=float(np.mean(excess)/down*math.sqrt(365)) if down>1e-12 and valid_return else None,
        cagr_pct=annualized if duration>=365 and valid_return else None,
        calmar=annualized/maxddpct if duration>=30 and annualized is not None and maxddpct>0 and valid_return else None,
        profit_factor=wins/losses if losses>0 else None,win_rate=100*float((pnls>0).mean()) if count else None,
        average_trade=float(pnls.mean()) if count else None,worst_trade=worst,best_trade=float(pnls.max()) if count else None,
        expected_shortfall_95=float(tail.mean()) if count else None,fees=sum(t['fees'] for t in trades),
        slippage=sum(t['slippage'] for t in trades),mark_coverage_pct=100*fresh/obs if obs else None,
        sample_days=len(days),daily=daily,curve=curve)
    if sizing_mode == 'btc':
        # Fixed BTC size has no account-value denominator. Report a P&L path
        # and zero-benchmark daily P&L ratios, independent of legacy capital.
        daily_pnl=np.array([d['pnl'] for d in daily],dtype=float)
        pnl_sd=float(np.std(daily_pnl,ddof=1)) if len(daily_pnl)>1 else 0
        pnl_down=math.sqrt(float(np.mean(np.minimum(daily_pnl,0)**2))) if len(daily_pnl) else 0
        result['sharpe']=float(np.mean(daily_pnl)/pnl_sd*math.sqrt(365)) if pnl_sd>1e-12 else None
        result['sortino']=float(np.mean(daily_pnl)/pnl_down*math.sqrt(365)) if pnl_down>1e-12 else None
        for key in ('return_pct','final_equity','max_drawdown_pct','cagr_pct','calmar'):
            result[key]=None
        for row in daily:
            row['equity']-=capital;row['return_pct']=None
        for point in curve:
            point['equity']-=capital;point['drawdown_pct']=None
        result['ratio_basis']='Daily USD P&L at fixed BTC size; zero benchmark; sqrt(365)'
    if unresolved:
        for key in ('net_pnl','return_pct','final_equity','max_drawdown','max_drawdown_pct','sharpe','sortino','cagr_pct','calmar','profit_factor','win_rate','average_trade'):
            result[key]=None
    return result


def run_experiment(c,data_root,cache,progress=lambda message,fraction:None):
    c=validate_request(c)
    dates=[str(t.date()) for t in pd.date_range(c['start'],c['end'],tz='UTC')]
    if c['mode']=='sweep':
        grids=[[float(x.strip()) for x in c[k].split(',')] for k in ('grid_delta','grid_stop','grid_tp')]
        configs=[{**c,'call_delta':d,'put_delta':d,'stop_loss_pct':s,'take_profit_pct':p}
                 for d,s,p in itertools.product(*(list(dict.fromkeys(v)) for v in grids))]
    else:
        configs=[c]
    state=[dict(config=cfg,trades=[],days=[],skips=Counter(),equity=cfg['capital'],path=[],halted=False,missing=[],sources=[],diagnostics=[])
           for cfg in configs]
    months=sorted({d[:7] for d in dates});sources=[]
    for month_i,month in enumerate(months):
        option_file=data_root/'options_data'/f'BTC_{month}.csv'
        futures_file=data_root/'futures_data'/f'BTCUSD_{month}.csv'
        selected=[d for d in dates if d.startswith(month)]
        if not option_file.exists() or not futures_file.exists():
            for s in state:
                for date in selected:
                    s['missing'].append(date);s['skips']['missing_source_pair']+=1
            continue
        progress(f'Preparing {month} · first use builds the daily cache',month_i/len(months))
        def indexing(message):
            progress(message,month_i/len(months))
        option_dir,om=index_source(option_file,cache,indexing)
        future_dir,fm=index_source(futures_file,cache,indexing)
        sources.extend([om,fm])
        for date in selected:
            # Days are loaded once and reused across all variants.
            options=load_day(option_dir,date);futures=load_day(future_dir,date)
            fraction=(month_i+(selected.index(date)+1)/len(selected))/len(months)
            if options.empty or futures.empty:
                for s in state:
                    s['missing'].append(date);s['skips']['missing_daily_pair']+=1
                continue
            books=build_books(options,c['expiry_hour']);spots=Ticks.frame(futures)
            for idx,s in enumerate(state):
                cfg=s['config'];weekday=pd.Timestamp(date).dayofweek
                def tick_progress(message):
                    progress(f'{message} · configuration {idx+1}/{len(state)}',min(.99,(month_i+(selected.index(date)+idx/len(state))/len(selected))/len(months)))
                tick_progress(f'Replaying {date}')
                if s['halted']:
                    s['skips']['halted_after_unresolved_or_insolvency']+=1;continue
                if cfg['days']=='weekdays' and weekday>=5 or cfg['days']=='weekends' and weekday<5:
                    s['skips']['weekday_filter']+=1;continue
                outcome,skips=replay_day(date,books,spots,cfg,s['equity'],tick_progress)
                s['skips'].update(skips)
                if outcome:
                    trade,path=outcome
                    s['trades'].append(trade)
                    s['path'].extend((t,s['equity']+p) for t,p in path)
                    if trade['net_pnl'] is None:
                        s['halted']=True
                    else:
                        s['equity']+=trade['net_pnl']
                        if cfg['sizing_mode']=='capital' and s['equity']<=0:
                            s['halted']=True
                else:
                    s['skips']['no_entry_days']+=1
    split=max(1,min(len(dates)-1,int(len(dates)*c['train_pct']/100)))
    train_days,test_days=dates[:split],dates[split:]
    result_runs=[]
    for i,s in enumerate(state):
        start_ns=pd.Timestamp(c['start'],tz='UTC').value
        full_path=[(start_ns,c['capital'])]+s['path']
        # Add end-of-day equity so dates without entries remain visible.
        eq=c['capital'];bydate={t['date']:t for t in s['trades']}
        for date in dates:
            trade=bydate.get(date)
            if trade and trade['net_pnl'] is None:
                break
            if trade:
                eq+=trade['net_pnl']
            full_path.append((pd.Timestamp(date,tz='UTC').value+86400*SECOND-1,eq))
        full_path.sort(key=lambda p:p[0])
        has_open=any(t['net_pnl'] is None for t in s['trades'])
        m=metrics(s['trades'],dates,c['capital'],c['rate_pct'],full_path,has_open,c['sizing_mode'])
        def subset(selected):
            ts=[t for t in s['trades'] if t['date'] in selected]
            ps=[(pd.Timestamp(selected[0],tz='UTC').value,c['capital'])] if selected else []
            # Rebase each subperiod to starting capital, preserving its actual P&L path.
            before=sum(t['net_pnl'] or 0 for t in s['trades'] if t['date']<selected[0]) if selected else 0
            lower=pd.Timestamp(selected[0],tz='UTC').value if selected else 0
            upper=pd.Timestamp(selected[-1],tz='UTC').value+86400*SECOND if selected else 0
            ps.extend((t,e-before) for t,e in full_path if lower<=t<upper)
            return metrics(ts,selected,c['capital'],c['rate_pct'],ps,any(t['net_pnl'] is None and t['date']<=selected[-1] for t in s['trades']) if selected else False,c['sizing_mode'])
        train=subset(train_days) if c['mode']=='sweep' else None
        test=subset(test_days) if c['mode']=='sweep' else None
        # Downsample display curve while retaining per-bucket extrema. Metrics used full event path.
        def thin(summary):
            curve=summary['curve'];out=[];stride=max(1,len(curve)//600)
            for begin in range(0,len(curve),stride):
                bucket=curve[begin:begin+stride]
                chosen={0,len(bucket)-1,min(range(len(bucket)),key=lambda j:bucket[j]['equity']),max(range(len(bucket)),key=lambda j:bucket[j]['equity'])}
                out.extend(bucket[j] for j in sorted(chosen))
            summary['curve']=out
        thin(m)
        if train:thin(train)
        if test:thin(test)
        result_runs.append(dict(index=i,config=s['config'],metrics=m,development=train,holdout=test,
                                trades=s['trades'],skips=dict(s['skips']),missing_days=s['missing'],
                                quality=dict(incomplete_entries=sum(not t['entry_complete'] for t in s['trades']),
                                             invalid_greek_events=sum(t['invalid_greek_events'] for t in s['trades']))))
    selected_index=0;eligible=[];winner=False
    if c['mode']=='sweep':
        for run in result_runs:
            m=run['development'];objective=c['objective']
            value=m['max_drawdown'] if objective=='drawdown' else m[objective]
            development_missing=any(d in train_days for d in run['missing_days'])
            run['eligible']=m['trade_count']>=c['min_trades'] and m['unresolved_count']==0 and value is not None and (c['sizing_mode']=='btc' or (m['final_equity'] is not None and m['final_equity']>0)) and not development_missing
            run['objective_value']=value
            if run['eligible']:
                eligible.append(((-value if objective=='drawdown' else value),run['index']))
        if eligible:
            selected_index=max(eligible,key=lambda x:(x[0],-x[1]))[1];winner=True
    return dict(engine_version=VERSION,source_root=str(data_root),sources=sources,runs=result_runs,
                selected_index=selected_index,winner_selected=winner,
                split_date=test_days[0] if c['mode']=='sweep' else None,
                assumptions=['BTC-size mode omits account capital and margin eligibility; USD P&L ratios use daily P&L with a zero benchmark.' if c['sizing_mode']=='btc' else 'Capital mode uses account reserve eligibility and daily equity returns.', 'USD linear premiums; one contract = 0.001 BTC.',
                    'Futures used as a spot proxy; no official settlement, order book, funding, hedges, or liquidation.',
                    'Risk monitoring starts after entry completion; execution-window drawdowns may be unobserved.',
                    'Observed intraday drawdown is a lower bound when marks are stale or absent.',
                    'Identical rows deduplicated without trade IDs; legitimate identical prints may be conservatively removed.',
                    'Fee parameters are fixed assumptions for the whole sample, not a verified historical fee schedule.',
                    'Missing dates stay visible; a missing-data run is an incomplete sample, not an all-days result.'])
