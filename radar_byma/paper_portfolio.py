#!/usr/bin/env python3
"""Fail-closed, USD-only paper ledger driven by audited underlying radar.
No broker connection, no retroactive fills, no CEDEAR ARS conversion.
Daily bars cannot establish intraday order; entries use next observed close
only, after an earlier validated signal, with conservative gap/stop rules.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/data/underlying_radar.json"
LEDGER = ROOT / "docs/data/paper_portfolio.json"
CAPITAL = 1000.0
RISK = .02
EXPOSURE = .40

def blank():
    return {"schema":1, "currency":"USD", "initial_cash":CAPITAL,
            "cash":CAPITAL, "positions":[], "closed":[], "events":[],
            "processed_report_at":None, "pending":[], "updated_at":None,
            "status":"PAPER_ONLY_NO_BROKER"}

def eligible(a):
    m=a.get("metrics") or {}
    return (a.get("quality_state")=="HISTORICO_VALIDO_PRELIMINAR"
            and a.get("bars_ohlcv",0)>=220
            and a.get("mapping_verified") is True
            and a.get("independent_match") is True
            and a.get("currency")=="USD"
            and a.get("research_state")=="VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE"
            and m.get("breakout_at_daily_close") is True
            and m.get("trend_confirmed") is True
            and m.get("rvol20",0)>=1.0
            and m.get("atr14_wilder",0)>0)

def process(report, ledger):
    stamp=report.get("generated_at")
    if not stamp or stamp==ledger.get("processed_report_at"):
        return ledger
    if ledger.get("processed_report_at") and stamp<ledger["processed_report_at"]:
        return ledger
    # Report timestamp is not an exchange trade timestamp. Never fill from it.
    # Only arm a prospective signal, after independent data checks.
    pending=[]
    for a in report.get("assets",[]):
        if not eligible(a):
            continue
        m=a["metrics"]
        pending.append({"symbol":a["underlying"],"cedear":a["cedear"],
                        "signal_close_date":m["close_date"],
                        "signal_close":m["last_close"],
                        "atr":m["atr14_wilder"],
                        "state":"WAIT_NEXT_SESSION_VERIFIED_EXECUTION",
                        "reason":"No timestamped independent next-session execution price, spread or costs"})
    ledger["pending"]=pending
    ledger["processed_report_at"]=stamp
    ledger["updated_at"]=datetime.now(timezone.utc).isoformat()
    ledger["status"]="NO_EXECUTABLE_FILLS_UNTIL_INDEPENDENT_EXECUTION_DATA"
    return ledger

def main():
    if not REPORT.exists():
        raise SystemExit("No radar report: refuse to trade")
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    ledger=json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else blank()
    ledger=process(report,ledger)
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    LEDGER.write_text(json.dumps(ledger,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"report":ledger["processed_report_at"],"pending":len(ledger["pending"]),
                      "positions":len(ledger["positions"]),"closed":len(ledger["closed"]),
                      "cash":ledger["cash"],"status":ledger["status"]}))

if __name__=="__main__":
    main()
