import unittest
from unittest.mock import patch
from paper_portfolio import blank, eligible, process

class PaperTests(unittest.TestCase):
    def test_no_independent_quote_no_fill(self):
        a={"metrics":{"breakout_at_daily_close":True,"trend_confirmed":True,
             "rvol20":2,"atr14_wilder":3,"close_date":"2026-11-18","last_close":100},
           "quality_state":"HISTORICO_VALIDO_PRELIMINAR","bars_ohlcv":250,
           "mapping_verified":True,"independent_match":False,"currency":"USD",
           "research_state":"VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE",
           "underlying":"TEST","cedear":"TEST"}
        self.assertFalse(eligible(a))
        p=process({"generated_at":"2026-11-19T10:00:00Z","assets":[a]},blank())
        self.assertEqual(p["cash"],1000)
        self.assertEqual(len(p["positions"]),0)
        self.assertEqual(p["pending"],[])
    def test_verified_signal_is_pending_not_filled(self):
        a={"metrics":{"breakout_at_daily_close":True,"trend_confirmed":True,
             "rvol20":2,"atr14_wilder":3,"close_date":"2026-11-18","last_close":100},
           "quality_state":"HISTORICO_VALIDO_PRELIMINAR","bars_ohlcv":250,
           "mapping_verified":True,"independent_match":True,"currency":"USD",
           "research_state":"VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE",
           "underlying":"TEST","cedear":"TEST"}
        p=process({"generated_at":"2026-11-19T10:00:00Z","assets":[a]},blank())
        self.assertEqual(len(p["pending"]),1)
        self.assertEqual(len(p["positions"]),0)
        self.assertEqual(p["cash"],1000)
        self.assertEqual(process({"generated_at":"2026-11-19T10:00:00Z","assets":[a]},p)["pending"],p["pending"])


    def test_full_buy_then_sell_demo_no_real_market_orders(self):
        """Synthetic closes: arm -> buy -> take profit; never touches broker."""
        a={"underlying":"DEMO","cedear":"DEMO","currency":"USD",
           "bars_ohlcv":260,"quality_state":"HISTORICO_VALIDO_PRELIMINAR",
           "independent_match":True,
           "research_state":"VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE",
           "metrics":{"breakout_at_daily_close":True,"trend_confirmed":True,
                      "rvol20":1.6,"atr14_wilder":4,
                      "close_date":"2026-11-16","last_close":100}}
        l=process({"generated_at":"2026-11-17T01:00:00Z","assets":[a]},blank())
        self.assertEqual(len(l["pending"]),1)
        sources={"yahoo":"MOCK_YAHOO","stooq":"MOCK_STOOQ"}
        with patch("paper_portfolio.confirmed_close",return_value=(
            {"date":"2026-11-17","close":101},sources)):
            l=process({"generated_at":"2026-11-18T01:00:00Z","assets":[]},l)
        self.assertEqual(len(l["positions"]),1)
        self.assertEqual(l["events"][0]["type"],"BUY")
        self.assertEqual(l["positions"][0]["quantity"],3)
        with patch("paper_portfolio.confirmed_close",return_value=(
            {"date":"2026-11-18","close":120},sources)):
            l=process({"generated_at":"2026-11-19T01:00:00Z","assets":[]},l)
        self.assertEqual(len(l["positions"]),0)
        self.assertEqual(len(l["closed"]),1)
        self.assertEqual([e["type"] for e in l["events"]],["BUY","SELL"])
        self.assertGreater(l["cash"],1000)
        self.assertEqual(l["events"][-1]["reason"],"TARGET_DAILY_CLOSE")
        n=len(l["events"])
        l=process({"generated_at":"2026-11-19T01:00:00Z","assets":[]},l)
        self.assertEqual(len(l["events"]),n)

if __name__=="__main__":
    unittest.main()
