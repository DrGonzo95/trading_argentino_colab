#!/usr/bin/env python3
"""Enlarge PULSO daily-chart coverage from public IOL historical OHLCV, without fake bars.
Reuses prior Git-committed chart records when recent; never treats chart-only assets as signal-ready.
The 400-bar requirement for actual technical setups is enforced separately in rank_byma.
"""
import concurrent.futures as fut
import json,math,os,re,subprocess
from pathlib import Path
from datetime import datetime,date
from urllib.parse import quote
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
TODAY=NOW.date()
OUT=Path("docs/data/charts.json")
ROOT="https://iol.invertironline.com/Titulo/DatosHistoricos?mercado=BCBA&simbolo="
PRIORITY=["GGAL","YPFD","PAMP","ALUA","BYMA","EDN","COME","CRES","LOMA","TGNO4","TXAR",
          "MIRG","HARG","IRSA","TECO2","SUPV","AAPL","NVDA","SPY","QQQ","MSFT","AMZN",
          "GOOGL","META","MELI","TSLA","JPM","KO","XOM","YPF","ECOG","GLOB"]
def parsefloat(s):
    s=str(s).replace("\xa0","").replace("$","").replace(" ","").strip()
    if not s or s in ("—","-"):return None
    if "," in s:s=s.replace(",","")
    try:return float(s)
    except ValueError:return None
def bars_valid(bars):
    if not isinstance(bars,list) or len(bars)<60:return False
    last=""
    for b in bars:
        if len(b)!=6 or str(b[0])<=last or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in b[1:]):
            return False
        last=b[0]
        if b[1]<=0 or b[3]<=0 or b[2]<max(b[1],b[3],b[4]) or b[3]>min(b[1],b[2],b[4]) or b[5]<0:
            return False
    return True
def previous():
    try:
        # HEAD contains the last committed chart feed, not the freshly overwritten export.
        p=subprocess.run(["git","show","HEAD:docs/data/charts.json"],capture_output=True,text=True,timeout=8)
        if p.returncode==0:return json.loads(p.stdout).get("symbols",{})
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return {}
def fetch(symbol):
    url=ROOT+quote(symbol)
    try:
        response=requests.get(url,timeout=23,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
        response.raise_for_status()
        soup=BeautifulSoup(response.text,"html.parser")
        rows=[]
        for table in soup.select("table"):
            head=table.get_text(" ",strip=True).lower()
            if not all(z in head for z in ("apertura","cierre","volumen")):continue
            for tr in table.select("tr"):
                cells=[x.get_text(" ",strip=True) for x in tr.find_all(["td","th"])]
                if len(cells)<8:continue
                try:
                    dt=datetime.strptime(cells[0],"%m/%d/%Y").date()
                    if dt>TODAY:continue
                    o,h,l,c,v=(parsefloat(cells[i]) for i in (1,2,3,4,7))
                    if any(x is None for x in (o,h,l,c,v)):continue
                    rows.append([dt.isoformat(),o,h,l,c,int(v)])
                except (ValueError,TypeError,OverflowError):continue
        rows=sorted({r[0]:r for r in rows}.values(),key=lambda r:r[0])
        if len(rows)<80:return symbol,None,"menos de 80 cierres públicos"
        # Prefer the last 260 sessions; price jumps / corrections are rejection flags.
        rows=rows[-260:]
        bad=sum(not(r[2]>=max(r[1],r[3],r[4]) and r[3]<=min(r[1],r[2],r[4])) for r in rows)
        if bad:return symbol,None,"OHLC inconsistente: "+str(bad)+" ruedas"
        for a,b in zip(rows,rows[1:]):
            if abs(b[4]/a[4]-1)>.35:return symbol,None,"salto >35%: posible evento corporativo"
            gap=(date.fromisoformat(b[0])-date.fromisoformat(a[0])).days
            if gap>21:return symbol,None,"hueco >21 días"
        if (TODAY-date.fromisoformat(rows[-1][0])).days>10:return symbol,None,"serie histórica antigua"
        if not bars_valid(rows):return symbol,None,"históricos inválidos"
        return symbol,{"source":"IOL public historical daily BCBA (no corporate-action adjustments)",
                      "source_url":url,"last_candle":rows[-1][0],"timeframe":"1D",
                      "chart_only":True,"bars":rows},None
    except Exception as e:return symbol,None,type(e).__name__+": "+str(e)[:120]
def main():
    feed=json.loads(OUT.read_text(encoding="utf-8"))
    current=feed["symbols"]
    old=previous()
    # Preserve previously retrieved history only when its last candle is recent.
    for sym,r in old.items():
        if sym not in current and bars_valid(r.get("bars")):
            age=(TODAY-date.fromisoformat(r["bars"][-1][0])).days
            if age<=10:current[sym]=r
    market=json.loads(Path("docs/data/market.json").read_text(encoding="utf-8"))
    eligible={r["symbol"] for r in market.get("assets",[]) if r.get("kind") in ("accion","cedear")}
    missing=[sym for sym in PRIORITY if sym in eligible and sym not in current]
    max_extra=int(os.getenv("MAX_EXTRA_CHART_REQUESTS","26"))
    missing=missing[:max_extra]
    errors={}
    workers=4
    with fut.ThreadPoolExecutor(max_workers=workers) as ex:
        for sym,rec,err in ex.map(fetch,missing):
            if rec:current[sym]=rec
            else:errors[sym]=err
    feed["symbols"]=dict(sorted(current.items()))
    feed["expanded_at"]=NOW.isoformat()
    feed["chart_sources_note"]="Históricos públicos NO ajustados. Algunas especies no tienen series aptas y se excluyen; las velas NO son señales de compra."
    feed["coverage"]={"charted":len(current),"attempted_missing":len(missing),
                      "added":len(missing)-len(errors),"errors":errors}
    OUT.write_text(json.dumps(feed,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    print("HISTORICOS_AMPLIADOS",json.dumps(feed["coverage"],ensure_ascii=False))
if __name__=="__main__":main()
