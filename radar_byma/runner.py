#!/usr/bin/env python3
"""Radar BYMA público: backtests exploratorios; ninguna operación real."""
import csv, io, json, math, os, time
from datetime import date
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

TICKERS=["GGAL","YPFD","PAMP","CEPU","BMA","AAPL","GOOGL","NVDA","SPY","AL30","GD30","AL35"]
RISK=.005
MAX_POSITION=.20
FEE=.003
SLIPPAGE=.001
MIN_BARS=400
OUT=Path("resultados")
OUT.mkdir(exist_ok=True)
today=pd.Timestamp.now(tz=ZoneInfo("America/Argentina/Cordoba")).date()
cutoff=pd.Timestamp(os.getenv("FECHA_CORTE",str(today)))
session=requests.Session()
session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; BYMAResearchPaperTrading/1.0; non-commercial)","Accept":"text/html"})
def num(x):
    t=str(x).replace("$","").replace("\xa0","").replace(" ","").strip()
    if "," in t and "." in t: t=t.replace(",","")
    elif "," in t: t=t.replace(",",".")
    return float(t)
def download(ticker):
    url=f"https://iol.invertironline.com/Titulo/DatosHistoricos?mercado=BCBA&simbolo={quote(ticker)}"
    response=session.get(url,timeout=30)
    response.raise_for_status()
    soup=BeautifulSoup(response.text,"html.parser")
    rows=[]
    for table in soup.select("table"):
        header=table.get_text(" ",strip=True).lower()
        if not all(w in header for w in ["apertura","cierre","volumen"]): continue
        for tr in table.select("tr"):
            cells=[x.get_text(" ",strip=True) for x in tr.find_all(["th","td"])]
            if len(cells)<8: continue
            dt=pd.to_datetime(cells[0],format="%m/%d/%Y",errors="coerce")
            if pd.isna(dt): continue
            try:
                o,h,l,c,v=[num(cells[k]) for k in (1,2,3,4,7)]
                rows.append(dict(date=dt,open=o,high=h,low=l,close=c,volume=v))
            except (ValueError,IndexError): pass
    if not rows: raise ValueError("Tabla OHLCV no encontrada en HTML público")
    d=pd.DataFrame(rows)
    d=d.loc[d.date<=cutoff].sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)
    if len(d)==0:raise ValueError("Sin fechas <= corte")
    if (d[["open","high","low","close"]]<=0).any().any() or (d.volume<0).any():raise ValueError("Precios/volumen inválidos")
    bad=(d.high<d[["open","low","close"]].max(axis=1)) | (d.low>d[["open","high","close"]].min(axis=1))
    if bad.any():
        sample=d.loc[bad,["date","open","high","low","close"]].head(3).copy()
        sample["date"]=sample["date"].dt.strftime("%Y-%m-%d")
        raise ValueError(f"OHLC inconsistente: {int(bad.sum())} de {len(d)} velas; ejemplos: {sample.to_dict(orient='records')}")
    if ((d.open/d.close.shift()-1).abs()>.35).any():raise ValueError("Gap >35%, posible split o cambio de ratio")
    if len(d)>1 and d.date.diff().dt.days.max()>21:raise ValueError("Hay brecha >21 días en el histórico")
    return d,url
def calculate(d):
    d=d.copy()
    d["ema50"]=d.close.ewm(span=50,adjust=False,min_periods=50).mean()
    d["ema200"]=d.close.ewm(span=200,adjust=False,min_periods=200).mean()
    delta=d.close.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-delta).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["rsi14"]=100-100/(1+gain/loss)
    macd=d.close.ewm(span=12,adjust=False).mean()-d.close.ewm(span=26,adjust=False).mean()
    macds=macd.ewm(span=9,adjust=False).mean()
    pc=d.close.shift()
    tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
    d["atr14"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d["rvol20"]=d.volume/d.volume.shift().rolling(20).mean()
    prevhigh=d.high.shift().rolling(20).max()
    d["signal"]=((d.close>d.ema50)&(d.ema50>d.ema200)&(d.ema50>d.ema50.shift(10))&
                 (d.close>prevhigh)&(d.rvol20>1.2)&d.rsi14.between(52,75)&
                 (macd>macds)&(d.atr14>0)).fillna(False)
    return d
def backtest(d,initial):
    cash=float(initial)
    position=None
    trade_list=[]
    equity=[]
    for i in range(len(d)):
        bar=d.iloc[i]
        if position is None and i>0 and bool(d.signal.iloc[i-1]):
            atr=float(d.atr14.iloc[i-1])
            entry=float(bar.open)*(1+SLIPPAGE)
            stop=entry-1.5*atr
            target=entry+3.7*atr
            entry_cost=entry*(1+FEE)
            stop_net=stop*(1-FEE-SLIPPAGE)
            target_net=target*(1-FEE-SLIPPAGE)
            risk=entry_cost-stop_net
            reward=target_net-entry_cost
            if stop>0 and risk>0 and reward/risk>=2:
                n=min(math.floor(cash*RISK/risk),math.floor(initial*MAX_POSITION/entry_cost),math.floor(cash/entry_cost))
                if n>0:
                    position=dict(n=n,entry=entry,stop=stop,target=target,cost=n*entry_cost,start=i,dt=str(bar.date.date()))
                    cash-=position["cost"]
        if position:
            p=position
            if bar.open<=p["stop"]: reason,px="gap_stop",float(bar.open)
            elif bar.open>=p["target"]: reason,px="gap_target",float(bar.open)
            elif bar.low<=p["stop"]: reason,px="stop_o_ambos",p["stop"]
            elif bar.high>=p["target"]: reason,px="objetivo",p["target"]
            elif i-p["start"]>=9:reason,px="tiempo_10",float(bar.close)
            elif i==len(d)-1:reason,px="fin_historico",float(bar.close)
            else:reason,px=None,None
            if px is not None:
                income=p["n"]*px*(1-FEE-SLIPPAGE)
                cash+=income
                trade_list.append(dict(entrada=p["dt"],salida=str(bar.date.date()),cantidad=p["n"],motivo=reason,pnl=round(income-p["cost"],2)))
                position=None
        mark=position["n"]*float(bar.close)*(1-FEE-SLIPPAGE) if position else 0
        equity.append(cash+mark)
    peak=pd.Series(equity).cummax()
    return dict(inicial=initial,final=round(cash,2),retorno_pct=round((cash/initial-1)*100,3),
                operaciones=len(trade_list),ganadoras=sum(t["pnl"]>0 for t in trade_list),
                max_drawdown_pct=round(((pd.Series(equity)/peak)-1).min()*100,3)),trade_list
def write(name,rows):
    with open(OUT/name,"w",encoding="utf-8",newline="") as f:
        if not rows:return
        fields=list(dict.fromkeys(key for row in rows for key in row.keys()))
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)
states=[];backtests=[];trades=[];candidates=[]
for ticker in TICKERS:
    record={"simbolo":ticker,"fecha_ejecucion":str(today)}
    try:
        d,url=download(ticker)
        record.update(fuente=url,velas=len(d),primera=str(d.date.iloc[0].date()),ultima=str(d.date.iloc[-1].date()))
        if len(d)<MIN_BARS:
            record["estado"]="RECHAZADO_MENOS_400"
        elif ticker in ["AL30","GD30","AL35"]:
            record["estado"]="EXCLUIDO_DE_PNL: faltan cupones/amortizaciones"
        else:
            x=calculate(d)
            d.to_csv(OUT/f"{ticker}_ohlcv.csv",index=False)
            last=x.iloc[-1]
            record.update(estado="SIN_SENAL",ema50=round(last.ema50,2),ema200=round(last.ema200,2),rsi14=round(last.rsi14,2))
            if bool(last.signal):
                record["estado"]="CANDIDATO_SOLO_PAPEL"
                candidates.append(dict(simbolo=ticker,fecha=str(last.date.date()),cierre_historico=last.close,
                    advertencia="NO es precio ejecutable ni orden; validar puntas y costes con broker"))
            cut=int(len(x)*.70)
            for capital in [100000,50000]:
                # Indicadores calculados sobre el histórico anterior, sin datos del futuro.
                for period,segment in [("entrenamiento",x.iloc[:cut]),("prueba",x.iloc[cut:])]:
                    summary,tt=backtest(segment.reset_index(drop=True),capital)
                    backtests.append(dict(simbolo=ticker,periodo=period,capital=capital,
                        desde=str(segment.date.iloc[0].date()),hasta=str(segment.date.iloc[-1].date()),**summary))
                    trades.extend(dict(simbolo=ticker,periodo=period,capital=capital,**t) for t in tt)
    except Exception as exc:
        record.update(estado="ERROR_DATOS",detalle=str(exc)[:220])
    states.append(record)
    time.sleep(1.5)
write("estado.csv",states)
write("backtests.csv",backtests)
write("trades.csv",trades)
write("candidatos_solo_papel.csv",candidates)
print(json.dumps({"fecha":str(today),"estados":states,"backtests":backtests,"candidatos":candidates},ensure_ascii=False,indent=2,default=str))
