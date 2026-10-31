#!/usr/bin/env python3
"""Public IOL panel discovery for the ARS BYMA radar.
Does NOT imply real time. Quotes are provider-delayed and lack guaranteed timestamp.
Historical downloads are bounded; bonds/ON remain snapshot-only unless verified
cashflow/settlement metadata are available.
"""
import ast,csv,json,re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BASE="https://iol.invertironline.com"
PANELS={
 "acciones_lideres":BASE+"/Mercado/Cotizaciones",
 "acciones_general":BASE+"/mercado/cotizaciones/argentina/acciones/panel-general",
 "cedears":BASE+"/mercado/cotizaciones/argentina/cedears/todos",
 "bonos":BASE+"/mercado/cotizaciones/argentina/bonos",
 "obligaciones_negociables":BASE+"/mercado/cotizaciones/argentina/obligaciones-negociables",
}
GROUP={"acciones_lideres":"accion","acciones_general":"accion","cedears":"cedear","bonos":"bono","obligaciones_negociables":"on"}
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
OUT=Path("resultados/discovery")
OUT.mkdir(parents=True,exist_ok=True)
TICKER=re.compile(r"^[A-Z][A-Z0-9.]{0,11}$")
MIN_TURNOVER=5_000_000.0  # indicative ARS turnover; screen only, not full liquidity quality.
def parse_num(x):
    x=str(x).strip().replace("\u00a0","").replace("$","").replace("%","").replace(" ","")
    if x in ("-","", "—"):return None
    if "." in x and "," in x:x=x.replace(".","").replace(",",".")
    elif "," in x:x=x.replace(",",".")
    try:return float(x)
    except ValueError:return None
def core_symbols():
    # Parse the base ticker literal without executing runner.py.
    src=ast.parse(Path("radar_byma/runner.py").read_text(encoding="utf-8"))
    for node in src.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="TICKERS" for t in node.targets):
            return list(ast.literal_eval(node.value))
    return []
def analyze(page,kind):
    soup=BeautifulSoup(page,"html.parser")
    title=soup.title.get_text(" ",strip=True).lower() if soup.title else ""
    heading=" ".join(h.get_text(" ",strip=True).lower() for h in soup.select("h1"))
    required={"accion":"acciones","cedear":"cedear","bono":"bonos","on":"obligaciones"}
    if required[kind] not in heading+" "+title:
        raise ValueError(f"La página no es panel de {kind}: {heading[:90]}")
    best=[]
    for table in soup.select("table"):
        head=table.get_text(" ",strip=True).lower()
        if "símbolo" not in head and "simbolo" not in head:continue
        if "monto" not in head and "operado" not in head:continue
        rows=[]
        for tr in table.select("tr"):
            td=tr.find_all("td")
            if len(td)<10:continue
            first=td[0].get_text(" ",strip=True)
            match=re.match(r"^([A-Z0-9.]{1,12})(?:\s|$)",first)
            if not match:continue
            sym=match.group(1)
            if not TICKER.fullmatch(sym):continue
            price=parse_num(td[1].get_text(" ",strip=True))
            # Stock/CEDEAR have 12 columns, bonds/ON have 13.
            amount_index=11 if kind in ("accion","cedear") else 10
            if len(td)<=amount_index:continue
            turnover=parse_num(td[amount_index].get_text(" ",strip=True))
            if price is None or price<=0:continue
            rows.append({"symbol":sym,"class":kind,"last_delayed":price,
                         "variation_pct":parse_num(td[2].get_text(" ",strip=True)),
                         "turnover_indicative":turnover or 0.0,
                         "provider":"IOL public delayed panel",
                         "scraped_at":NOW.isoformat(),
                         "quote_time":"unknown; panel typically delayed by >=20 min",
                         "currency":"UNVERIFIED: do not infer solely from suffix"})
        if len(rows)>len(best):best=rows
    if not best:raise ValueError("Panel sin tabla de precios legible")
    return best
def main():
    ses=requests.Session()
    ses.headers.update({"User-Agent":"Mozilla/5.0 (compatible; BYMAPaperResearch/1.0)","Accept":"text/html"})
    panels={};errors={};allrows={}
    for panel,url in PANELS.items():
        try:
            response=ses.get(url,timeout=28)
            response.raise_for_status()
            rows=analyze(response.text,GROUP[panel])
            panels[panel]={"count":len(rows),"url":url,"state":"verified_html_table"}
            for r in rows:
                key=(r["class"],r["symbol"])
                if key not in allrows or r["turnover_indicative"]>allrows[key]["turnover_indicative"]:
                    allrows[key]=r
        except Exception as exc:
            panels[panel]={"count":0,"url":url,"state":"unavailable"}
            errors[panel]=str(exc)[:240]
    rows=sorted(allrows.values(),key=lambda x:(x["class"],-x["turnover_indicative"],x["symbol"]))
    by={g:[r for r in rows if r["class"]==g] for g in ("accion","cedear","bono","on")}
    for g in ("accion","cedear"):
        symbols={r["symbol"] for r in by[g]}
        for row in by[g]:
            sym=row["symbol"]
            # USD/C duplicate only when the peso-base symbol appears in the same panel;
            # NEVER blindly strip the suffix of e.g. AMD, MCD, or BRKB.
            row["possible_fx_variant"]=sym.endswith(("D","C")) and sym[:-1] in symbols
    old=set(core_symbols())
    candidates=[]
    selected_by={}
    for group,limit in (("accion",16),("cedear",20)):
        usable=[r for r in by[group] if r["symbol"] not in old
                and not r.get("possible_fx_variant") and r["last_delayed"]>=100
                and r["turnover_indicative"]>=MIN_TURNOVER]
        # Deterministic round-robin across days, after sorting by turnover.
        usable.sort(key=lambda r:(-r["turnover_indicative"],r["symbol"]))
        pool=usable[:min(110,len(usable))]
        selected=[]
        if pool:
            start=(NOW.timetuple().tm_yday*limit)%len(pool)
            for off in range(len(pool)):
                row=pool[(start+off)%len(pool)]
                if row["symbol"] not in selected:
                    selected.append(row["symbol"])
                if len(selected)>=limit:break
        selected_by[group]=selected
        candidates+=selected
    # Capture the broad snapshot without inventing signals from delayed prices.
    payload={"scanned_at":NOW.isoformat(),"source":"IOL quote panels; delayed",
             "panels":panels,"errors":errors,
             "snapshot_counts":{g:len(by[g]) for g in by},
             "quote_rows_total":len(rows),
             "historical_extra_symbols":candidates,
             "historical_extra_by_type":selected_by,
             "history_policy":"bounded 36 rotating liquid-looking ARS candidates; price/turnover only indicative; OHLCV validation required",
             "not_live":True,"snapshot":rows}
    (OUT/"snapshot.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"history_candidates.json").write_text(json.dumps({"tickers":candidates,"groups":selected_by,"scanned_at":NOW.isoformat()},ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"all_listed_quotes.csv").open("w",encoding="utf-8",newline="") as f:
        if rows:
            cols=list(dict.fromkeys(k for r in rows for k in r))
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
    print("BYMA_DISCOVERY "+json.dumps({k:v for k,v in payload.items() if k!="snapshot"},ensure_ascii=False))
if __name__=="__main__": main()
