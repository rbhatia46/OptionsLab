import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.options_lab.engine import Ticks
from app.options_lab.pricing import YEAR_NS, price
from app.options_lab.rsi_option_seller import (IST, RsiOptionConfig, _modeled_exit,
                                                compute_rsi_signal, performance,
                                                signal_changed_before_fill)


class RsiOptionSellerTests(unittest.TestCase):
    def test_rsi_compares_with_sma_of_rsi_and_has_both_states(self):
        prices=np.r_[np.linspace(100,130,80),np.linspace(130,80,80),np.linspace(80,120,80)]
        bars=pd.DataFrame(dict(t=np.arange(len(prices)),open=prices,high=prices,low=prices,close=prices,volume=1.,ticks=1))
        result=compute_rsi_signal(bars,14,50)
        self.assertIn(1,set(result.signal))
        self.assertIn(-1,set(result.signal))
        valid=result.dropna(subset=['rsi_sma'])
        self.assertTrue(((valid.signal==1)==(valid.rsi>valid.rsi_sma)).all())

    def test_combined_metrics_sum_multiple_timeframes_per_day(self):
        trades=[dict(exit_time_ist='2026-06-01T10:00:00+05:30',net_pnl=10.,gross_pnl=12.,fees=2.,slippage=1.),
                dict(exit_time_ist='2026-06-01T11:00:00+05:30',net_pnl=-3.,gross_pnl=-2.,fees=1.,slippage=1.)]
        summary,daily=performance(trades,'2026-06-01','2026-06-02')
        self.assertEqual(summary['net_pnl'],7.)
        self.assertEqual(summary['market_pnl_before_costs'],12.)
        self.assertEqual(daily.iloc[0].net_pnl,7.)

    def test_config_rejects_non_contract_quantity(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=RsiOptionConfig(Path(tmp),Path(tmp)/'out',quantity_btc=.0005)
            with self.assertRaisesRegex(ValueError,'0.001'):
                config.validate()

    def test_pending_entry_is_cancelled_when_signal_flips_before_fill(self):
        width=5*60*1_000_000_000
        bars=pd.DataFrame({'t':[0,width,2*width],'signal':[1,-1,-1]})
        self.assertTrue(signal_changed_before_fill(bars,width,width,2*width,1))
        self.assertFalse(signal_changed_before_fill(bars,width,2*width,2*width+30_000_000_000,-1))

    def test_unobserved_exit_uses_prior_iv_without_future_data(self):
        quote_ns=pd.Timestamp('2026-01-01 10:00',tz=IST).tz_convert('UTC').value
        decision_ns=pd.Timestamp('2026-01-01 11:00',tz=IST).tz_convert('UTC').value
        expiry_ns=pd.Timestamp('2026-01-02 17:30',tz=IST).tz_convert('UTC').value
        volatility=.7
        premium=price('C',100.,110.,(expiry_ns-quote_ns)/YEAR_NS,0.,volatility)
        history=pd.DataFrame({'timestamp_ns':[quote_ns],'price':[premium],
                              'symbol':['C-BTC-110-020126']})

        class FakeArchive:
            def option_window(self, start_ns, end_ns, symbol):
                self.bounds=(start_ns,end_ns,symbol)
                return history

        with tempfile.TemporaryDirectory() as tmp:
            config=RsiOptionConfig(Path(tmp),Path(tmp)/'out',slippage_pct=1.)
            spots=Ticks(np.array([quote_ns,decision_ns],dtype=np.int64),
                        np.array([100.,105.]),np.ones(2))
            archive=FakeArchive()
            fill=_modeled_exit(archive,spots,'C-BTC-110-020126',decision_ns,config)
        expected=price('C',105.,110.,(expiry_ns-decision_ns)/YEAR_NS,0.,volatility)
        self.assertEqual(fill['price_source'],'black_scholes_exit_proxy')
        self.assertAlmostEqual(fill['raw_price'],expected,places=6)
        self.assertAlmostEqual(fill['price'],expected*1.01,places=6)
        self.assertLessEqual(archive.bounds[1],decision_ns)


if __name__ == '__main__':
    unittest.main()
