#!/usr/bin/env python3
"""Prospective observation-only RSI35 challenger; locked on 2026-10-31.
Does not send trade orders or backfill paper trades before November 2026.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import pandas as pd
import research_advanced as ra
from research_advanced import load,simulate,STRATEGIES

NAME="rsi35_challenger_2026_11"
START=pd.Timestamp("2026-11-02")
COST_NOTE="0.50% fee + 0.05% rights with 21% VAT, plus 0.10% slippage per side (illustrative)."
OUT=Path("resultados/challenger")
OUT.mkdir(parents=True,exist_ok=True)
def main():
    data,rejected=load()
    for df in data.values():
        df[NAME]=df["reversion_rsi14"].fillna(False)
    STRATEGIES[NAME]={"stop":1.5,"target":4.5,"hold":15}
    ra.FEE=(.005+.0005)*1.21
    ra.SLIPPAGE=.001 if hasattr(ra,'SLIPPAGE') else .001
    ra.SLIP=.001
    today=datetime.now(ZoneInfo("America/Argentina/Cordoba")).date()
    # Refuse to use incomplete same-day candles even when IOL publishes them.
    cut=pd.Timestamp(today)-pd.Timedelta(days=1)
    end=min((frame.index.max() for frame in data.values()),default=pd.Timestamp("2026-10-30"))
    finish=min(cut,end)
    response={"status":"NO_FUTURE_SESSION_YET","phase":"FORWARD_PAPER_ONLY",
              "strategy":NAME,"predeclared":"2026-10-31",
              "from":str(START.date()),"through":str(finish.date()),
              "costs":COST_NOTE,"rejected_sources":rejected,
              "warning":"This is a paper reconstruction from each completed bar, NOT a real broker fill or executed notification."}
    if finish>=START:
        results=[]
        for cap in [50000,100000]:
            summary,orders,curve=simulate(data,NAME,START,finish,cap)
            results.append(summary)
            pd.DataFrame(orders).to_csv(OUT/f"orders_{cap}.csv",index=False)
            pd.DataFrame(curve).to_csv(OUT/f"equity_{cap}.csv",index=False)
        response.update(status="PAPER_SIMULATION_COMPUTED",results=results)
    (OUT/"current.json").write_text(json.dumps(response,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print("CHALLENGER_RSI35 "+json.dumps(response,ensure_ascii=False,default=str))
if __name__=="__main__": main()
