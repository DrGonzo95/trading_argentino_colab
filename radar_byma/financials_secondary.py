#!/usr/bin/env python3
"""Fallback financial table snapshots from publicly viewable issuer financial tables.
SOURCE IS THIRD PARTY, NOT SEC, NOT FILING-DATED. NO point-in-time backtesting.
Scrape only 8 established examples + 4 rotating, no bypass, no auth.
"""
import csv,json,math,re,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
OUT=Path("resultados/fundamentales")
OUT.mkdir(parents=True,exist_ok=True)
PANEL=Path("resultados/discovery/snapshot.json")
FREQ=6
CORE=["AAPL","NVDA","MSFT","AMZN","GOOGL","META"]
ALTERNATE=["TSLA","MELI","AVGO","JPM","XOM","KO","BMA","GGAL"]
HEAD={"User-Agent":"Mozilla/5.0 (educational financial snapshot review; contact github.com/DrGonzo95/trading_argentino_colab)",
      "Accept":"text/html"}
SESSION=requests.Session();SESSION.headers.update(HEAD)
def n(raw):
    s=str(raw).strip().replace("$","").replace(",","").replace(" ","")
    if s in ("","-","—"):return None
    try:
        x=float(s)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None
def choose():
    rot=ALTERNATE[(NOW.toordinal()*2)%len(ALTERNATE):]+ALTERNATE[:(NOW.toordinal()*2)%len(ALTERNATE)]
    return CORE+[r for r in rot if r not in CORE][:4]
def parse(ticker):
    url=f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/"
    resp=SESSION.get(url,timeout=18)
    resp.raise_for_status()
    soup=BeautifulSoup(resp.text,"html.parser")
    # Find explicit scale in visible body, no inference about USD or millions.
    top=" ".join(soup.get_text(" ",strip=True).split())
    if not (re.search(r"(Millions USD|Financials in millions USD|millions USD)",top,re.I)):
        raise ValueError("Moneda/escala USD millones no confirmada")
    tables=soup.select("table")
    chosen=None
    for table in tables:
        text=table.get_text(" ",strip=True).lower()
        if "revenue" in text and "net income" in text and "fiscal year" in text:
            chosen=table
            break
    if chosen is None:raise ValueError("No hay tabla de ingresos/ganancia anual legible")
    tr=chosen.select("tr")
    header=[]
    for row in tr[:3]:
        cells=[c.get_text(" ",strip=True) for c in row.select("th,td")]
        if any(re.search(r"\bFY\s*20\d\d\b",c) for c in cells):
            header=cells;break
    if not header:raise ValueError("No aparecen años fiscales explícitos")
    years=[(i,re.search(r"\bFY\s*(20\d\d)\b",text).group(1))
           for i,text in enumerate(header) if re.search(r"\bFY\s*(20\d\d)\b",text)]
    if len(years)<2:raise ValueError("Menos de dos ejercicios anuales comparables")
    i,year=years[0];j,prevyear=years[1]
    if int(year)-int(prevyear)!=1:raise ValueError("Años fiscales no consecutivos")
    values={}
    for row in tr:
        cells=[c.get_text(" ",strip=True) for c in row.select("th,td")]
        if len(cells)<=max(i,j):continue
        label=" ".join(cells[0].strip().lower().split())
        aliases={
            "revenue":"Revenue",
            "net income":"Net Income",
            "operating income":"Operating Income",
            "gross profit":"Gross Profit"
        }
        selected=None
        for prefix,key in aliases.items():
            if label==prefix or label.startswith(prefix+" "+prefix+" growth"):
                selected=key
                break
        if selected:
            a,b=n(cells[i]),n(cells[j])
            if a is not None and b is not None:
                values[selected]={"current":a,"previous":b}
    if not all(x in values for x in ("Revenue","Net Income")):
        raise ValueError("Faltan Revenue y Net Income con unidades explícitas")
    v=values["Revenue"];p=values["Net Income"]
    if v["current"]<=0 or v["previous"]<=0:raise ValueError("Ventas no positivas")
    growth=round(100*(v["current"]/v["previous"]-1),3)
    margin=round(100*p["current"]/v["current"],3)
    if abs(growth)>1000 or abs(margin)>200:raise ValueError("Datos extremos/tabla posible desalineada")
    return {"ticker":ticker,"fiscal_year":int(year),"previous_fiscal_year":int(prevyear),
            "revenue_usd_millions":v["current"],"prior_revenue_usd_millions":v["previous"],
            "revenue_growth_nominal_pct":growth,
            "net_income_usd_millions":p["current"],"net_profit_margin_pct":margin,
            "operating_income_usd_millions":values.get("Operating Income",{}).get("current"),
            "units":"MILLIONS_USD_FROM_THIRD_PARTY",
            "publication_date":"UNKNOWN_NOT_POINT_IN_TIME",
            "snapshot_at":NOW.isoformat(),
            "source":url,"license_context":"source public summary not a replacement for official filing",
            "usable_for_historical_backtest":False,
            "usable_for_automatic_buy":False}
def main():
    selected=choose()
    rows=[];errors={}
    for ticker in selected:
        try:rows.append(parse(ticker))
        except Exception as e:errors[ticker]=type(e).__name__+": "+str(e)[:125]
        time.sleep(.3)
    if rows:
        with (OUT/"terceros_financieros.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={"fetched_at":NOW.isoformat(),"status":"SECONDARY_SNAPSHOT_ONLY" if rows else "UNAVAILABLE",
       "queried":selected,"verified_table_rows":len(rows),"errors":errors,
       "results":rows,
       "policy":"Never combine a third-party undated table with historic prices as a point-in-time backtest; compare ONLY current issuer ratios, no ARS CEDEAR valuation."}
    (OUT/"terceros_estado.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("THIRD_PARTY_FUNDAMENTALS "+json.dumps({k:v for k,v in summary.items() if k!="results"},ensure_ascii=False))
if __name__=="__main__":main()
