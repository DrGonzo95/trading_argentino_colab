import unittest
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

if __name__=="__main__":
    unittest.main()
