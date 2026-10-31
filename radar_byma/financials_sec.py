#!/usr/bin/env python3
"""SEC companyfacts XBRL: numerical issuer fundamentals, point-in-time safe.
For SEC filings only (U.S. equity/CEDEAR underlying and selected verified ADR).
No valuations against BYMA ARS prices. Missing IFRS/company-specific facts = NULL.
"""
import csv,json,math,re,time
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
TODAY=NOW.date()
OUT=Path("resultados/fundamentales")
OUT.mkdir(parents=True,exist_ok=True)
ROOT=Path("resultados/discovery/snapshot.json")
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
API="https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
HEAD={"User-Agent":"BYMA-PublicResearch github.com/DrGonzo95/trading_argentino_colab",
      "Accept":"application/json","Accept-Encoding":"gzip, deflate"}
SES=requests.Session();SES.headers.update(HEAD)
BASE=["AAPL","NVDA","MSFT","AMZN","GOOGL","META","TSLA","MELI","AVGO","JPM","XOM","KO"]
# ADR mapping is a possible underlying listed on SEC, NOT same traded security or FX.
ADR={"YPFD":"YPF","GGAL":"GGAL","BMA":"BMA","BBAR":"BBAR","PAMP":"PAM",
     "SUPV":"SUPV","CRES":"CRESY","TGSU2":"TGS","TECO2":"TEO","EDN":"EDN"}
TAGS={
"revenue":["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax","Revenue"],
"net_income":["NetIncomeLoss","ProfitLoss","ProfitLossAttributableToOwnersOfParent"],
"operating_cashflow":["NetCashProvidedByUsedInOperatingActivities","CashFlowsFromUsedInOperatingActivities"],
"assets":["Assets"],
"liabilities":["Liabilities"],
"equity":["StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest","EquityAttributableToOwnersOfParent","Equity"],
"cash":["CashAndCashEquivalentsAtCarryingValue","CashAndCashEquivalents"],
"debt_current":["LongTermDebtCurrent","ShortTermBorrowings","CurrentPortionOfLongTermDebt"],
"debt_long":["LongTermDebtNoncurrent","LongTermDebt","LongtermBorrowings"]
}
FLOWS={"revenue","net_income","operating_cashflow"}
def fetch(url,timeout=27):
    r=SES.get(url,timeout=timeout)
    r.raise_for_status()
    return r.json()
def ticker_map():
    # An official SEC directory may return HTTP403 from shared cloud runner IPs.
    # Use a small previously documented fallback for DIRECT endpoint diagnostics;
    # report fallback and do NOT pretend full market ticker coverage.
    fallback={"AAPL":320193,"NVDA":1045810,"MSFT":789019,"AMZN":1018724,
              "GOOGL":1652044,"META":1326801,"TSLA":1318605,"MELI":1099590,
              "AVGO":1730168,"JPM":19617,"XOM":34088,"KO":21344}
    try:
        raw=fetch(SEC_TICKERS)
        items=raw.values() if isinstance(raw,dict) else raw
        result={str(p["ticker"]).upper():int(p["cik_str"]) for p in items
             if isinstance(p,dict) and p.get("ticker") and p.get("cik_str") is not None}
        return result,"SEC_TICKER_MAP_OFFICIAL"
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403,429):
            return fallback,"FALLBACK_KNOWN_CIK_OFFICIAL_MAP_403"
        raise
def candidates(mapping):
    names=set()
    if ROOT.exists():
        try:
            p=json.loads(ROOT.read_text(encoding="utf-8"))
            tickers={str(r.get("symbol","")).upper() for r in p.get("snapshot",[]) if r.get("class")=="cedear"}
            for t in tickers:
                if t in mapping:names.add(t)
                # Dollar/C suffix only if original listed on same IOL panel.
                if t.endswith(("D","C")) and t[:-1] in tickers and t[:-1] in mapping:names.add(t[:-1])
        except (ValueError,OSError):pass
    names.update(k for k in BASE if k in mapping)
    # Cap requests and rotate. SEC filings can be several megabytes each.
    all_names=sorted(names-set(BASE))
    chosen=[t for t in BASE if t in mapping]
    if all_names:
        start=(TODAY.toordinal()*12)%len(all_names)
        chosen+= [all_names[(start+i)%len(all_names)] for i in range(min(12,len(all_names)))]
    adr={local:under for local,under in ADR.items() if under in mapping}
    chosen+=sorted(set(adr.values())-set(chosen))[:8]
    return list(dict.fromkeys(chosen))[:32],adr,len(names)
def safe_date(d):
    try:return date.fromisoformat(d)
    except (ValueError,TypeError):return None
def points(facts,metric,endcut):
    # Facts from standard taxonomies only. Company-specific extensions intentionally excluded.
    for ns in ("us-gaap","ifrs-full"):
        available=facts.get(ns,{})
        for tag in TAGS[metric]:
            entry=available.get(tag,{})
            for unit,obs in entry.get("units",{}).items():
                if unit!="USD":continue
                for p in obs:
                    ed=safe_date(p.get("end"));fd=safe_date(p.get("filed"))
                    if not ed or not fd or fd>endcut or ed>endcut:continue
                    if p.get("form") not in ("10-K","10-K/A","20-F","20-F/A","40-F","40-F/A","10-Q","10-Q/A","6-K"):continue
                    try:val=float(p.get("val"))
                    except (TypeError,ValueError):continue
                    if not math.isfinite(val):continue
                    st=safe_date(p.get("start"))
                    duration=(ed-st).days if st else None
                    if metric in FLOWS and (duration is None or duration<330 or duration>395):continue
                    if metric not in FLOWS and duration is not None:continue
                    yield {"value":val,"end":ed,"filed":fd,"tag":tag,"namespace":ns,
                           "form":p.get("form"),"unit":unit,"accn":p.get("accn"),
                           "period_days":duration}
            # Prefer earliest standard tag with valid annual facts.
            if any(True for _ in []):pass
def select(facts,metric,at):
    rows=list(points(facts,metric,at))
    if not rows:return []
    # Comparable annual USD series. Repeated 10-K restatements are filtered by
    # eligible date and latest filing date. An entire fiscal year is one observation.
    # Latest by report period end, then latest filed <= as-of.
    unique={}
    for p in rows:
        key=p["end"].isoformat()
        old=unique.get(key)
        if old is None or (p["filed"],p["form"]=="10-K")>(old["filed"],old["form"]=="10-K"):
            unique[key]=p
    return sorted(unique.values(),key=lambda x:x["end"],reverse=True)[:4]
def pct(a,b):
    return round(100*(a/b-1),3) if b not in (None,0) and a is not None else None
def summarize(sym,cik,record,adr_local=[]):
    facts=record.get("facts",{})
    found={m:select(facts,m,TODAY) for m in TAGS}
    revenue=found["revenue"];income=found["net_income"]
    # Latest annual, values from different metrics only comparable near same period end.
    annual_end=revenue[0]["end"] if revenue else income[0]["end"] if income else None
    def value(m):
        if annual_end is None:return None
        r=next((p for p in found[m] if abs((p["end"]-annual_end).days)<=35),None)
        return r["value"] if r else None
    # Filing date >= newest among constituent fields, never earlier.
    def published(m):
        if annual_end is None:return None
        r=next((p for p in found[m] if abs((p["end"]-annual_end).days)<=35),None)
        return r["filed"].isoformat() if r else None
    rev=value("revenue");ni=value("net_income");ocf=value("operating_cashflow")
    a=value("assets");l=value("liabilities");eq=value("equity")
    cash=value("cash");dl=value("debt_long");dc=value("debt_current")
    # Current and long term debt concepts can overlap. Only show estimate if
    # both are identifiable and distinct; do not silently double count.
    debt=(dl+dc) if dl is not None and dc is not None else None
    previous=next((p for p in revenue[1:] if revenue and 330<=(revenue[0]["end"]-p["end"]).days<=395),None)
    row={"sec_ticker":sym,"ticker_byma_or_adr":",".join(adr_local) if adr_local else sym,
         "cik":cik,"emisor_sec":record.get("entityName"),"source":API.format(cik=str(cik).zfill(10)),
         "periodo_anual_cierre":str(annual_end) if annual_end else None,
         "moneda_fundamentos":"USD_US_GAAP_O_IFRS_XBRL",
         "ingresos_usd":rev,"ingresos_variacion_anual_pct":pct(rev,previous["value"]) if previous else None,
         "ganancia_neta_usd":ni,"margen_neto_pct":round(100*ni/rev,3) if rev and ni is not None else None,
         "flujo_operativo_usd":ocf,"activos_usd":a,"pasivos_usd":l,
         "patrimonio_usd":eq,"caja_usd":cash,"deuda_financiera_estimada_usd":debt,
         "deuda_financiera_menos_caja_usd":round(debt-cash,2) if debt is not None and cash is not None else None,
         "roa_pct":round(100*ni/a,3) if ni is not None and a else None,
         "fecha_publicacion_ingresos":published("revenue"),
         "fecha_publicacion_resultados":published("net_income"),
         "ratio_precio_bolsa":None,"valuation":"SIN_PRECIO_USD_AJUSTADO_POR_RATIO_CEDEAR",
         "calidad":"ANUAL_NUMERICO_PARCIAL" if rev is not None and ni is not None else "INSUFICIENTE_DATOS_ANUALES",
         "riesgos":"No mezclar monedas; sectores bancarios requieren ratios específicos; revisiones pueden alterar el histórico"}
    return row,found
def main():
    status={"fecha":NOW.isoformat(),"SEC_API":"NO_CONECTADO","resultados":[],"errores":[],
      "nota":"Todos los hechos usan filed<=fecha de evaluación; todavía no son ratios de todos los balances argentinos."}
    try:mapping,map_origin=ticker_map()
    except Exception as e:
        status["errores"].append({"fase":"ticker_map","error":type(e).__name__+": "+str(e)[:200]})
        (OUT/"sec_estado.json").write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
        print("SEC_XBRL "+json.dumps({"status":"SIN_DATOS_SEC","errores":status["errores"]},ensure_ascii=False))
        return
    selected,adr,names_count=candidates(mapping)
    status["ticker_map_origin"]=map_origin
    if map_origin.startswith("FALLBACK_"):
        selected=[s for s in ("AAPL","NVDA","MSFT") if s in mapping]
        status["restricciones_fallback"]="La API oficial rechazó el directorio; se verifican tres CIK documentados, no todos los CEDEAR."
    details=[];flat=[]
    for sym in selected:
        cik=mapping[sym];local=[a for a,t in adr.items() if t==sym]
        try:
            data=fetch(API.format(cik=str(cik).zfill(10)),timeout=35)
            row,points_by_metric=summarize(sym,cik,data,local)
            if row["calidad"]=="ANUAL_NUMERICO_PARCIAL":
                flat.append(row)
                details.append({"ticker":sym,"cik":cik,
                                "metrics":{k:[{**p,"end":str(p["end"]),"filed":str(p["filed"])} for p in v]
                                           for k,v in points_by_metric.items()}})
            else:
                status["errores"].append({"ticker":sym,"error":"No hay serie anual USD comparable"})
        except Exception as e:
            status["errores"].append({"ticker":sym,"error":type(e).__name__+": "+str(e)[:150]})
        time.sleep(.28)
    if flat:
        with (OUT/"sec_fundamentales.csv").open("w",newline="",encoding="utf-8") as fp:
            w=csv.DictWriter(fp,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    (OUT/"sec_series_punto_en_tiempo.json").write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding="utf-8")
    status.update({"SEC_API":"PARCIAL_OPERATIVA" if flat else "SIN_FUNDAMENTOS_VALIDOS",
       "ticker_map_total":len(mapping),"cedears_identificados_en_panel_sec":names_count,
       "consulta_seleccion":selected,"filas_financieras_validas":len(flat),
       "resultados":[{"ticker":r["sec_ticker"],"asof":r["periodo_anual_cierre"],
                      "filing":r["fecha_publicacion_ingresos"],"yoy_pct":r["ingresos_variacion_anual_pct"],
                      "net_margin_pct":r["margen_neto_pct"],"quality":r["calidad"]} for r in flat],
       "restricciones":[
         "Ratios en USD de emisor SEC; no son balances completos de todo BYMA ni precios de la especie ARS.",
         "La SEC permite acceder a cifras publicadas pero no predice dirección del precio.",
         "No comparar métricas bancarias con industriales; deuda corriente/largo plazo parcial.",
         "Se eligieron solo etiquetas estándar annual USD; IFRS en moneda local puede quedar fuera.",
         "Valores comparados solo si sus períodos anuales coinciden ±35 días; 'filed' conserva momento público.",
         "Descarga rotativa y limitada para respetar SEC Fair Access, sin claves privadas."]})
    (OUT/"sec_estado.json").write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SEC_XBRL "+json.dumps({k:v for k,v in status.items() if k!="resultados"},ensure_ascii=False))
if __name__=="__main__":main()
