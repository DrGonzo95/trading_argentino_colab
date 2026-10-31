#!/usr/bin/env python3
"""Strictly filed-date SEC XBRL quantitative screening for BYMA CEDEAR issuers.
No keys. SEC official data only; no inferred earnings from social/news headlines.
Requires USD units, matching duration, and year-ago comparison. Non-US
foreign private issuers and ETFs without comparable 10-Q/10-K fail closed.
"""
import csv,json,os,time,math,re
from datetime import datetime,date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

OUT=Path("resultados/fundamentales");OUT.mkdir(parents=True,exist_ok=True)
STATE=Path("radar_byma/cache/sec_fundamentals.json")
STATE.parent.mkdir(parents=True,exist_ok=True)
PANEL=Path("resultados/discovery/snapshot.json")
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
BASE="https://data.sec.gov/api/xbrl/companyfacts/CIK{:010d}.json"
SUB="https://data.sec.gov/submissions/CIK{:010d}.json"
HEADERS={"User-Agent":"BYMA-public-finance-research/1.0 https://github.com/DrGonzo95/trading_argentino_colab",
         "Accept":"application/json"}
S=requests.Session();S.headers.update(HEADERS)
REVENUE=["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues",
         "SalesRevenueNet","SalesRevenueGoodsNet","RevenueFromContractWithCustomerIncludingAssessedTax"]
NET=["NetIncomeLoss","ProfitLoss"]
OPERATING=["OperatingIncomeLoss"]
FLOWS=["NetCashProvidedByUsedInOperatingActivities"]
def get(url):
    response=S.get(url,timeout=22)
    response.raise_for_status()
    return response.json()
def as_date(v):
    try:return date.fromisoformat(v)
    except (ValueError,TypeError):return None
def periods(facts,tags):
    gaap=facts.get("facts",{}).get("us-gaap",{})
    result=[]
    for tag in tags:
        units=gaap.get(tag,{}).get("units",{}).get("USD",[])
        for r in units:
            if r.get("form") not in ("10-Q","10-K"):continue
            start=as_date(r.get("start"));end=as_date(r.get("end"))
            filed=as_date(r.get("filed"))
            v=r.get("val")
            if not start or not end or not filed or filed>NOW.date() or not isinstance(v,(int,float)):continue
            length=(end-start).days
            period="quarter" if 65<=length<=110 else "annual" if 330<=length<=385 else None
            if period is None:continue
            if (NOW.date()-filed).days>800:continue
            result.append({"tag":tag,"period":period,"start":start,"end":end,"filed":filed,"value":float(v),"accession":r.get("accn")})
    # Prefer latest publication per end/period and preferred standardized tag.
    result.sort(key=lambda r:(r["end"],r["filed"],-tags.index(r["tag"])),reverse=True)
    unique={}
    for r in result:
        k=(r["period"],r["end"])
        if k not in unique:unique[k]=r
    return list(unique.values())
def compare(facts,tags):
    records=periods(facts,tags)
    for kind in ("quarter","annual"):
        valid=sorted((r for r in records if r["period"]==kind and (NOW.date()-r["filed"]).days<=180),
                     key=lambda r:(r["end"],r["filed"]),reverse=True)
        for current in valid:
            prev=sorted((r for r in records if r["period"]==kind and
                330<=(current["end"]-r["end"]).days<=400 and
                330<=(current["start"]-r["start"]).days<=400 and
                r["filed"]<=NOW.date()),key=lambda r:abs((current["end"]-r["end"]).days-365))
            if not prev:continue
            last=prev[0]
            if last["value"]==0:continue
            ratio=current["value"]/abs(last["value"])-last["value"]/abs(last["value"])
            # For negative previous earnings, interpretation is ambiguous; report absolute delta separately.
            return {"kind":kind,"current":current,"previous":last,
                    "growth_pct":round((current["value"]-last["value"])/abs(last["value"])*100,2),
                    "delta":current["value"]-last["value"]}
    return None
def public_summary(name,cik,issuer):
    data=get(BASE.format(cik));time.sleep(.3)
    reports=get(SUB.format(cik));time.sleep(.3)
    recent=reports.get("filings",{}).get("recent",{})
    forms=list(zip(recent.get("form",[]),recent.get("filingDate",[]),recent.get("accessionNumber",[])))
    filed=[{"form":form,"filed":filed,"accession":acc} for form,filed,acc in forms
           if form in ("10-Q","10-K") and as_date(filed) and 0<=(NOW.date()-as_date(filed)).days<=120]
    if not filed:raise ValueError("NO_10Q_10K_RECIENTE")
    rev=compare(data,REVENUE)
    net=compare(data,NET)
    operating=compare(data,OPERATING)
    if rev is None or net is None:raise ValueError("SIN_COMPARABLES_USD_DE_REVENUE_Y_NET_INCOME")
    if rev["kind"]!=net["kind"] or abs((rev["current"]["end"]-net["current"]["end"]).days)>10:
        raise ValueError("PERIODOS_NO_COMPARABLES")
    # Income margin and improvement are computed on the same period and currency.
    revenue=rev["current"]["value"];prior_rev=rev["previous"]["value"]
    net_income=net["current"]["value"];prior_net=net["previous"]["value"]
    if revenue<=0 or prior_rev<=0:raise ValueError("INGRESOS_NO_POSITIVOS")
    margin=100*net_income/revenue
    prevmargin=100*prior_net/prior_rev
    impact=float(rev["delta"])
    # Pre-committed economic gate; no news/social vote, no future prices.
    # Earnings can be loss-making but not automatically positive merely on growth.
    strong=(rev["growth_pct"]>=8 and net_income>0 and
            net_income>=prior_net and margin>=prevmargin and margin>=5)
    recent_sec=sorted(filed,key=lambda r:r["filed"],reverse=True)
    # Only report if period published recently enough to be relevant, avoiding stale
    # claims based on a different 10-K/10-Q.
    delta_days=(NOW.date()-rev["current"]["filed"]).days
    if delta_days>120:raise ValueError("ESTADOS_NO_RECIENTES")
    return {"ticker":name,"emisor_sec":issuer,"cik":cik,
       "estado":"IMPACTO_CUANTIFICADO" if strong else "BALANCE_CUANTIFICADO_NO_SUPERA_FILTRO",
       "tipo_periodo":rev["kind"],"cierre_periodo":str(rev["current"]["end"]),
       "presentado_sec":str(rev["current"]["filed"]),
       "fecha_disponible_desde":str(max(rev["current"]["filed"],net["current"]["filed"])),
       "crecimiento_ingresos_yoy_pct":rev["growth_pct"],
       "crecimiento_beneficio_yoy_pct":net["growth_pct"],
       "ingresos_usd":revenue,"cambio_ingresos_usd_yoy":impact,
       "beneficio_usd":net_income,"beneficio_usd_yoy_anterior":prior_net,
       "margen_neto_pct":round(margin,2),"margen_neto_anterior_pct":round(prevmargin,2),
       "margen_neto_cambio_puntos":round(margin-prevmargin,2),
       "operating_comparable":bool(operating),
       "puerta_fundamental":strong,
       "documento_form":recent_sec[0]["form"],
       "acceso_fuente_sec":"https://www.sec.gov/Archives/edgar/data/"+str(cik)+"/"+recent_sec[0]["accession"].replace("-","")+"/",
       "api_datos_sec":BASE.format(cik),"api_presentaciones_sec":SUB.format(cik),
       "interpretacion":"Variación contable USD sobre período comparable; NO impacto causal de la noticia, ni sorpresa vs consenso.",
       "advertencia":"Solo emisores US-GAAP con series SEC suficientes; el precio del CEDEAR ARS incluye tipo de cambio."}
def main():
    if not PANEL.exists():raise RuntimeError("No se encontró panel de CEDEARs")
    snapshots=json.loads(PANEL.read_text(encoding="utf-8"))
    universe={r["symbol"] for r in snapshots.get("snapshot",[]) if r.get("class")=="cedear"}
    states={};accepted=[];errors={}
    try:
        listing=get(SEC_TICKERS)
        mapping={v["ticker"].upper():v for v in listing.values() if isinstance(v,dict) and v.get("ticker")}
    except Exception as e:
        listing={};mapping={}
        errors["sec_ticker_directory"]=type(e).__name__+": "+str(e)[:150]
    # Large CEDEAR universe, avoid downloading hundreds of XBRL files per run.
    # Stable high-profile priority plus deterministic rotation over remaining SEC-matched issuers.
    priority=("AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","MELI","GOOG","JPM","KO","XOM",
              "AVGO","V","MA","BRKB","NFLX","AMD","QCOM","CAT","WMT","ADBE","LLY")
    known=[s for s in priority if s in universe and s in mapping]
    other=sorted(universe & set(mapping)-set(known))
    shift=(NOW.toordinal()*13)%len(other) if other else 0
    selected=(known[:12]+(other[shift:]+other[:shift])[:13])[:25]
    for ticker in selected:
        v=mapping[ticker]
        try:
            rec=public_summary(ticker,v["cik_str"],v["title"])
            accepted.append(rec)
            states[ticker]={"estado":rec["estado"],"cik":v["cik_str"]}
        except Exception as e:
            states[ticker]={"estado":"SIN_CUANTIFICACION_COMPARABLE",
                             "motivo":type(e).__name__+": "+str(e)[:160]}
        time.sleep(.3)
    # Always write both no-data states and numerical evidence.
    if accepted:
        fields=list(dict.fromkeys(k for r in accepted for k in r))
        with (OUT/"sec_ratios_verificados.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(accepted)
    response={"hora":NOW.isoformat(),"cobertura_cedears_panel":len(universe),
       "coincidencias_directorio_sec":len(universe & set(mapping)),
       "emisores_consultados":selected,"balances_usd_comparables":len(accepted),
       "cumplen_filtro_fundamental":sum(x["puerta_fundamental"] for x in accepted),
       "estados_por_emisor":states,"errores_fuentes":errors,
       "metodo":"10-Q/10-K US-GAAP; USD; comparable misma duración y trimestre o anual; revenue yoy >=8%, utilidad positiva no decreciente, margen neto >=5% y sin deterioro.",
       "advertencias":[
           "La SEC es fuente oficial para emisoras sujetas a reportes estadounidenses; ETFs, emisoras extranjeras sin 10-Q y firmas no comparables se excluyen.",
           "No existe una API estructurada de todos los balances de empresas argentinas ya verificada en este proyecto; sus ratios NO se inventan.",
           "No se interpreta una noticia como señal de compra; la puerta fundamental es sólo un requisito, no predice retornos.",
           "El ticker SEC exige coincidencia exacta; correspondencia CEDEAR, ratio de conversión y moneda de cada especie no verificados.",
           "Datos históricos de filings respetan la fecha de presentación; backtest de eventos SEC independiente NO implementado." ]}
    (OUT/"sec_estado.json").write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SEC_FUNDAMENTALES "+json.dumps({k:v for k,v in response.items() if k not in ("estados_por_emisor","emisores_consultados","advertencias")},ensure_ascii=False))
    print("SEC_FILTRO_POSITIVO "+json.dumps([{"ticker":r["ticker"],"crecimiento":r["crecimiento_ingresos_yoy_pct"],"margen":r["margen_neto_pct"],"filed":r["fecha_disponible_desde"]} for r in accepted if r["puerta_fundamental"]],ensure_ascii=False))
if __name__=="__main__":main()
