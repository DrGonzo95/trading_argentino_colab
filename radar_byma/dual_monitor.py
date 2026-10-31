#!/usr/bin/env python3
"""RSI14 forward-only paper ledger + public ARS caucion observer; no actual orders."""
import json,math,re
from datetime import datetime,date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd,requests
from bs4 import BeautifulSoup
from research_advanced import features

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"resultados"/"dual"
OUT.mkdir(parents=True,exist_ok=True)
STATE=ROOT/"radar_byma"/"state"/"paper_ledger.json"
TODAY=datetime.now(ZoneInfo("America/Argentina/Cordoba")).date()
INITIAL_DATE="2026-10-30"
TARIFF={"commission_month":.0015,"rights_90days":.00045,"iva":.21}
TRADING={"commission":.005,"rights":.0005,"slippage":.001,"risk":.005,"concentration":.2,"stopATR":1.2,"targetATR":3.5}
COST=(TRADING["commission"]+TRADING["rights"])*1.21
BUY=1+COST+TRADING["slippage"]
SELL=1-COST-TRADING["slippage"]
SOURCE="https://www.iamc.com.ar/informesmes/"
def base():
    return {"version":1,"started_after":INITIAL_DATE,"last_processed":INITIAL_DATE,
            "paper":{str(c):{"cash":float(c),"positions":{},"pending":{},"trades":[],
                              "rejections":[],"signals":[],"equity":float(c)} for c in (50000,100000)}}
def load():
    if not STATE.exists():return base()
    p=json.loads(STATE.read_text(encoding="utf-8"))
    if p.get("started_after")!=INITIAL_DATE:raise RuntimeError("Inicio del forward test alterado")
    return p
def data():
    datasets={}; errors=[]
    for f in sorted((ROOT/"resultados").glob("*_ohlcv.csv")):
        s=f.name.replace("_ohlcv.csv","")
        if s in ("AL30","GD30","AL35"):continue
        try:
            frame=pd.read_csv(f,parse_dates=["date"])
            if len(frame)<400 or (frame[["open","high","low","close"]]<=0).any().any():raise ValueError("Datos insuficientes o incorrectos")
            datasets[s]=features(frame)
        except Exception as e:errors.append({"ticker":s,"reason":str(e)})
    return datasets,errors
def update_day(p,day,bars,datasets):
    # Orders derived exclusively from previous completed sessions; entry at the next dated opening.
    for sym,pending in list(p["pending"].items()):
        if sym not in bars or pending["day"]>=str(day.date()):continue
        b=bars[sym]; atr=pending["atr"];entry=float(b["open"])*(1+TRADING["slippage"])
        stop=entry-TRADING["stopATR"]*atr
        target=entry+TRADING["targetATR"]*atr
        paid=entry*(1+COST)
        risk=paid-stop*SELL
        reward=target*SELL-paid
        capital=p["cash"]+sum(pos["qty"]*float(bars[k]["open"]) for k,pos in p["positions"].items() if k in bars)
        qty=0
        if stop>0 and risk>0 and reward/risk>=2 and sym not in p["positions"]:
            qty=min(math.floor(capital*TRADING["risk"]/risk),
                    math.floor(capital*TRADING["concentration"]/paid),
                    math.floor(p["cash"]/paid))
        if qty>=1:
            spent=qty*paid
            p["cash"]-=spent
            p["positions"][sym]={"qty":qty,"spent":spent,"entry":entry,"stop":stop,"target":target,"date":str(day.date()),"days":0}
        else:
            p["rejections"].append({"ticker":sym,"date":str(day.date()),"reason":"Stop / costos / tamaño mínimo o R:R insuficiente"})
        del p["pending"][sym]
    for sym,pos in list(p["positions"].items()):
        if sym not in bars:continue
        b=bars[sym];px=None;reason=None
        if b["open"]<=pos["stop"]:px=float(b["open"]);reason="gap_stop"
        elif b["open"]>=pos["target"]:px=float(b["open"]);reason="gap_target"
        elif b["low"]<=pos["stop"]:px=pos["stop"];reason="stop_or_both"
        elif b["high"]>=pos["target"]:px=pos["target"];reason="target"
        elif pos["days"]>=13:px=float(b["close"]);reason="time_exit"
        if px is not None:
            proceeds=pos["qty"]*px*SELL;p["cash"]+=proceeds
            p["trades"].append({"ticker":sym,"entry_date":pos["date"],"exit_date":str(day.date()),"qty":pos["qty"],
                                "entry":round(pos["entry"],2),"exit":round(px,2),"pnl":round(proceeds-pos["spent"],2),"reason":reason})
            del p["positions"][sym]
        else:pos["days"]+=1
    # Daily RSI14 crossing from below 35 in a broad bullish regime.
    for sym,frame in datasets.items():
        if day not in frame.index:continue
        row=frame.loc[day]
        if bool(row["reversion_rsi14"]) and sym not in p["positions"] and sym not in p["pending"]:
            atr=float(row["atr"])
            if math.isfinite(atr) and atr>0:
                signal={"ticker":sym,"day":str(day.date()),"atr":atr,"rsi14":float(row["rsi14"])}
                p["pending"][sym]=signal;p["signals"].append(signal)
    p["equity"]=round(p["cash"]+sum(pos["qty"]*float(bars[s]["close"])*SELL for s,pos in p["positions"].items() if s in bars),2)
def caucion():
    report={"source":SOURCE,"queried":str(TODAY),"state":"NO_VERIFIED_RATE","kind":"public VWAP, NOT executable quote","examples":[]}
    try:
        rsp=requests.get(SOURCE,timeout=18,headers={"User-Agent":"Mozilla/5.0 (educational paper finance monitor)"})
        rsp.raise_for_status()
        page=re.sub(r"\s+"," ",BeautifulSoup(rsp.text,"html.parser").get_text(" ",strip=True))
        dm=re.search(r"Rueda\s+(\d{2})[-/ ]([A-Za-z]{3})[-/ ](\d{2,4})",page,re.I)
        rm=re.search(r"Cauci[oó]n\s+pesos\s*[·:\-]?\s*1\s+d[ií]a\s+h[aá]bil\s+([\d,.]+)\s*%",page,re.I)
        if not dm or not rm:
            report["reason"]="Fecha y TNA de la caucion ARS a un dia no verificables en HTML"
            return report
        months={"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        dd,mm,yy=dm.groups();year=int(yy);year=year+2000 if year<100 else year
        asof=date(year,months[mm.lower()],int(dd))
        rate=float(rm.group(1).replace(",","."))
        report.update(asof=asof.isoformat(),tna=rate)
        if asof>TODAY or (TODAY-asof).days>2 or not 0<=rate<=200:
            report["state"]="STALE_RATE";return report
        settlement=asof+timedelta(days=1)
        while settlement.weekday()>4:settlement+=timedelta(days=1)
        days=(settlement-asof).days
        for cap in (50000,100000):
            gross=cap*rate/100*days/365
            broker=cap*TARIFF["commission_month"]*days/30
            rights=cap*TARIFF["rights_90days"]*days/90
            iva=(broker+rights)*TARIFF["iva"]
            report["examples"].append({"capital":cap,"calendar_days_assumed":days,"gross_ars":round(gross,2),
                                       "broker_ars":round(broker,2),"rights_ars":round(rights,2),
                                       "vat_ars":round(iva,2),"estimated_net_ars":round(gross-broker-rights-iva,2)})
        report["state"]="PUBLIC_REFERENCE_ONLY"
        report["reason"]="IOL illustrative prorated tariff; no broker quote, no holiday calendar or minimum fees confirmed"
        return report
    except Exception as e:
        report["reason"]=type(e).__name__+": "+str(e)[:120]
        return report
def main():
    state=load();datasets,errors=data()
    completed=sorted({dt for frame in datasets.values() for dt in frame.index
                      if str(dt.date())>state["last_processed"] and dt.date()<TODAY})
    for d in completed:
        bars={s:frame.loc[d].to_dict() for s,frame in datasets.items() if d in frame.index}
        for cap in (50000,100000):
            update_day(state["paper"][str(cap)],d,bars,datasets)
        state["last_processed"]=str(d.date())
    report={"mode":"PAPER_ONLY","queried":str(TODAY),"last_closed_bar":state["last_processed"],
            "new_completed_sessions":len(completed),"tickers":sorted(datasets),"excluded":errors,
            "portfolios":{str(c):{"cash":round(state["paper"][str(c)]["cash"],2),
               "equity":state["paper"][str(c)]["equity"],
               "return_pct":round((state["paper"][str(c)]["equity"]/c-1)*100,3),
               "closed_trades":len(state["paper"][str(c)]["trades"]),
               "positions":sorted(state["paper"][str(c)]["positions"]),
               "pending_paper_entries":sorted(state["paper"][str(c)]["pending"])} for c in (50000,100000)},
            "caucion":caucion(),
            "warnings":["Public prices delayed; never submit orders.","No trades backfilled before 2026-10-30.",
                        "Broker rates IOL illustrative and not assumed to be the user's broker."]}
    (OUT/"current.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"ledger_snapshot.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    # State is committed by GitHub Actions only when a genuinely new historical session was consumed.
    if completed:STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
