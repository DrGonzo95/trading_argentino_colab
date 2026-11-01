#!/usr/bin/env python3
"""Independent close comparison: IOL cached OHLC vs public Gio Bursatil Argentine leader table.
No API keys, no scraped intraday execution claims. Graceful failure when source is unavailable.
A match is only a same-date/same-species EOD consistency check, NOT proof of execution price.
"""
import json, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
URL="https://giobursatil.com.ar/cotizaciones/"
OUT=Path("docs/data/quote_check.json")
CHARTS=Path("docs/data/charts.json")
def number(raw):
    s=str(raw).replace("\xa0","").replace("$","").replace("%","").replace(" ","").strip()
    if not s or s in ("—","-"):return None
    if "," in s: s=s.replace(".","").replace(",",".")
    else:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+",s):s=s.replace(".","")
    try:return float(s)
    except (ValueError,TypeError):return None
def get_gio():
    r=requests.get(URL,timeout=20,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    title=soup.get_text(" ",strip=True)
    dates=re.findall(r"(\d{2}/\d{2}/\d{4})",title[:1500])
    # Select table with leader column header, not some unrelated CEDEAR currency variant.
    for table in soup.select("table"):
        head=" ".join(th.get_text(" ",strip=True).lower() for th in table.find_all("th"))
        if not any(w in head for w in ("símbolo","simbolo")):continue
        if "último" not in head and "ultimo" not in head and "precio" not in head:continue
        rows={}
        for tr in table.select("tr"):
            cells=[c.get_text(" ",strip=True) for c in tr.find_all(["td"])]
            if len(cells)<2:continue
            symbol=cells[0].split()[0].upper().strip()
            if not re.fullmatch("[A-Z][A-Z0-9]{1,10}",symbol):continue
            value=number(cells[1])
            if value and value>0:rows[symbol]=value
        if len(rows)>=8:
            return rows, (datetime.strptime(dates[0],"%d/%m/%Y").date().isoformat() if dates else None)
    raise ValueError("La tabla de cotizaciones líderes no está disponible en el HTML.")
def main():
    feed=json.loads(CHARTS.read_text(encoding="utf-8"))
    results={}
    payload={"generated_at":NOW.isoformat(),"source_name":"Gio Bursatil (independiente de IOL)",
        "source_url":URL,"method":"Comparación de cierre por símbolo y fecha de mercado, NO precio ejecutable",
        "state":"UNAVAILABLE","asof":None,"checked":0,"matched":0,"discrepancies":0,
        "prices":{},"error":None}
    try:
        gio,asof=get_gio()
        if not asof:raise ValueError("Fecha de sesión de Gio no verificable; se omite comparación.")
        payload["asof"]=asof
        for sym,rec in feed.get("symbols",{}).items():
            bars=rec.get("bars",[])
            if sym not in gio or not bars:continue
            last=bars[-1]
            if last[0]!=asof:continue
            iol=float(last[4]);other=float(gio[sym])
            if iol<=0:continue
            diff=round(100*abs(other-iol)/iol,4)
            status="MATCH" if diff<=.5 else "DIVERGENCE"
            results[sym]={"historical_close":iol,"independent_close":other,
                "market_date":asof,"difference_pct":diff,"status":status,
                "historical_provider":rec.get("source","IOL"),"independent_provider":"Gio Bursatil"}
        payload["prices"]=results
        payload["checked"]=len(results)
        payload["matched"]=sum(x["status"]=="MATCH" for x in results.values())
        payload["discrepancies"]=sum(x["status"]=="DIVERGENCE" for x in results.values())
        payload["state"]="PARTIAL_INDEPENDENT_EOD" if results else "NO_SAME_DATE_OVERLAP"
    except Exception as exc:
        payload["error"]=type(exc).__name__+": "+str(exc)[:240]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print("SECOND_SOURCE_EOD",json.dumps({k:v for k,v in payload.items() if k!="prices"},ensure_ascii=False))
if __name__=="__main__":main()
