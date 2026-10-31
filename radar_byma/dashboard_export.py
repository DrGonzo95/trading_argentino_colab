#!/usr/bin/env python3
"""Prepare a static BYMA dashboard from public delayed panels and verified research.

No real-time feed, no broker access, no execution. Quotes have unknown true
exchange timestamp. Full generated_at is the retrieval/processing time ONLY.
An actionable paper setup requires a previously completed daily candle,
consistent finite levels and reward/risk >= 2 after modeled expenses.
"""
import ast, csv, json, math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("America/Argentina/Cordoba")
NOW=datetime.now(TZ)
ROOT=Path("resultados")
OUT=Path("docs/data")
OUT.mkdir(parents=True,exist_ok=True)
STATE=Path("radar_byma/state")
FEE_SIDE=.0055*1.21+.001

def read_json(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError,ValueError):return {}
def read_csv(path):
    try:
        with Path(path).open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
    except (OSError,ValueError):return []
def numeric(x):
    try:
        v=float(x)
        return round(v,6) if math.isfinite(v) else None
    except (TypeError,ValueError):return None
def date_parse(s):
    try:
        dt=datetime.fromisoformat(str(s).replace("Z","+00:00"))
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    except (ValueError,TypeError):return None
def date_age(s):
    try:return (NOW.date()-datetime.strptime(str(s),"%Y-%m-%d").date()).days
    except (ValueError,TypeError):return None
def recent(s,maxdays):
    dt=date_parse(s)
    return dt is not None and timedelta(0)<=NOW-dt<=timedelta(days=maxdays)
def event_sort(e):
    return date_parse(e.get("published")) or datetime(1970,1,1,tzinfo=TZ)
def qty_from_csv(t,cap):
    raw=t.get("unidades_referencia") or {}
    if isinstance(raw,str):
        try:raw=ast.literal_eval(raw)
        except (SyntaxError,ValueError):raw={}
    if not isinstance(raw,dict):return 0
    try:return max(0,int(raw.get(str(cap),0) or 0))
    except (TypeError,ValueError):return 0

def level_ok(t):
    price=numeric(t.get("entrada_teorica_basada_en_cierre"))
    stop=numeric(t.get("stop_teorico"))
    target=numeric(t.get("objetivo_teorico"))
    rr=numeric(t.get("rr_neto_referencia"))
    close_day=t.get("fecha_historico")
    age=date_age(close_day)
    if any(x is None for x in (price,stop,target,rr)) or age is None:return False
    return 0<stop<price<target and rr>=2 and 0<=age<=5
def main():
    panel=read_json(ROOT/"discovery/snapshot.json")
    if not panel.get("snapshot"):raise RuntimeError("No hay panel publico; no generar señales antiguas como actuales.")
    technical={x.get("simbolo"):x for x in read_csv(ROOT/"ranking/acciones_cedears_analisis_tecnico.csv")}
    history=read_json(STATE/"event_history.json").get("events",{})
    sec=read_json(STATE/"sec_latest.json")
    third=read_json(STATE/"secondary_latest.json")
    arg=read_json(STATE/"local_financials.json").get("records",{})
    sec_by={r.get("ticker"):r for r in sec.get("resultados",[])}
    third_by={r.get("ticker"):r for r in third.get("results",[]) if r.get("ticker")}
    source_group={r.get("symbol"):r.get("class") for r in panel.get("snapshot",[])}
    all_events={}
    for e in history.values():
        ticker=e.get("ticker")
        if not ticker or not recent(e.get("asof_usable"),10):continue
        all_events.setdefault(ticker,[]).append(e)
    for entries in all_events.values():entries.sort(key=event_sort,reverse=True)
    result=[]
    for r in panel["snapshot"]:
        sym=str(r.get("symbol") or "")
        kind=r.get("class")
        if not sym or kind not in ("accion","cedear","bono","on"):continue
        t=technical.get(sym,{})
        e=all_events.get(sym,[])[:5]
        actual_events=[x for x in e if x.get("source") in ("CNV_OFICIAL","NEWS_HEADLINE")]
        official=sum(x.get("source")=="CNV_OFICIAL" for x in actual_events)
        news=sum(x.get("source")=="NEWS_HEADLINE" for x in actual_events)
        price=numeric(r.get("last_delayed"))
        change=numeric(r.get("variation_pct"))
        turnover=numeric(r.get("turnover_indicative"))
        technical_score=numeric(t.get("puntaje_tecnico"))
        entry=numeric(t.get("entrada_teorica_basada_en_cierre"))
        stop=numeric(t.get("stop_teorico"))
        target=numeric(t.get("objetivo_teorico"))
        rr=numeric(t.get("rr_neto_referencia"))
        active=(kind in ("accion","cedear") and t.get("estado")=="SEÑAL_RSI35_PAPEL"
                and level_ok(t)
                and turnover is not None and turnover>=5000000
                and not r.get("possible_fx_variant")
                and (qty_from_csv(t,100000)>0))
        has_negative=change is not None and change<=-3
        has_recent_news=bool(actual_events)
        if active:status="ENTRADA_TEORICA_PAPEL"
        elif kind in ("accion","cedear") and has_negative and has_recent_news:
            status="CAIDA_CON_NOVEDAD_INVESTIGAR"
        elif kind in ("accion","cedear") and technical_score is not None and technical_score>=60:
            status="VIGILANCIA_TECNICA"
        elif official>0:
            status="NOVEDAD_OFICIAL"
        else:status="SOLO_SEGUIMIENTO"
        # The watch score is not expected return, only research ordering.
        priority=(min(37,technical_score*.35) if technical_score is not None else 0)
        priority+=min(23,official*8)+min(12,news*3)
        if has_negative and has_recent_news:priority+=17
        if active:priority+=28
        if kind in ("bono","on"):priority=min(priority,23)
        if not turnover or turnover<5000000:priority-=4
        priority=max(0,min(100,round(priority,1)))
        fundamental=None
        if kind=="accion" and arg.get(sym,{}).get("status")=="ANNUAL_FOUND":
            d=arg[sym]["statement"]
            fundamental={"source":"tabla_terceros_nominal_ARS","fy":d.get("year"),
                "sales_yoy_pct":numeric(d.get("revenue_yoy_nominal_pct")),
                "net_margin_pct":numeric(d.get("net_income_margin_pct")),
                "url":d.get("source"),"point_in_time":False}
        elif kind=="cedear" and third.get("status")=="SECONDARY_SNAPSHOT_ONLY" and recent(third.get("fetched_at"),15) and sym in third_by:
            d=third_by[sym]
            fundamental={"source":"tabla_terceros_anual_USD","fy":d.get("fiscal_year"),
                "sales_yoy_pct":numeric(d.get("revenue_growth_nominal_pct")),
                "net_margin_pct":numeric(d.get("net_profit_margin_pct")),
                "url":d.get("source"),"point_in_time":False}
        warnings=[]
        if r.get("possible_fx_variant"):warnings.append("Posible especie en otra moneda/plazo: verificar.")
        if not t or technical_score is None:warnings.append("Sin OHLCV diario validado para calcular señal.")
        if not r.get("spread_pct_delayed"):warnings.append("No hay spread/profundidad utilizable.")
        if turnover is None or turnover<5000000:warnings.append("Actividad indicativa baja: ejecución incierta.")
        if has_negative and has_recent_news:warnings.append("La caída coincide con publicaciones; causalidad no comprobada.")
        if active:warnings.append("Entrada y niveles derivados del cierre diario, NO de una cotización en vivo.")
        if kind in ("bono","on"):warnings.append("Sin TIR, cupones y vencimientos conciliados: solo observación.")
        event_objects=[{"title":x.get("title","")[:260],"source":x.get("source"),
                        "published":x.get("published"),
                        "observed_first":x.get("first_seen"),
                        "url":x.get("url")}
                       for x in actual_events[:4]]
        row={"symbol":sym,"kind":kind,"status":status,"score":priority,
            "quote_price":price,"change_pct":change,"turnover":turnover,
            "quote_retrieved_at":r.get("scraped_at"),"quote_exchange_time":None,
            "quote_currency_verified":False,"quote_delayed":True,
            "bid":numeric(r.get("best_bid_delayed")),"ask":numeric(r.get("best_ask_delayed")),
            "spread_pct_delayed":numeric(r.get("spread_pct_delayed")),
            "technical_score":technical_score,"technical_status":t.get("estado") or "SIN_HISTORICO",
            "rsi14":numeric(t.get("rsi14")),"rvol":numeric(t.get("volumen_relativo")),
            "trend_bull":t.get("en_tendencia_larga") if technical_score is not None else None,
            "daily_bar_date":t.get("fecha_historico"),
            "bars":int(t.get("ruedas") or 0),
            "entry_ref":entry if active else None,
            "stop_ref":stop if active else None,
            "target_ref":target if active else None,
            "rr_net_est":rr if active else None,
            "example_qty_50k":qty_from_csv(t,50000) if active else None,
            "example_qty_100k":qty_from_csv(t,100000) if active else None,
            "events_official":official,"events_news":news,
            "events":event_objects,"fundamental":fundamental,
            "warnings":warnings[:5],
            "source_url":"https://iol.invertironline.com/mercado/cotizaciones/argentina/",
            "assumed_cost_per_side_pct":round(100*FEE_SIDE,4),
            "risk_pct":.5,"max_allocation_pct":20,
            "paper_only":True,"horizon":"1 a 5 ruedas",
            "actual_order":False}
        result.append(row)
    result.sort(key=lambda x:(x["status"]!="ENTRADA_TEORICA_PAPEL",
                              x["status"]!="CAIDA_CON_NOVEDAD_INVESTIGAR",
                              -x["score"],x["symbol"]))
    byclass={g:sum(r["kind"]==g for r in result) for g in ("accion","cedear","bono","on")}
    total_paper=sum(r["status"]=="ENTRADA_TEORICA_PAPEL" for r in result)
    pending=sum(r["status"]=="CAIDA_CON_NOVEDAD_INVESTIGAR" for r in result)
    out={"meta":{"generated_at":NOW.isoformat(),"source_snapshot_at":panel.get("scanned_at"),
          "market_data":"IOL - consulta pública diferida, NO cotizaciones en tiempo real",
          "quote_time_verified":False,
          "provider_stated_delay":"No calculable: se desconoce timestamp real del último negocio",
          "next_fetch":"GitHub Actions mejor esfuerzo cada 15 minutos en rueda",
          "data_reliable":not bool(panel.get("errors")),
          "provider_errors":panel.get("errors",{}),
          "market":"BYMA, especies identificadas en paneles públicos"},
          "summary":{"total":len(result),"types":byclass,
                     "paper_setups":total_paper,"watch_catalyst":pending,
                     "fundamentals":sum(x["fundamental"] is not None for x in result),
                     "validated_tech":sum(x["technical_score"] is not None for x in result)},
          "assets":result}
    (OUT/"market.json").write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    print("DASHBOARD_EXPORTED "+json.dumps({"assets":len(result),"paper_setups":total_paper,
       "catalyst_watch":pending,"tech":out["summary"]["validated_tech"],
       "fundamentals":out["summary"]["fundamentals"],"bytes":(OUT/"market.json").stat().st_size,
       "provider_panels_ok":out["meta"]["data_reliable"]},ensure_ascii=False))
if __name__=="__main__":main()
