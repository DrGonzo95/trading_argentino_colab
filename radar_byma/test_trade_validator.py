"""Unit tests exercise validation logic with synthetic bars, NOT a real-market backtest."""
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
import validate_daily_trades as v

class ValidatorTests(unittest.TestCase):
    def make_bars(self, rows=450):
        # Synthetic monotonic market, valid arithmetic but not evidence of a real trade.
        dates=pd.bdate_range(end=v.last_completed("US"),periods=rows)
        close=np.linspace(100.,150.,rows)
        return pd.DataFrame({
            "date":dates,"open":close,"high":close*1.012,
            "low":close*.988,"close":close,
            "volume":np.full(rows,1_000_000,dtype=float)
        })
    def test_220_bars_required(self):
        with self.assertRaises(ValueError):
            v.check_bars(self.make_bars(210),"US")
    def test_all_indicators_calculated_with_450_bars(self):
        x=v.indicators(v.check_bars(self.make_bars(450),"US"))
        keys=("ema20","ema50","ema200","rsi14","macd","macds","atr14","rvol20","res20")
        for name in keys:
            self.assertTrue(np.isfinite(float(x.iloc[-1][name])),name)
        self.assertEqual(float(x.iloc[-1]["rsi14"]),100.)
    def test_bad_ohlc_rejected(self):
        d=self.make_bars()
        d.loc[len(d)-1,"high"]=1
        with self.assertRaises(ValueError):
            v.check_bars(d,"US")
    def test_costs_reduce_reward_risk(self):
        d=v.indicators(v.check_bars(self.make_bars(),"US"))
        _state,setup=v.plan(d,.0025,True)
        self.assertIsNone(setup) # No invented signal from ordinary synthetic trend.
    def test_chronological_replay_never_calls_it_calibrated(self):
        d=v.indicators(v.check_bars(self.make_bars(),"US"))
        x=v.backtest_chronological(d,.0025)
        self.assertEqual(x["probabilidad"],"NO_CALIBRADA")

if __name__=="__main__":
    unittest.main()
