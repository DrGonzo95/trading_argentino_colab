#!/usr/bin/env python3
"""PULSO BYMA: frozen RSI35 research audit, not a prediction or market-data certification.
No look-ahead: signal after day t close, next-session OPEN entry. No tuned params.
Conservative stop-first on bars where both stop and target trade.
This is a trade-event sample, NOT a portfolio return or validated live strategy.
"""
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

OUT=Path("docs/data/strategy_audit.json")
FEE_SIDE=(.0055*1.21)       # 0.5% broker + 0.05% market rights, VAT 21%
SLIPPAGE=.001              # 0.10% per side (assumption, not observed spread)
STOP_ATR=1.2
TARGET_ATR=3.5
MAX_HOLD=14
MIN_ROWS=400
TZ=ZoneInfo("America/Argentina/Cordoba")

def audit_source(path):
    d=pd.read_csv(path)
    needed={"date","open","high","low","close","volume"}
    if not needed.issubset(d.columns):
        return None,"faltan columnas"
    d["date"]=pd.to_datetime(d["date"],errors="coerce")
    for c in needed-{"date"}:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    if d[list(needed)].isnull().any().any() or len(d)<MIN_ROWS: return None,"menos de 400 ruedas o datos incompletos"
    if d["date"].duplicated().any(): return None,"fechas duplicadas"
    d=d.sort_values("date").reset_index(drop=True)
    if (d[["open","high","low","close"]]<=0).any().any():return None,"precios no positivos"
    if (d["volume"]<0).any():return None,"volumen negativo"
    if ((d["high"]<d[["open","close","low"]].max(axis=1)) |
        (d["low"]>d[["open","close","high"]].min(axis=1))).any():return None,"inconsistencia OHLC"
    if (d["close"].pct_change().abs()>.35).any():return None,"salto diario >35%, revisar ajuste corporativo"
    if (d["date"].diff().dt.days>21).any():return None,"hueco histórico >21 días"
    return d,None

def compute_signals(d):
    diff=d["close"].diff()
    up=diff.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    dn=(-diff).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean().replace(0,np.nan)
    rsi=100-100/(1+up/dn)
    ema200=d["close"].ewm(span=200,adjust=False,min_periods=200).mean()
    prev_close=d["close"].shift(1)
    tr=pd.concat([(d["high"]-d["low"]),(d["high"]-prev_close).abs(),
                  (d["low"]-prev_close).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    valid=((d["close"]>ema200)&(rsi.shift(1)<=35)&(rsi>35)&
           np.isfinite(atr)&(atr>0))
    return valid.fillna(False).to_numpy(),atr.to_numpy()

def simulate_one(sym,d):
    signal,atr=compute_signals(d)
    out=[]
    i=200
    while i<len(d)-1:
        if not signal[i]:
            i+=1
            continue
        # First tradable point after observing the complete candle at i.
        nxt=i+1
        raw_entry=float(d.at[nxt,"open"])
        entry=raw_entry*(1+SLIPPAGE)
        stop=entry-STOP_ATR*float(atr[i])
        target=entry+TARGET_ATR*float(atr[i])
        buy=entry*(1+FEE_SIDE)
        risk=buy-stop*(1-FEE_SIDE-SLIPPAGE)
        reward=target*(1-FEE_SIDE-SLIPPAGE)-buy
        if stop<=0 or risk<=0 or reward/risk<2:
            i+=1;continue
        exit_j=min(nxt+MAX_HOLD-1,len(d)-1)
        exit_price=float(d.at[exit_j,"close"])
        why="tiempo"
        for j in range(nxt,exit_j+1):
            o,h,l=(float(d.at[j,k]) for k in ("open","high","low"))
            # For the entry candle, orders are effective after entry at open.
            if o<=stop:
                exit_price=o;why="gap_stop";exit_j=j;break
            if o>=target:
                exit_price=o;why="gap_target";exit_j=j;break
            if l<=stop:
                exit_price=stop;why="stop";exit_j=j;break
            if h>=target:
                exit_price=target;why="target";exit_j=j;break
        proceeds=exit_price*(1-SLIPPAGE)*(1-FEE_SIDE)
        net_pct=(proceeds/buy-1)*100
        out.append({"symbol":sym,"signal_date":str(d.at[i,"date"].date()),
                    "entry_date":str(d.at[nxt,"date"].date()),
                    "exit_date":str(d.at[exit_j,"date"].date()),
                    "entry":round(entry,4),"exit":round(exit_price,4),
                    "return_pct":round(net_pct,5),"exit_reason":why})
        i=exit_j+1 # never overlap positions in same species
    return out

def metrics(ts):
    n=len(ts)
    if n==0:return {"trades":0,"win_rate_pct":None,"mean_net_pct":None,
                    "median_net_pct":None,"profit_factor":None,
                    "max_drawdown_pct":None,"expectancy_r":None}
    r=np.array([t["return_pct"] for t in ts],dtype=float)
    wins=float(r[r>0].sum())
    losses=float(-r[r<0].sum())
    # Compounded sequential equal full-capital hypothetical trades, NOT a real portfolio.
    equity=np.cumprod(1+r/100)
    peak=np.maximum.accumulate(np.r_[1.,equity])[1:]
    drawdown=(equity/peak-1)*100
    pf=(round(wins/losses,3) if losses>0 else None)
    return {"trades":n,"win_rate_pct":round(float((r>0).mean()*100),2),
            "mean_net_pct":round(float(np.mean(r)),3),
            "median_net_pct":round(float(np.median(r)),3),
            "profit_factor":pf,"max_drawdown_pct":round(float(drawdown.min()),2),
            "hypothetical_sequential_return_pct":round(float((equity[-1]-1)*100),2)}

def main():
    files={}
    for path in list(sorted(Path("resultados").glob("*_ohlcv.csv")))+list(sorted(Path("radar_byma/cache/ohlcv").glob("*.csv"))):
        sym=path.stem.removesuffix("_ohlcv")
        files.setdefault(sym,path)
    histories={}
    rejected={}
    rows={}
    for sym,path in files.items():
        try:
            d,error=audit_source(path)
            if error:rejected[sym]=error;continue
            histories[sym]=d
            rows[sym]=len(d)
        except Exception as error:
            rejected[sym]=str(error)[:120]
    if histories:
        # Freeze a chronological calendar split, not chosen using returns.
        dates=sorted(set(x.date() for d in histories.values() for x in d["date"]))
        pivot=dates[int(len(dates)*.60)]
        all_trades=[t for sym,d in histories.items() for t in simulate_one(sym,d)]
        all_trades.sort(key=lambda x:(x["entry_date"],x["symbol"]))
        train=[t for t in all_trades if t["entry_date"]<str(pivot)]
        test=[t for t in all_trades if t["entry_date"]>=str(pivot)]
    else:
        pivot=None;all_trades=[];train=[];test=[]
    sample_ok=len(test)>=30 and len(histories)>=15
    # Even a positive result from one sample is NOT a profitability certification.
    payload={
      "generated_at":datetime.now(TZ).isoformat(),
      "method":"RSI14 crosses above 35, closing price above EMA200. Signal at close. Next session OPEN, ATR14 stop 1.2x / target 3.5x, max hold 14 sessions.",
      "basis":"Unadjusted public daily candles from locally cached IOL BCBA; not independently matched to official settlement, adjustments, bid/ask or corporate actions.",
      "version":"frozen-rsi35-v1",
      "assumptions":{"commission_iva_each_side_pct":round(FEE_SIDE*100,4),
                     "slippage_each_side_pct":round(SLIPPAGE*100,4),
                     "stop_first_when_both_hit":True,"no_same_symbol_overlap":True,
                     "capital_exposure_not_modeled":True,"spread_not_observed":True},
      "history_sources":len(files),"valid_symbols":len(histories),
      "symbols":rows,"rejected":rejected,
      "split_date":str(pivot) if pivot else None,
      "train":metrics(train),"test":metrics(test),
      "sample_ok":sample_ok,
      "status":"EXPLORATORY_NOT_PROVEN",
      "conclusion":"La rentabilidad NO está demostrada. Se requieren más activos, ajustes corporativos, spreads reales, validación fuera de muestra y paper trading forward.",
      "limitations":["Sesgo de selección y supervivencia: universo con históricos disponibles, no toda BYMA",
                     "Series no ajustadas por splits/dividendos/CEDEAR ratio/FX",
                     "No existe reconstrucción histórica del spread ni liquidez",
                     "El stop podría ejecutarse peor que el nivel teórico",
                     "La división temporal sin ajustes posteriores evita un tipo de sesgo, no todos",
                     "Resultados por operación, no rendimiento de cartera diversificada"],
      "test_trades_recent":test[-20:]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print("AUDITORIA_RSI35",json.dumps({"valid":len(histories),"rejected":rejected,
          "split":payload["split_date"],"train":payload["train"],"test":payload["test"],
          "status":payload["status"]},ensure_ascii=False))
if __name__=="__main__":main()
