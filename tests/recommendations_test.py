#!/usr/bin/env python3
"""Regression tests for conservative, evidence-linked per-asset research guidance."""
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from radar_byma.recommendations import decision, NOW

DAY=(NOW.date()-timedelta(days=1)).isoformat()
BASE={
 "symbol":"TEST","kind":"accion","status":"SOLO_SEGUIMIENTO","quote_price":100.0,
 "quote_retrieved_at":DAY+"T18:00:00-03:00","technical_score":None,
 "rsi14":None,"daily_bar_date":None,"change_pct":0.0,"events":[]
}
CHART={"last_candle":DAY,"source":"IOL", "bars":[[DAY,99.,101.,98.,100.,10000]]}
SECOND={"status":"MATCH","market_date":DAY,"difference_pct":0.0}
def rec(**mod):
    a=BASE.copy();a.update(mod)
    return decision(a,CHART,SECOND,True,True)

class ResearchAdviceTests(unittest.TestCase):
    def test_missing_technicals_never_buy(self):
        r=rec()
        self.assertEqual(r["code"],"ESPERAR_TECNICO")
        self.assertFalse(r["real_trade_allowed"])
        self.assertFalse(r["strategy_proven"])
    def test_news_fall_is_research_not_buy(self):
        r=rec(status="CAIDA_CON_NOVEDAD_INVESTIGAR",change_pct=-5.0)
        self.assertEqual(r["code"],"INVESTIGAR_CAIDA")
        self.assertIn("no comprar",r["next_step"].lower())
    def test_valid_setup_only_paper(self):
        r=rec(status="ENTRADA_TEORICA_PAPEL",entry_ref=100.0,stop_ref=95.0,
             target_ref=115.0,rr_net_est=2.4,daily_bar_date=DAY)
        self.assertEqual(r["code"],"SIMULAR_ENTRADA")
        self.assertFalse(r["real_trade_allowed"])
    def test_mismatched_source_blocks_setup(self):
        a=BASE.copy()
        a.update(status="ENTRADA_TEORICA_PAPEL",entry_ref=100.,
           stop_ref=95.,target_ref=115.,rr_net_est=2.4,daily_bar_date=DAY)
        r=decision(a,CHART,{"status":"DIVERGENCE","market_date":DAY,
                            "difference_pct":4.0},True,True)
        self.assertEqual(r["code"],"REVISAR_DISCREPANCIA")
    def test_internal_panel_mismatch_blocks(self):
        a=BASE.copy()
        a.update(status="ENTRADA_TEORICA_PAPEL",quote_price=109.,
            entry_ref=100.,stop_ref=95.,target_ref=115.,rr_net_est=2.4,daily_bar_date=DAY)
        r=decision(a,CHART,SECOND,True,True)
        self.assertEqual(r["code"],"REVISAR_DISCREPANCIA")
    def test_partial_signal_never_simulates(self):
        r=rec(status="ENTRADA_TEORICA_PAPEL",daily_bar_date=DAY)
        self.assertEqual(r["code"],"ESPERAR_VALIDACION")
    def test_official_publication_visible_without_technical(self):
        r=rec(status="NOVEDAD_OFICIAL")
        self.assertEqual(r["code"],"REVISAR_CNV")
    def test_bond_not_equity_rule(self):
        r=rec(kind="bono")
        self.assertEqual(r["code"],"ANALIZAR_CONTRATO")
    def test_stale_second_source_does_not_validate(self):
        r=decision(BASE,CHART,{"status":"MATCH","market_date":"2020-01-01",
                   "difference_pct":0},True,True)
        self.assertFalse(r["independent_verified"])
    def test_every_record_has_recommendation_after_export(self):
        if not (ROOT/"docs/data/market.json").exists():return
        data=json.loads((ROOT/"docs/data/market.json").read_text(encoding="utf-8"))
        self.assertTrue(data["assets"])
        self.assertEqual(len(data["assets"]),data["summary"]["total"])
        self.assertEqual(sum(data["summary"].get("recommendation_counts",{}).values()),len(data["assets"]))
        self.assertTrue(all(a["recommendation"]["real_trade_allowed"] is False
                            and a["recommendation"]["strategy_proven"] is False
                            and a["recommendation"]["next_step"]
                            for a in data["assets"]))
if __name__=="__main__":
    unittest.main()
