#!/usr/bin/env python3
"""Export strictly observed local daily OHLCV data for mobile BYMA charting.
No simulated candles. Excludes invalid/corporate-action-suspect prices and
makes it explicit which symbols have NO real price series available.
"""
import json,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
ROOT=Path("resultados")
CACHE=Path("radar_byma/cache/ohlcv")
OUT=Path("docs/data")
OUT.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
def valid_series(path):
    d=pd.read_csv(path)
    if not all(k in d for k in ("date","open","high","low","close","volume")):return None
    d["date"]=pd.to_datetime(d.date,errors="coerce")
    d=d.dropna(subset=["date","open","high","low","close","volume"]).sort_values("date")
    d=d.drop_duplicates("date",keep="last")
    if len(d)<80:return None
    ohlc=d[["open","high","low","close"]].apply(pd.to_numeric,errors="coerce")
    volume=pd.to_numeric(d.volume,errors="coerce")
    if not ohlc.notna().all().all() or not volume.notna().all():return None
    if not (ohlc>0).all().all() or (volume<0).any():return None
    if ((ohlc.high<ohlc[["open","low","close"]].max(axis=1))|(ohlc.low>ohlc[["open","high","close"]].min(axis=1))).mean()>.02:return None
    if (d.close.pct_change().abs()>.35).any():return None
    if (d.date.diff().dt.days>21).any():return None
    if len(d)>260:d=d.tail(260).copy()
    result=[]
    for r in d.itertuples():
        vals=[float(r.open),float(r.high),float(r.low),float(r.close),float(r.volume)]
        if not all(math.isfinite(x) for x in vals):return None
        result.append([r.date.date().isoformat(),round(vals[0],4),round(vals[1],4),round(vals[2],4),round(vals[3],4),int(vals[4])])
    return result
def main():
    symbols={}
    skips={}
    sources=list(ROOT.glob("*_ohlcv.csv"))+list(CACHE.glob("*.csv"))
    for path in sorted(sources):
        sym=path.stem.removesuffix("_ohlcv")
        if sym in symbols:continue
        if sym.endswith(("_US","_D")):continue
        try:
            d=valid_series(path)
            if d is None:skips[sym]="Datos diarios inválidos o insuficientes";continue
            symbols[sym]={"source":"IOL historical daily BCBA, source data unadjusted",
                         "last_candle":d[-1][0],"timeframe":"1D","bars":d}
        except Exception as e:skips[sym]=str(e)[:100]
    payload={"generated_at":NOW.isoformat(),"timeframe":"1D",
      "chart_data":"DAILY_HISTORICAL_ONLY_NOT_LIVE",
      "candle_format":"[YYYY-MM-DD,open,high,low,close,volume]",
      "provider":"IOL historical public BCBA", "symbols":symbols,
      "limitations":["No live streaming or intraday candles",
         "Open/high/low/close and volume are not corporate-action/dividend adjusted",
         "Some historical price jumps may be due to splits, distributions or FX factors",
         "Candles represent past sessions only; reference lines are theoretical paper levels",
         "No historical price source means no chart; never invent candles."]}
    p=OUT/"charts.json"
    p.write_text(json.dumps(payload,separators=(",",":"),ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("CHART_HISTORY "+json.dumps({"symbols":len(symbols),"candles":sum(len(v["bars"]) for v in symbols.values()),"skipped":skips,"bytes":p.stat().st_size},ensure_ascii=False))
if __name__=="__main__":main()
