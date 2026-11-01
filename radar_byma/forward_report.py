#!/usr/bin/env python3
"""Publish strictly prospective paper-trade state. Never backfill or manufacture orders.
Reads ledger committed by frozen daily trading monitor. No synchronization with browser paper book.
"""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SRC=Path("radar_byma/state/paper_ledger.json")
OUT=Path("docs/data/forward_status.json")
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
def main():
    ledger=json.loads(SRC.read_text(encoding="utf-8")) if SRC.exists() else {}
    from_day=ledger.get("started_after") or None
    source_paper=ledger.get("paper",{})
    rows={}
    for capital,state in source_paper.items():
        orders=state.get("orders",[])
        valid=[]
        for o in orders:
            # Preserve only actual recorded forward orders, with source identity and after frozen start date.
            dt=str(o.get("fecha") or o.get("date") or o.get("entry_date") or "")
            if from_day and dt and dt[:10]<=from_day:continue
            valid.append(o)
        rows[capital]={"closed_or_recorded_orders":len(valid),
                       "open_positions":len(state.get("positions",{})),
                       "pending_entries":len(state.get("pending",{})),
                       "rejections":len(state.get("rejections",[])),
                       "signals_seen":len(state.get("signals",[])),
                       "portfolio_equity_ars":state.get("equity"),
                       "capital_ars":float(capital)}
    payload={"generated_at":NOW.isoformat(),"kind":"FORWARD_LEDGER_ONLY",
       "strategy_state":"EXPERIMENTAL_NOT_PROVEN",
       "from_exclusive":from_day,"last_processed_session":ledger.get("last_processed"),
       "portfolio_tracking":rows,
       "description":"Operaciones de papel prospectivas registradas desde el inicio del monitor; nunca registros inventados. Cartera del radar NO sincronizada con el navegador.",
       "warning":"El historial 0 o pequeño no demuestra ventaja. Deslizamiento, corporate actions y spreads no están comprobados. El seguimiento no equivale a ejecución de broker."}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("FORWARD_QUALITY",json.dumps({"from":from_day,"processed":ledger.get("last_processed"),"portfolios":rows},ensure_ascii=False))
if __name__=="__main__":main()
