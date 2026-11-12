#!/usr/bin/env python3
"""CEDEAR research: analyze the *original* US-listed security, never its ARS
certificate as a substitute. Public data only, research-only output.

All market results are descriptive; no paper fill, order, calibrated win-rate
or local price conversion is produced by this module.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import time
import unicodedata
import zipfile
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "resultados/discovery/snapshot.json"
REPORT = ROOT / "docs/data/underlying_radar.json"
MARKDOWN = ROOT / "CEDEARS_SUBYACENTES_EN_VIGILANCIA.md"
CACHE = ROOT / "radar_byma/cache/origin"
MAP_URL = "https://criteria.com.ar/ratios-de-conversion-elementor/"
MAX_BATCH = max(1, min(45, int(os.getenv("ORIGIN_BATCH_SIZE", "24"))))
TIMEZONE = ZoneInfo("America/Argentina/Cordoba")
NY_TZ = ZoneInfo("America/New_York")
US_EXCHANGES = ("NASDAQ", "NEW YORK", "NYSE", "NYSEAMERICAN", "NYSE ARCA", "NYSEARCA", "NYSE MKT")
# Curated seed: only a research fallback if the live symbol/ISIN table fails.
# Never use this fallback for CEDEAR conversion ratios or trade authorization.
SEEDS = {
    "AAPL":"AAPL", "MSFT":"MSFT", "NVDA":"NVDA", "AMZN":"AMZN", "GOOGL":"GOOGL",
    "GOOG":"GOOG", "META":"META", "TSLA":"TSLA", "AMD":"AMD", "AVGO":"AVGO",
    "AMAT":"AMAT", "MRNA":"MRNA", "ADBE":"ADBE", "CRM":"CRM", "GLOB":"GLOB",
    "PFE":"PFE", "MELI":"MELI", "MSTR":"MSTR", "JPM":"JPM", "KO":"KO",
    "AAL":"AAL", "ABNB":"ABNB", "ABBV":"ABBV", "ACN":"ACN", "AXP":"AXP",
    "AMGN":"AMGN", "BA":"BA", "BAC":"BAC", "C":"C", "CAT":"CAT",
    "COIN":"COIN", "COST":"COST", "CVX":"CVX", "DIS":"DIS", "F":"F",
    "GE":"GE", "GILD":"GILD", "HD":"HD", "IBM":"IBM", "INTC":"INTC",
    "LLY":"LLY", "MA":"MA", "MCD":"MCD", "MU":"MU", "NFLX":"NFLX",
    "NIO":"NIO", "NU":"NU", "ORCL":"ORCL", "PBR":"PBR", "PLTR":"PLTR",
    "QCOM":"QCOM", "RIO":"RIO", "SHOP":"SHOP", "SNOW":"SNOW", "SPOT":"SPOT",
    "T":"T", "TGT":"TGT", "TSM":"TSM", "UBER":"UBER", "UNH":"UNH",
    "V":"V", "VALE":"VALE", "WMT":"WMT", "XOM":"XOM", "YPF":"YPF",
    "BRKB":"BRK-B", "ADGO":"AGRO", "SPY":"SPY", "QQQ":"QQQ",
}
PINNED = ("AMAT", "MRNA", "AMD", "AVGO", "NVDA", "GLOB", "PFE")

def norm(text):
    return "".join(c for c in unicodedata.normalize("NFKD", str(text).lower()) if not unicodedata.combining(c))

def safe_symbol(value):
    value = str(value).strip().upper().replace("/", "-")
    return value if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", value) else None

def parse_reference(html):
    """Use explicit source ticker columns; never infer original ticker from BYMA."""
    soup = BeautifulSoup(html, "html.parser")
    mapping = {}
    for table in soup.select("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        head = [norm(x.get_text(" ", strip=True)) for x in rows[0].find_all(["th", "td"])]
        try:
            byma_i = next(i for i,h in enumerate(head) if "id de mercado" in h)
            origin_i = next(i for i,h in enumerate(head) if "ticker en mercado de origen" in h)
            exchange_i = next(i for i,h in enumerate(head) if "mercado de valor subyacente" in h)
        except StopIteration:
            continue
        ratio_i = next((i for i,h in enumerate(head) if "ratio cedear" in h), None)
        isin_i = next((i for i,h in enumerate(head) if "isin valor subyacente" in h), None)
        for tr in rows[1:]:
            vals = [x.get_text(" ", strip=True) for x in tr.find_all(["th", "td"])]
            if len(vals) <= max(byma_i, origin_i, exchange_i):
                continue
            byma = safe_symbol(vals[byma_i])
            origin = safe_symbol(vals[origin_i])
            exchange = vals[exchange_i].upper().strip()
            if not byma or not origin or not any(x in exchange for x in US_EXCHANGES):
                continue
            # Exclude OTC/GDRs: exchange/quote treatment needs separate controls.
            if "OTC" in exchange or "GDR" in exchange:
                continue
            ratio = vals[ratio_i] if ratio_i is not None and ratio_i < len(vals) else None
            isin = vals[isin_i][:12] if isin_i is not None and isin_i < len(vals) else None
            mapping[byma] = {"ticker": origin, "exchange_reference":exchange,
                             "ratio_reference":ratio, "isin_underlying":isin,
                             "mapping_source":MAP_URL, "mapping_verified":True}
    return mapping


CAJA_URL = "https://cajadevalores.com.ar/Servicios/Cedears"
CAJA_XLSX = "https://cajadevalores.com.ar/pdf/CEDEARS.xlsx"
ATLAS_URL = "https://www.atlas-stocks.com/es/cedears"

def parse_caja_reference(html):
    """Official Caja de Valores list: exact BYMA and origin symbols plus ISIN."""
    soup=BeautifulSoup(html,"html.parser")
    mapping={}
    for table in soup.select("table"):
        rows=table.find_all("tr")
        if not rows:
            continue
        header_idx=None
        for idx,tr in enumerate(rows[:5]):
            heads=[norm(x.get_text(" ",strip=True)) for x in tr.find_all(["th","td"])]
            try:
                a=next(i for i,h in enumerate(heads) if "simbolo byma" in h)
                b=next(i for i,h in enumerate(heads) if "ticker en mercado" in h)
                ex=next(i for i,h in enumerate(heads) if "mercado de origen" in h)
            except StopIteration:
                continue
            header_idx=idx
            ratio_i=next((i for i,h in enumerate(heads) if "ratio" in h),None)
            isin_i=next((i for i,h in enumerate(heads) if "isin accion" in h or "isin etf" in h),None)
            break
        if header_idx is None:
            continue
        for tr in rows[header_idx+1:]:
            vals=[x.get_text(" ",strip=True) for x in tr.find_all(["td","th"])]
            if len(vals)<=max(a,b,ex):
                continue
            byma=safe_symbol(vals[a])
            ticker=safe_symbol(vals[b])
            exchange=vals[ex].upper().strip()
            if not byma or not ticker or not any(x in exchange for x in US_EXCHANGES):
                continue
            if "OTC" in exchange or "GDR" in exchange:
                continue
            mapping[byma]={"ticker":ticker,"exchange_reference":exchange,
                "ratio_reference":vals[ratio_i] if ratio_i is not None and ratio_i<len(vals) else None,
                "isin_underlying":vals[isin_i] if isin_i is not None and isin_i<len(vals) else None,
                "mapping_source":CAJA_URL,"mapping_verified":True}
    return mapping

def parse_caja_xlsx(data):
    """Read the official XLSX as zipped XML, no third-party workbook dependency.

    Scans all worksheet tabs and only trusts clearly labelled original-ticker
    and BYMA-symbol columns. Cells with unknown coordinates are skipped.
    """
    if len(data)>8_000_000 or data[:2]!=b"PK":
        raise ValueError("NO_ES_XLSX_O_TAMANO_EXCESIVO")
    shared=[]
    namespace="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as xlsx:
        names=xlsx.namelist()
        if "xl/sharedStrings.xml" in names:
            root=ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
            for si in root.findall(namespace+"si"):
                shared.append("".join((el.text or "") for el in si.iter(namespace+"t")))
        mapping={}
        for filename in names:
            if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml",filename):
                continue
            sheet=ET.fromstring(xlsx.read(filename))
            rows=[]
            for row in sheet.iter(namespace+"row"):
                cells={}
                for cell in row.findall(namespace+"c"):
                    letter=re.match(r"^[A-Z]+",cell.get("r",""))
                    if not letter:
                        continue
                    col=0
                    for ch in letter.group(0):
                        col=col*26+(ord(ch)-64)
                    col-=1
                    v=cell.find(namespace+"v")
                    if cell.get("t")=="s" and v is not None:
                        try: value=shared[int(v.text)]
                        except (ValueError,IndexError,TypeError):continue
                    elif cell.get("t")=="inlineStr":
                        value="".join((x.text or "") for x in cell.iter(namespace+"t"))
                    else:
                        value=v.text if v is not None else ""
                    cells[col]=str(value).strip()
                if cells:
                    rows.append(cells)
            for idx,header in enumerate(rows[:35]):
                heads={i:" ".join(norm(v).split()) for i,v in header.items()}
                try:
                    byma_i=next(i for i,v in heads.items() if "simbolo byma" in v)
                    origin_i=next(i for i,v in heads.items() if "ticker en mercado" in v)
                    exchange_i=next(i for i,v in heads.items() if "mercado de origen" in v)
                except StopIteration:
                    continue
                ratio_i=next((i for i,v in heads.items() if "ratio" in v),None)
                isin_i=next((i for i,v in heads.items() if "isin accion" in v or "isin etf" in v),None)
                for cells in rows[idx+1:]:
                    byma=safe_symbol(cells.get(byma_i,""))
                    ticker=safe_symbol(cells.get(origin_i,""))
                    exchange=cells.get(exchange_i,"").upper()
                    if not byma or not ticker or not any(t in exchange for t in US_EXCHANGES):
                        continue
                    if "OTC" in exchange or "GDR" in exchange:
                        continue
                    mapping[byma]={"ticker":ticker,"exchange_reference":exchange,
                        "ratio_reference":cells.get(ratio_i) if ratio_i is not None else None,
                        "isin_underlying":cells.get(isin_i) if isin_i is not None else None,
                        "mapping_source":CAJA_XLSX,"mapping_verified":True}
                break
    return mapping

def parse_atlas_reference(html):
    """Secondary mapping for *research only*, not official ratios/trading.

    Only accept an explicit pair of local CEDEAR and underlying ticker with
    US listing. The mapping is never enough to authorize a paper entry.
    """
    soup=BeautifulSoup(html,"html.parser")
    mapping={}
    for table in soup.select("table"):
        rows=table.find_all("tr")
        if not rows:
            continue
        head=[" ".join(norm(x.get_text(" ",strip=True)).split())
              for x in rows[0].find_all(["th","td"])]
        try:
            byma_i=next(i for i,h in enumerate(head) if h=="cedear")
            company_i=next(i for i,h in enumerate(head) if "empresa o fondo" in h)
        except StopIteration:
            continue
        for tr in rows[1:]:
            cells=tr.find_all(["th","td"])
            if len(cells)<=max(byma_i,company_i):
                continue
            byma=safe_symbol(cells[byma_i].get_text(" ",strip=True))
            company=cells[company_i].get_text(" ",strip=True)
            mt=re.search(r"(?<![A-Z0-9])([A-Z][A-Z0-9./-]{0,13})\s*[·•]\s*(NASDAQ|NYSE|NEW YORK)(?:\s+(GS|GM|ARCA|AMERICAN))?\b",
                         company,flags=re.IGNORECASE)
            if not byma or not mt:
                continue
            ticker=safe_symbol(mt.group(1))
            if not ticker:
                continue
            # Explicit known exception for BYMA symbol != US ticker.
            if byma in SEEDS and SEEDS[byma]!=ticker:
                ticker=SEEDS[byma]
            mapping[byma]={"ticker":ticker,
                "exchange_reference":(mt.group(2)+" "+(mt.group(3) or "")).upper().strip(),
                "ratio_reference":None,"isin_underlying":None,
                "mapping_source":ATLAS_URL+" (TERCERO_SOLO_INVESTIGACION)",
                "mapping_verified":False}
    return mapping

def reference(session):
    mapping={}
    notes=[]
    try:
        r=session.get(CAJA_XLSX,timeout=23)
        r.raise_for_status()
        xmap=parse_caja_xlsx(r.content)
        mapping.update(xmap)
        notes.append(f"CAJA_XLSX_OFICIAL_{len(xmap)}")
    except (requests.RequestException,ValueError,zipfile.BadZipFile,ET.ParseError) as exc:
        notes.append("CAJA_XLSX_NO_DISPONIBLE: "+str(exc)[:90])
    try:
        r=session.get(CAJA_URL,timeout=22)
        r.raise_for_status()
        hmap=parse_caja_reference(r.text)
        for ticker,details in hmap.items():
            mapping.setdefault(ticker,details)
        notes.append(f"CAJA_HTML_{len(hmap)}")
    except (requests.RequestException,ValueError) as exc:
        notes.append("CAJA_HTML_NO_ACCESIBLE: "+str(exc)[:90])
    try:
        r=session.get(MAP_URL,timeout=22)
        r.raise_for_status()
        cmap=parse_reference(r.text)
        for ticker,details in cmap.items():
            mapping.setdefault(ticker,details)
        notes.append(f"CRITERIA_{len(cmap)}")
    except (requests.RequestException,ValueError) as exc:
        notes.append("CRITERIA_NO_ACCESIBLE: "+str(exc)[:90])
    try:
        r=session.get(ATLAS_URL,timeout=22)
        r.raise_for_status()
        amap=parse_atlas_reference(r.text)
        for ticker,details in amap.items():
            mapping.setdefault(ticker,details)
        notes.append(f"ATLAS_TERCIARIO_SOLO_ESTUDIO_{len(amap)}")
    except (requests.RequestException,ValueError) as exc:
        notes.append("ATLAS_NO_ACCESIBLE: "+str(exc)[:90])
    return mapping,"; ".join(notes)

def discover():
    if not SNAPSHOT.exists():
        return set(), "PANEL_IOL_INDISPONIBLE"
    try:
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        rows = data.get("snapshot", [])
        if data.get("errors") or not rows:
            return set(), "PANEL_IOL_PARCIAL_O_VACIO"
        return {str(x.get("symbol", "")).upper() for x in rows if x.get("class") == "cedear"}, "PANEL_IOL_CONSULTADO"
    except (OSError, ValueError, TypeError):
        return set(), "PANEL_IOL_INVALIDO"

def get_hist(session, ticker):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + requests.utils.quote(ticker, safe="-")
    params = {"range":"2y", "interval":"1d", "events":"div,splits"}
    r = session.get(url, params=params, timeout=22)
    r.raise_for_status()
    obj = r.json()
    entry = (obj.get("chart", {}).get("result") or [None])[0]
    if not entry:
        raise ValueError("SIN_RESULTADO_YAHOO")
    meta = entry.get("meta", {})
    symbol = safe_symbol(meta.get("symbol", ""))
    currency = str(meta.get("currency") or "").upper()
    exchange = str(meta.get("exchangeName") or "").upper()
    if symbol != ticker.upper() or currency != "USD":
        raise ValueError(f"ESPECIE_NO_COINCIDE: {symbol}/{currency}")
    if exchange not in ("NMS","NYQ","NGM","NCM","ASE","PCX","BTS","NASDAQ","NYSE"):
        raise ValueError(f"BOLSA_ORIGEN_NO_CONFIRMADA: {exchange}")
    quote = ((entry.get("indicators") or {}).get("quote") or [{}])[0]
    stamps = entry.get("timestamp") or []
    out = {}
    for i, stamp in enumerate(stamps):
        try:
            day = datetime.fromtimestamp(int(stamp), NY_TZ).date().isoformat()
            bar = {k: quote[k][i] for k in ("open","high","low","close","volume")}
            if any(v is None or not math.isfinite(float(v)) for v in bar.values()):
                continue
            o,h,l,c,v = (float(bar[k]) for k in ("open","high","low","close","volume"))
            if o<=0 or l<=0 or c<=0 or v<0 or h<max(o,l,c) or l>min(o,h,c):
                continue
            out[day] = {"date":day,"open":o,"high":h,"low":l,"close":c,"volume":v}
        except (IndexError, KeyError, TypeError, ValueError, OverflowError):
            continue
    bars = [out[k] for k in sorted(out)]
    # Daily Yahoo bar for today's session is unfinished until after US close.
    # Do not classify its partial volume as a completed-day RVOL or breakout.
    ny_now=datetime.now(NY_TZ)
    if bars and bars[-1]["date"]==ny_now.date().isoformat():
        if ny_now.hour<16 or (ny_now.hour==16 and ny_now.minute<25):
            bars=bars[:-1]
    if len(bars)<220:
        raise ValueError(f"OHLCV_INSUFICIENTE_{len(bars)}")
    events = entry.get("events") or {}
    return bars, {"url":r.url, "currency":"USD", "exchange_code":exchange,
                  "market_timestamp":meta.get("regularMarketTime"),
                  "regular_market_price":meta.get("regularMarketPrice"),
                  "corporate_splits_in_window":len(events.get("splits") or {})}

def ema(values, n):
    result=[]; value=values[0]; a=2/(n+1)
    for x in values:
        value=a*x+(1-a)*value
        result.append(value)
    return result

def wilder(values, n):
    result=[None]*len(values)
    if len(values)<n+1:
        return result
    val=sum(values[1:n+1])/n;result[n]=val
    for i in range(n+1,len(values)):
        val=(val*(n-1)+values[i])/n
        result[i]=val
    return result

def indicators(bars):
    close=[b["close"] for b in bars]
    vol=[b["volume"] for b in bars]
    n=len(bars)-1
    E20,E50,E200=(ema(close,k) for k in (20,50,200))
    m=[x-y for x,y in zip(ema(close,12),ema(close,26))]
    ms=ema(m,9)
    gains=[0.]+[max(0,close[i]-close[i-1]) for i in range(1,len(close))]
    losses=[0.]+[max(0,close[i-1]-close[i]) for i in range(1,len(close))]
    ag,al=wilder(gains,14),wilder(losses,14)
    rsi=100 if al[n]==0 and ag[n]>0 else (50 if al[n]==0 else 100-100/(1+ag[n]/al[n]))
    tr=[bars[0]["high"]-bars[0]["low"]]
    for i in range(1,len(bars)):
        b=bars[i]; pc=close[i-1]
        tr.append(max(b["high"]-b["low"],abs(b["high"]-pc),abs(b["low"]-pc)))
    atr=wilder(tr,14)[n]
    avgvol=sum(vol[-21:-1])/20
    resistance=max(b["high"] for b in bars[-21:-1])
    support=min(b["low"] for b in bars[-21:-1])
    last=close[n]; rv=vol[n]/avgvol if avgvol>0 else None
    return {"last_close":round(last,4), "ema20":round(E20[n],4),
            "ema50":round(E50[n],4),"ema200":round(E200[n],4),
            "rsi14_wilder":round(rsi,3),"macd":round(m[n],4),
            "macd_signal":round(ms[n],4),"macd_hist":round(m[n]-ms[n],4),
            "atr14_wilder":round(atr,4),
            "rvol20":round(rv,3) if rv is not None else None,
            "resistance20_prior":round(resistance,4),
            "support20_prior":round(support,4),
            "breakout_at_daily_close":last>resistance,
            "trend_confirmed":last>E20[n]>E50[n]>E200[n],
            "near_resistance":last<resistance and resistance-last<=atr,
            "close_date":bars[n]["date"],"last_volume":vol[n]}

def independent_close(session, ticker, date):
    # Stooq is a second, distinct public source. No alternative provider: no match.
    end=date.replace("-","")
    start=(datetime.strptime(date,"%Y-%m-%d").date()-timedelta(days=14)).strftime("%Y%m%d")
    url="https://stooq.com/q/d/l/"
    r=session.get(url,params={"s":ticker.lower()+".us","i":"d","d1":start,"d2":end},timeout=15)
    r.raise_for_status()
    for row in csv.DictReader(io.StringIO(r.text)):
        if row.get("Date")==date:
            return {"source":r.url,"close":float(row["Close"]),"date":row["Date"]}
    return None

def save_history(ticker,bars):
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/(ticker.replace("-","_")+".csv")
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=("date","open","high","low","close","volume"))
        w.writeheader();w.writerows(bars)

def choose(mapping, listed, previous):
    # Only symbols listed in the actually obtained CEDEAR panel.
    all_symbols=sorted(s for s in listed if s in mapping)
    extra=[s for s in sorted(SEEDS) if s not in mapping and s in listed]
    for s in extra:
        mapping[s]={"ticker":SEEDS[s],"exchange_reference":"US_LISTED_RESEARCH_ONLY",
                    "ratio_reference":None,"isin_underlying":None,
                    "mapping_source":"CURATED_SEED_UNCONFIRMED","mapping_verified":False}
    all_symbols=sorted(set(all_symbols+extra))
    previous_watch=[str(x) for x in previous.get("watched_symbols",[]) if str(x) in all_symbols]
    priority=[s for s in PINNED if s in all_symbols]
    priority += [s for s in previous_watch if s not in priority]
    priority=priority[:min(10,MAX_BATCH)]
    rest=[s for s in all_symbols if s not in priority]
    # Rotate deterministically each run without relying on unstable random ranking.
    moment=datetime.now(timezone.utc)
    start=((moment.toordinal()*24 + moment.hour)*max(1,MAX_BATCH-len(priority))) % max(1,len(rest))
    selected=priority + [rest[(start+i)%len(rest)] for i in range(min(MAX_BATCH-len(priority),len(rest)))]
    return selected,len(all_symbols)

def run():
    now=datetime.now(TIMEZONE)
    session=requests.Session()
    session.headers.update({"User-Agent":"Mozilla/5.0 (public-market-research; no credentials)",
                            "Accept":"text/html,application/json,text/csv"})
    listed,panel_state=discover()
    mapping,mapping_state=reference(session)
    previous={}
    if REPORT.exists():
        try: previous=json.loads(REPORT.read_text(encoding="utf-8"))
        except (OSError,ValueError): pass
    selected,recognized=choose(mapping,listed,previous)
    findings=[]; failures=[]; watches=[]
    for sym in selected:
        info=mapping[sym]
        ticker=info["ticker"]
        result={"cedear":sym,"underlying":ticker,"mapping_status":info["mapping_source"],
                "mapping_verified":info["mapping_verified"],
                "ratio_reference_not_verified_for_conversion":info["ratio_reference"],
                "isin_underlying_reference":info["isin_underlying"],
                "origin_exchange_reference":info["exchange_reference"],
                "trade_status":"SIN_ENTRADA_FICTICIA_AUTORIZADA"}
        try:
            bars,origin=get_hist(session,ticker)
            metrics=indicators(bars)
            age=(now.date()-datetime.strptime(metrics["close_date"],"%Y-%m-%d").date()).days
            jumps=sum(abs(bars[i]["close"]/bars[i-1]["close"]-1)>.45 for i in range(1,len(bars)))
            result.update({"source_original":origin["url"],"currency":"USD",
                           "origin_exchange_code":origin["exchange_code"],
                           "bars_ohlcv":len(bars),"first_date":bars[0]["date"],"latest_date":bars[-1]["date"],
                           "metrics":metrics,"data_age_calendar_days":age,
                           "split_count_reported":origin["corporate_splits_in_window"],
                           "extreme_price_jumps_gt45pct":jumps})
            save_history(ticker,bars)
            enough=age>=0 and age<=5 and jumps==0 and origin["corporate_splits_in_window"]==0
            result["quality_state"]="HISTORICO_VALIDO_PRELIMINAR" if enough else "REVISAR_FRESCURA_O_CORPORATE_ACTIONS"
            technical=(metrics["trend_confirmed"] and metrics["macd_hist"]>0 and
                       50<=metrics["rsi14_wilder"]<=74 and
                       metrics["rvol20"] is not None and metrics["rvol20"]>=0.7 and
                       (metrics["near_resistance"] or metrics["breakout_at_daily_close"]))
            if technical and enough:
                try: cross=independent_close(session,ticker,metrics["close_date"])
                except (requests.RequestException,ValueError,KeyError):cross=None
                ok=cross is not None and abs(cross["close"]/metrics["last_close"]-1)<=.015
                result["independent_quote"]=cross
                result["independent_match"]=ok
                if ok and info["mapping_verified"]:
                    result["research_state"]="VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE"
                    watches.append(sym)
                else:
                    result["research_state"]="FALTA_COTEJO_INDEPENDIENTE_O_MAPEO"
            else:
                result["research_state"]="SIN_SETUP_TECNICO_CONFIRMADO"
            findings.append(result)
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            result["error"]=str(exc)[:200]
            result["quality_state"]="SIN_SERIE_VERIFICABLE"
            failures.append(result)
        time.sleep(.18)
    report={"generated_at":now.isoformat(),"mode":"PUBLIC_ONLY_PAPER_RESEARCH_NO_ORDERS",
            "universe":{"listed_cedears":len(listed),"mapped_cedears":recognized,
                        "panel_status":panel_state,"mapping_status":mapping_state,
                        "mapping_reference":[CAJA_XLSX,CAJA_URL,MAP_URL,ATLAS_URL]},
            "coverage":{"selected":len(selected),"downloaded_histories":len(findings),
                        "valid_220_ohlcv":sum(x.get("bars_ohlcv",0)>=220 for x in findings),
                        "fresh_preliminary":sum(x.get("quality_state")=="HISTORICO_VALIDO_PRELIMINAR" for x in findings),
                        "independent_matched_watches":len(watches),
                        "failures":len(failures)},
            "watched_symbols":watches, "assets":findings+failures,
            "limits":["Datos diarios estadounidenses no equivalen a operaciones en CEDEAR ARS",
                      "Ratios de terceros NO autorizan conversion: cotejar emisor oficial",
                      "Sin puntas locales contemporaneas, CCL y costos no hay entrada ni R:R neta ejecutable",
                      "Datos Yahoo/Stooq publicos sujetos a restricciones y demoras",
                      "Sin backtesting cronologico OOS no hay probabilidad calibrada",
                      "No se infieren fills desde maximos/minimos diarios ni se ejecutan operaciones"]}
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Radar CEDEARs — análisis de acciones originales", "",
           f"Generado: **{now.isoformat()}**. Solo investigación; **no operaciones**.",
           f"CEDEARs en panel: **{len(listed)}**. Mapeados: **{recognized}**. "
           f"OHLCV descargados: **{len(findings)}**. Fallidos: **{len(failures)}**.",
           f"Series con ≥220 velas: **{report['coverage']['valid_220_ohlcv']}**. "
           f"Vigilancia original con cotejo independiente: **{len(watches)}**.", "",
           "Los precios USD del subyacente NO son precios ARS del CEDEAR. "
           "Los indicadores no constituyen una recomendación ni un boleto ficticio.", "",
           "| CEDEAR | Original (USD) | Última rueda | Cierre | RSI14 | RVOL20 | Estado |",
           "|---|---|---|---:|---:|---:|---|"]
    for x in findings:
        m=x["metrics"]
        lines.append(f"| {x['cedear']} | {x['underlying']} | {m['close_date']} | "
                     f"{m['last_close']} | {m['rsi14_wilder']} | {m['rvol20']} | "
                     f"{x['research_state']} |")
    for x in failures:
        lines.append(f"| {x['cedear']} | {x['underlying']} | — | — | — | — | {x['quality_state']} |")
    lines+=["","[Auditoría JSON](docs/data/underlying_radar.json)",
            "","**PROBABILIDAD NO CALIBRADA.** Cualquier operación local requiere "
            "serie CEDEAR/ARS, ratio oficial, costo neto, cotización horaria y spread.", ""]
    MARKDOWN.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"generated_at":report["generated_at"],"coverage":report["coverage"],
                      "mapping_status":mapping_state,"panel_status":panel_state},ensure_ascii=False))
    return report

if __name__ == "__main__":
    run()
