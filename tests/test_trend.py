import unittest

import numpy as np
import pandas as pd

from app.options_lab.engine import DEFAULTS, metrics, validate_request
from app.options_lab.trend import SECOND, build_bars, replay_bars


class TrendTests(unittest.TestCase):
    def test_daily_bars_align_to_ist_midnight(self):
        times=pd.to_datetime(['2026-06-01 18:29:59Z','2026-06-01 18:30:00Z','2026-06-02 18:29:59Z'])
        ticks=pd.DataFrame(dict(timestamp_ns=times.as_unit('ns').astype('int64'),price=[100.,101.,102.],size=[1.,1.,1.]))
        bars=build_bars(ticks,'1D')
        self.assertEqual(len(bars),2)
        self.assertEqual(pd.Timestamp(int(bars.iloc[1].t),tz='UTC').tz_convert('Asia/Kolkata').hour,0)
        self.assertEqual(bars.iloc[1].open,101.)
        self.assertEqual(bars.iloc[1].close,102.)

    def test_crossover_signal_executes_at_next_bar(self):
        prices=[100.,101.,102.,103.,90.,80.]
        bars=pd.DataFrame(dict(t=np.arange(len(prices))*60*SECOND,open=prices,high=prices,low=prices,close=prices,volume=1.,ticks=1))
        config={**DEFAULTS,'strategy_family':'trend','trend_strategy':'ma_crossover','trend_timeframe':'1m',
                'trend_ma_type':'ema','trend_fast':2,'trend_slow':3,'quantity_btc':1.,'slippage_pct':0.,'fee_pct':0.,'tax_pct':0.}
        trades,_,_=replay_bars(bars,validate_request(config))
        self.assertGreaterEqual(len(trades),1)
        self.assertEqual(pd.Timestamp(trades[0]['entry_time']).value,3*60*SECOND)
        self.assertEqual(trades[0]['underlying_entry'],103.)

    def test_metrics_sum_multiple_futures_exits_on_same_day(self):
        base=dict(date='2026-06-01',status='closed',fees=0.,slippage=0.,mark_events=1,fresh_marks=1)
        result=metrics([{**base,'net_pnl':10.},{**base,'net_pnl':-3.}],['2026-06-01'],10000,0,[(0,10000),(SECOND,10007)],False,'btc')
        self.assertEqual(result['daily'][0]['pnl'],7.)
        self.assertEqual(result['net_pnl'],7.)

    def test_invalid_trend_parameters_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'Fast moving-average'):
            validate_request({'strategy_family':'trend','trend_fast':50,'trend_slow':20})
        with self.assertRaises(ValueError):
            validate_request({'strategy_family':'trend','trend_timeframe':'7m'})

    def test_unused_option_session_rules_do_not_block_trend_run(self):
        config=validate_request({'strategy_family':'trend','start':'2026-06-01','end':'2026-06-01',
                                 'days':'weekends','entry_time':'11:00','exit_time':'11:01',
                                 'entry_window_min':120,'fill_timeout_sec':600})
        self.assertEqual(config['strategy_family'],'trend')


if __name__ == '__main__':
    unittest.main()
