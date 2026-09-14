import math
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

from app.options_lab.engine import (DEFAULTS, SECOND, Book, Ticks, fill_order, fill_cash, metrics,
                                     replay_day, select_legs, validate_request, run_experiment)
from app.options_lab.pricing import price, implied_vol, greeks
from app.options_lab.data import index_source


class PricingTests(unittest.TestCase):
    def test_put_call_parity_and_iv_roundtrip(self):
        for years in (1/365,.2,1):
            call=price('C',60000,61000,years,.03,.65)
            put=price('P',60000,61000,years,.03,.65)
            self.assertAlmostEqual(call-put,60000-61000*math.exp(-.03*years),places=7)
            for kind,premium in [('C',call),('P',put)]:
                self.assertAlmostEqual(implied_vol(kind,60000,61000,years,.03,premium),.65,places=6)

    def test_delta_gamma_match_finite_differences(self):
        S=60000;K=61000;T=.1;r=.01;vol=.7;h=.5
        g=greeks('P',S,K,T,r,vol)
        middle=price('P',S,K,T,r,vol)
        up=price('P',S+h,K,T,r,vol);down=price('P',S-h,K,T,r,vol)
        self.assertAlmostEqual(g['delta'],(up-down)/(2*h),places=7)
        self.assertAlmostEqual(g['gamma'],(up-2*middle+down)/h**2,places=8)
        self.assertIsNone(implied_vol('C',100,90,1,0,5))
        self.assertIsNone(implied_vol('P',100,90,0,0,5))


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.t=pd.Timestamp('2026-06-01T06:00:00Z').value
        self.c={**DEFAULTS,'latency_sec':1.,'fill_timeout_sec':10.,'participation_pct':10.,'slippage_pct':1.,'spot_age_sec':60.,'entry_window_min':0}
        self.spot=Ticks(np.array([self.t+i*SECOND for i in range(-300,22000,5)],dtype=np.int64),np.full(4460,60000.),np.ones(4460))
        # Construct arrays from timestamps to keep fixtures independent of row count assumptions.
        self.spot.p=np.full(len(self.spot.t),60000.);self.spot.size=np.ones(len(self.spot.t))

    def ticks(self,seconds,prices,sizes):
        return Ticks(np.array([self.t+i*SECOND for i in seconds],dtype=np.int64),np.array(prices,dtype=float),np.array(sizes,dtype=float))

    def book(self,kind='C',strike=61000,roles=None):
        return Book(f'{kind}-BTC-{strike}-010626',kind,strike,self.t+6*3600*SECOND,roles or {})

    def test_fill_is_future_side_aware_capacity_limited_and_costed(self):
        book=self.book(roles={'maker':self.ticks([0,1,2,3],[1,1,100,110],[1e6,1e6,500,500]),'taker':self.ticks([2],[5000],[1e6])})
        fills,left,_=fill_order(book,'sell',.1,self.t,self.spot,self.c)
        self.assertAlmostEqual(left,0)
        self.assertEqual(len(fills),2)
        self.assertTrue(all(f['timestamp_ns']>self.t+SECOND for f in fills))
        self.assertAlmostEqual(sum(f['quantity_btc'] for f in fills),.1)
        self.assertAlmostEqual(sum(f['price']*f['quantity_btc'] for f in fills),10.395)
        self.assertAlmostEqual(fill_cash(fills),10.395-sum(f['fee'] for f in fills))

    def test_price_proxy_fills_full_btc_from_fresh_observed_print(self):
        book=self.book(roles={'maker':self.ticks([-1],[60],[1]),'taker':self.ticks([-2],[65],[1])})
        c={**self.c,'execution_mode':'price','quantity_btc':1.}
        fills,left,_=fill_order(book,'sell',1.,self.t,self.spot,c)
        self.assertEqual(left,0)
        self.assertEqual(len(fills),1)
        self.assertEqual(fills[0]['quantity_btc'],1.)
        self.assertEqual(fills[0]['timestamp_ns'],self.t+SECOND)
        self.assertAlmostEqual(fills[0]['raw_price'],60.)

    def test_price_proxy_exit_can_use_bounded_stale_observed_print(self):
        book=self.book(roles={'maker':self.ticks([-7200],[60],[1]),'taker':self.ticks([-7200],[65],[1])})
        c={**self.c,'execution_mode':'price','quantity_btc':1.,'exit_price_max_age_sec':21600.}
        fills,left,_=fill_order(book,'buy',1.,self.t,self.spot,c,price_max_age_sec=c['exit_price_max_age_sec'],allow_future=False)
        self.assertEqual(left,0)
        self.assertEqual(fills[0]['price_source'],'bounded_stale_exit_price')
        self.assertEqual(fills[0]['quote_age_sec'],7201.)

    def test_price_proxy_exit_rejects_observation_older_than_bound(self):
        book=self.book(roles={'maker':self.ticks([-22000],[60],[1]),'taker':self.ticks([-22000],[65],[1])})
        c={**self.c,'execution_mode':'price','quantity_btc':1.,'exit_price_max_age_sec':21600.}
        fills,left,_=fill_order(book,'buy',1.,self.t,self.spot,c,price_max_age_sec=c['exit_price_max_age_sec'],allow_future=False)
        self.assertEqual(fills,[])
        self.assertEqual(left,1.)

    def test_asof_never_uses_future_and_rejects_stale(self):
        ticks=self.ticks([-10,10],[100,999],[100,100])
        self.assertEqual(ticks.asof(self.t,20)[0],100)
        self.assertIsNone(ticks.asof(self.t,5))

    def test_unresolved_entry_is_kept_and_no_synthetic_close(self):
        book=self.book(roles={'maker':self.ticks([-1,2],[60,60],[1000,500]),'taker':self.ticks([-1],[65],[1000])})
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'min_credit':0.,'quantity_btc':.1}
        outcome,skips=replay_day('2026-06-01',{book.symbol:book},self.spot,c,10000,lambda _:None)
        self.assertIsNotNone(outcome)
        row,path=outcome
        self.assertFalse(row['entry_complete'])
        self.assertEqual(row['status'],'unresolved')
        self.assertIsNone(row['net_pnl'])
        self.assertAlmostEqual(row['unresolved'][0]['quantity_btc'],.05)

    def test_partial_entry_unwind_realizes_loss_and_fees(self):
        book=self.book(roles={'maker':self.ticks([-1,2],[60,60],[1000,500]),'taker':self.ticks([-1,14],[65,80],[1000,1000])})
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'min_credit':0.,'quantity_btc':.1}
        outcome,_=replay_day('2026-06-01',{book.symbol:book},self.spot,c,10000,lambda _:None)
        row,_=outcome
        self.assertEqual(row['status'],'closed')
        self.assertEqual(row['exit_reason'],'partial_entry_unwind')
        self.assertLess(row['net_pnl'],-1.)

    def test_future_tick_change_does_not_change_selection(self):
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'min_credit':0.}
        book=self.book(roles={'maker':self.ticks([-1,2],[60,1],[1000,1000]),'taker':self.ticks([-1],[65],[1000])})
        before,_=select_legs({book.symbol:book},self.spot,self.t,c)
        book.roles['maker'].p[1]=999999
        after,_=select_legs({book.symbol:book},self.spot,self.t,c)
        self.assertEqual(before['credit'],after['credit'])
        self.assertEqual(before['legs'][0]['greeks'],after['legs'][0]['greeks'])

    def test_otm_selection_rejects_strike_beyond_distance_tolerance(self):
        premium=price('C',60000,65000,6/24/365,0,.7)
        book=self.book('C',65000,{'maker':self.ticks([-1],[premium],[1000]),'taker':self.ticks([],[],[])})
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'otm_tolerance_pct':1.,'min_credit':0.}
        candidate,reason=select_legs({book.symbol:book},self.spot,self.t,c)
        self.assertIsNone(candidate)
        self.assertEqual(reason,'no_eligible_short_leg')

    def test_future_only_atm_strike_does_not_change_straddle(self):
        c={**self.c,'structure':'straddle','min_credit':0.}
        books={}
        for kind in ('C','P'):
            b=self.book(kind,61000,{'maker':self.ticks([-1],[price(kind,60000,61000,6/24/365,0,.7)],[1000]),'taker':self.ticks([],[],[])})
            books[b.symbol]=b
        before,_=select_legs(books,self.spot,self.t,c)
        for kind in ('C','P'):
            b=self.book(kind,60000,{'maker':self.ticks([10],[400],[1000]),'taker':self.ticks([],[],[])})
            books[b.symbol]=b
        after,_=select_legs(books,self.spot,self.t,c)
        self.assertEqual([l['book'].symbol for l in before['legs']],[l['book'].symbol for l in after['legs']])

    def test_price_proxy_selection_accepts_fresh_trade_from_either_role(self):
        premium=price('C',60000,61000,6/24/365,0,.7)
        book=self.book('C',61000,{'maker':self.ticks([],[],[]),
                                  'taker':self.ticks([-1],[premium],[1000])})
        c={**self.c,'execution_mode':'price','structure':'short_call','selection':'otm',
           'otm_pct':1.,'otm_tolerance_pct':1.,'min_credit':0.}
        candidate,reason=select_legs({book.symbol:book},self.spot,self.t,c)
        self.assertIsNone(reason)
        self.assertEqual(candidate['legs'][0]['book'].symbol,book.symbol)

    def test_participation_never_creates_fractional_contracts(self):
        book=self.book(roles={'maker':self.ticks([2,3],[100,100],[9,19]),'taker':self.ticks([],[],[])})
        fills,left,_=fill_order(book,'sell',.01,self.t,self.spot,self.c)
        self.assertEqual(len(fills),1)
        self.assertAlmostEqual(fills[0]['quantity_btc'],.001)
        self.assertAlmostEqual(left,.009)

    def test_stop_triggers_on_mark_but_fills_after_latency(self):
        book=self.book(roles={'maker':self.ticks([-1,2],[60,60],[1000,1000]),
                             'taker':self.ticks([-1,5,7],[65,150,180],[1000,1000,1000])})
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'min_credit':0.,'quantity_btc':.1}
        outcome,_=replay_day('2026-06-01',{book.symbol:book},self.spot,c,10000,lambda _:None)
        trade,_=outcome
        self.assertEqual(trade['exit_reason'],'credit_stop')
        self.assertEqual(trade['exit_trigger'],pd.Timestamp(self.t+5*SECOND,tz='UTC').isoformat())
        self.assertEqual(trade['legs'][0]['exit_fills'][0]['timestamp_ns'],self.t+7*SECOND)
        self.assertLess(trade['net_pnl'],-trade['entry_credit'])

    def test_custom_spread_keeps_short_and_long_signs(self):
        c={**self.c,'structure':'custom','min_credit':0.,'delta_tolerance':.3,
           'legs':[dict(type='C',side='sell',delta=.2,ratio=1),dict(type='C',side='buy',delta=.1,ratio=1)]}
        books={}
        for strike in (61000,62000):
            premium=price('C',60000,strike,6/24/365,0,.7)
            b=self.book('C',strike,{'maker':self.ticks([-1],[premium],[1000]),'taker':self.ticks([-1],[premium],[1000])})
            books[b.symbol]=b
        selected,_=select_legs(books,self.spot,self.t,c)
        self.assertIsNotNone(selected)
        self.assertEqual([l['side'] for l in selected['legs']],['sell','buy'])
        self.assertGreater(selected['credit'],0)

    def test_initial_loss_is_drawdown_and_zero_days_in_returns(self):
        trades=[dict(date='2026-06-01',net_pnl=-100.,status='closed',fees=1,slippage=1,mark_events=10,fresh_marks=8)]
        m=metrics(trades,['2026-06-01','2026-06-02'],1000,0,[(self.t,1000),(self.t+1,850),(self.t+2,900)])
        self.assertEqual(m['max_drawdown'],150)
        self.assertEqual(m['closed_trade_max_drawdown'],100)
        self.assertEqual(m['daily'][1]['pnl'],0)
        self.assertEqual(m['mark_coverage_pct'],80)
        self.assertLess(m['sharpe'],0)
        censored=metrics(trades,['2026-06-01'],1000,0,[(self.t,900)],True)
        self.assertIsNone(censored['net_pnl'])
        self.assertIsNone(censored['sharpe'])

    def test_btc_size_bypasses_capital_but_keeps_fill_limits(self):
        book=self.book(roles={'maker':self.ticks([-1,2],[60,60],[1000,500]),'taker':self.ticks([-1,14],[65,80],[1000,1000])})
        c={**self.c,'structure':'short_call','selection':'otm','otm_pct':1.,'min_credit':0.,'quantity_btc':1.,'capital':100}
        blocked,skips=replay_day('2026-06-01',{book.symbol:book},self.spot,c,100,lambda _:None)
        self.assertIsNone(blocked)
        self.assertEqual(skips['insufficient_margin_reserve'],1)
        outcome,_=replay_day('2026-06-01',{book.symbol:book},self.spot,{**c,'sizing_mode':'btc'},100,lambda _:None)
        self.assertIsNotNone(outcome)
        trade,_=outcome
        self.assertFalse(trade['entry_complete'])
        self.assertEqual(trade['exit_reason'],'partial_entry_unwind')

    def test_btc_metrics_have_no_capital_denominator(self):
        trades=[dict(date='2026-06-01',net_pnl=-1500.,status='closed',fees=1,slippage=1,mark_events=1,fresh_marks=1)]
        results=[]
        for capital in (1000,100000):
            results.append(metrics(trades,['2026-06-01','2026-06-02'],capital,10,[(self.t,capital),(self.t+1,capital-1500)],sizing_mode='btc'))
        self.assertEqual(results[0],results[1])
        self.assertEqual(results[0]['max_drawdown'],1500)
        self.assertEqual(results[0]['curve'][-1]['equity'],-1500)
        self.assertIsNone(results[0]['return_pct'])
        self.assertIsNone(results[0]['final_equity'])
        self.assertLess(results[0]['sharpe'],0)
        censored=metrics(trades,['2026-06-01'],1000,0,[(self.t,1000)],True,'btc')
        self.assertIsNone(censored['net_pnl'])
        self.assertIsNone(censored['sharpe'])

    def test_invalid_configs_rejected(self):
        for patch in [dict(call_delta=float('nan')),dict(quantity_btc=.0015),dict(exit_time='12:00'),dict(mode='sweep',start='2026-06-01',end='2026-06-02'),dict(fake=1)]:
            with self.assertRaises(ValueError):
                validate_request(patch)

    def test_day_filter_cannot_exclude_entire_sample(self):
        with self.assertRaisesRegex(ValueError,'excludes every date'):
            validate_request(dict(start='2026-06-01',end='2026-06-01',days='weekends'))
        self.assertEqual(validate_request(dict(start='2026-06-06',end='2026-06-06',days='weekends'))['days'],'weekends')


class IngestTests(unittest.TestCase):
    def test_dedup_invalid_dates_hash_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'BTC_2026-06.csv'
            source.write_text('product_symbol,price,size,timestamp,buyer_role\nC-BTC-61000-010626,50,2,2026-06-01 06:00:00,maker\nC-BTC-61000-010626,50,2,2026-06-01 06:00:00,maker\nC-BTC-61000-010626,-50,2,2026-06-01 06:00:00,maker\nC-BTC-61000-010626,50,2,bad,maker\n')
            folder,m=index_source(source,root/'cache',lambda _:None)
            self.assertEqual(m['quality']['invalid_rows'],2)
            self.assertEqual(m['quality']['duplicate_rows'],1)
            self.assertEqual(len(m['sha256']),64)
            again,m2=index_source(source,root/'cache',lambda _:self.fail('cache rebuilt'))
            self.assertEqual(folder,again)
            self.assertEqual(m,m2)


class ExperimentTests(unittest.TestCase):
    def test_missing_sources_are_visible_and_no_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            c={**DEFAULTS,'start':'2026-06-01','end':'2026-06-10','mode':'sweep','grid_delta':'.2','grid_stop':'100','grid_tp':'50'}
            result=run_experiment(c,Path(tmp),Path(tmp)/'cache')
            self.assertFalse(result['winner_selected'])
            self.assertEqual(len(result['runs'][0]['missing_days']),10)
            self.assertEqual(result['split_date'],'2026-06-08')

    def test_holdout_outcome_cannot_change_development_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for directory,filename in [('options_data','BTC_2026-06.csv'),('futures_data','BTCUSD_2026-06.csv')]:
                (root/directory).mkdir();(root/directory/filename).touch()
            c={**DEFAULTS,'start':'2026-06-01','end':'2026-06-10','mode':'sweep','grid_delta':'.15,.2',
               'grid_stop':'100','grid_tp':'50','min_trades':1,'objective':'net_pnl'}
            def replay(date,books,spots,cfg,equity,progress):
                # .15 wins development, but loses on the independent later dates.
                in_train=date<'2026-06-08'
                pnl=(2 if cfg['call_delta']==.15 else 1) if in_train else (-100 if cfg['call_delta']==.15 else 100)
                trade=dict(date=date,net_pnl=pnl,status='closed',fees=0,slippage=0,mark_events=1,fresh_marks=1,entry_complete=True,invalid_greek_events=0)
                return (trade,[(pd.Timestamp(date,tz='UTC').value+SECOND,pnl)]),{}
            frame=pd.DataFrame(dict(timestamp_ns=[0],price=[1.],size=[1.]))
            with patch('app.options_lab.engine.index_source',return_value=(root,{})),patch('app.options_lab.engine.load_day',return_value=frame),patch('app.options_lab.engine.build_books',return_value={}),patch('app.options_lab.engine.replay_day',side_effect=replay):
                result=run_experiment(c,root,root/'cache')
            self.assertTrue(result['winner_selected'])
            self.assertEqual(result['selected_index'],0)
            self.assertGreater(result['runs'][0]['development']['net_pnl'],result['runs'][1]['development']['net_pnl'])
            self.assertLess(result['runs'][0]['holdout']['net_pnl'],result['runs'][1]['holdout']['net_pnl'])


if __name__=='__main__':
    unittest.main()
