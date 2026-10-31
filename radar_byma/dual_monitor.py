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
    """Observe publicly reported IOL last traded taker rate, NEVER an executable lender offer."""
    url="https://iol.invertironline.com/mercado/cotizaciones/argentina/cauciones"
    report={"source":url,"queried":str(TODAY),"state":"NO_VERIFIED_RATE",
            "kind":"DELAYED_LAST_TAKER_RATE_NOT_EXECUTABLE","examples":[]}
    try:
        rsp=requests.get(url,timeout=22,headers={"User-Agent":"Mozilla/5.0 (educational paper-trading research)"})
        rsp.raise_for_status()
        soup=BeautifulSoup(rsp.text,"html.parser")
        rates=[]
        for table in soup.select("table"):
            for row in table.select("tr"):
                td=[x.get_text(" ",strip=True) for x in row.select("td")]
                if len(td)<7 or td[1].upper()!="PESOS":continue
                try:
                    days=int(td[0])
                    rate=float(td[5].replace("%","").replace(" ","").replace(",","."))
                    timestamp=datetime.strptime(td[6],"%d/%m/%Y %H:%M:%S")
                    if 1<=days<=30 and .1<=rate<=200 and timestamp.date()<=TODAY:
                        rates.append({"days":days,"rate":rate,"date":timestamp.date(),"time":td[6]})
                except (ValueError,IndexError):continue
        if not rates:
            report["reason"]="No hay tabla pública de tasas legibles y fechadas"
            return report
        latest=max(r["date"] for r in rates)
        report["last_date"]=str(latest)
        if (TODAY-latest).days>2:
            report["state"]="STALE_NO_SIGNAL"
            report["reason"]="La última pizarra pública tiene más de dos días"
            return report
        # One rate for each contractual calendar-day tenor, most recently dated only.
        rates=[r for r in rates if r["date"]==latest]
        selected={}
        for r in rates:
            if r["days"] not in selected or r["time"]>selected[r["days"]]["time"]:
                selected[r["days"]]=r
        for days in sorted(selected)[:12]:
            r=selected[days]
            row={"days_calendar":days,"tna_last_taker_pct":r["rate"],
                 "trade_datetime":r["time"],"example_only":True}
            for cap in (50000,100000):
                gross=cap*(r["rate"]/100)*days/365
                broker=cap*.0015*days/30
                rights=cap*.00045*days/90
                vat=(broker+rights)*.21
                net=gross-broker-rights-vat
                row[f"net_illustrative_{cap}_ars"]=round(net,2)
                row[f"positive_after_estimated_costs_{cap}"]=bool(net>0)
            report["examples"].append(row)
        report["state"]="REFERENCE_RATES_ONLY"
        report["reason"]="Tarifa ilustrativa de IOL; las tasas son tomadoras de última operación, no puntas colocadoras ejecutables. Sin mínimos, IVA efectivo ni costos de otros brokers confirmados."
        return report
    except Exception as e:
        report["reason"]=type(e).__name__+": "+str(e)[:170]
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
