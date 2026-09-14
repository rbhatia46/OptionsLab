import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from app.options_lab.rsi_option_seller import (RsiOptionConfig, compute_rsi_signal, performance,
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


if __name__ == '__main__':
    unittest.main()
