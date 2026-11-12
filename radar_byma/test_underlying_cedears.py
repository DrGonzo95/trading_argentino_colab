#!/usr/bin/env python3
"""Offline synthetic tests; no provider calls, orders or account credentials."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from underlying_cedears import (SEEDS, choose, ema, get_hist, indicators,
                                parse_reference, safe_symbol, wilder)

class UnderlyingTests(unittest.TestCase):
    def test_reference_ticker_is_explicit_not_guessed(self):
        page = """<table><tr>
        <th>Programa de CEDEAR</th><th>Ratio Cedear / valor sub-yacente</th>
        <th>Id de mercado</th><th>Ticker en mercado de origen</th>
        <th>ISIN valor subyacente</th><th>Mercado de valor subyacente</th></tr>
        <tr><td>Adecoagro</td><td>1:2</td><td>ADGO</td><td>AGRO</td>
        <td>LU0584671464</td><td>New York</td></tr>
        <tr><td>Applied Materials</td><td>5:1</td><td>AMAT</td><td>AMAT</td>
        <td>US0382221051</td><td>NASDAQ GS</td></tr>
        <tr><td>OTC only</td><td>1:1</td><td>FOO</td><td>FOOF</td>
        <td>US0000000000</td><td>OTC US</td></tr></table>"""
        mapping = parse_reference(page)
        self.assertEqual(mapping["ADGO"]["ticker"], "AGRO")
        self.assertEqual(mapping["AMAT"]["ticker"], "AMAT")
        self.assertNotIn("FOO", mapping)
        self.assertTrue(mapping["AMAT"]["mapping_verified"])

    def test_bad_symbols_rejected(self):
        self.assertIsNone(safe_symbol("AAPL&whatever"))
        self.assertIsNone(safe_symbol("QQQ US Equity"))
        self.assertEqual(safe_symbol("BRK/B"), "BRK-B")

    def test_synthetic_ohlcv_features(self):
        bars = []
        first=datetime(2025,1,1).date()
        for i in range(260):
            c = 100 + i * 0.15
            bars.append({"date":str(first+timedelta(days=i)),
                         "open":c-0.4,"high":c+1,"low":c-1.2,
                         "close":c,"volume":1000+i})
        i=indicators(bars)
        self.assertTrue(i["trend_confirmed"])
        self.assertGreater(i["atr14_wilder"],0)
        self.assertGreater(i["rvol20"],0)
        self.assertAlmostEqual(i["resistance20_prior"], bars[-2]["high"])
        self.assertGreater(i["rsi14_wilder"],90)

    def test_no_lookahead_prior_resistance(self):
        bars=[]
        for i in range(240):
            c=10+0.01*i
            bars.append({"date":str(datetime(2025,1,1).date()+timedelta(days=i)),
                         "open":c,"high":c+0.5,"low":c-0.5,
                         "close":c,"volume":100})
        bars[-1]["high"]=1000
        x=indicators(bars)
        self.assertLess(x["resistance20_prior"],100)
        self.assertEqual(x["rvol20"],1.0)

    def test_only_listed_can_be_selected(self):
        mp={"AMAT":{"ticker":"AMAT"},"MRNA":{"ticker":"MRNA"}}
        chosen,count=choose(mp,{"AMAT","UNRELATED"}, {"watched_symbols":["MRNA"]})
        self.assertEqual(chosen,["AMAT"])
        self.assertEqual(count,1)

    def test_yahoo_meta_mismatch_blocks_signal(self):
        class FakeResponse:
            url="https://query1.finance.yahoo.com/v8/finance/chart/AMAT"
            def raise_for_status(self): pass
            def json(self):
                return {"chart":{"result":[{"meta":{"symbol":"ANOTHER","currency":"USD",
                    "exchangeName":"NMS"},"timestamp":[],"indicators":{"quote":[]}}]}}
        class FakeSession:
            def get(self,*args,**kwargs):return FakeResponse()
        with self.assertRaisesRegex(ValueError,"ESPECIE_NO_COINCIDE"):
            get_hist(FakeSession(),"AMAT")

if __name__=="__main__":
    unittest.main()
