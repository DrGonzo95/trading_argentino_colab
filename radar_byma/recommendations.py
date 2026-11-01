#!/usr/bin/env python3
"""Derive conservative per-instrument research actions from already-published evidence.

This is NOT financial advice, trade execution or a prediction. No invented entry,
stop or target. The frozen strategy has NOT demonstrated profitability.
Recommendation fields are deterministic and auditable by source/date.
"""
import json
import math
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

OUT=Path("docs/data/market.json")
CHARTS=Path("docs/data/charts.json")
CHECK=Path("docs/data/quote_check.json")
AUDIT=Path("docs/data/strategy_audit.json")
TZ=ZoneInfo("America/Argentina/Cordoba")
NOW=datetime.now(TZ)
MAX_DAY_AGE=7

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def day_age(v):
    try:
        day=date.fromisoformat(str(v)[:10])
        n=(NOW.date()-day).days
        return n if 0<=n else None
    except (ValueError,TypeError):
        return None

def decision(a, chart, cross, audit_unproven, feed_healthy):
    sym=a.get("symbol","")
    kind=a.get("kind","")
    status=a.get("status","")
    quote=a.get("quote_price")
    score=a.get("technical_score")
    rsi=a.get("rsi14")
    daily=a.get("daily_bar_date")
    close_date=(chart or {}).get("last_candle")
    age=day_age(close_date)
    tech_age=day_age(daily)
    close=(chart or {}).get("bars",[[None,None,None,None,None]])[-1][4] if chart and chart.get("bars") else None
    verified=bool(cross and cross.get("status")=="MATCH" and cross.get("market_date")==close_date and
                  cross.get("difference_pct") is not None and cross.get("difference_pct")<=.5)
    mismatch=bool(cross and cross.get("status")=="DIVERGENCE" and cross.get("market_date")==close_date)
    same_day_panel=(str(a.get("quote_retrieved_at") or "")[:10] == str(close_date))
    # Compare panel and candle only when dates are actually aligned.
    panel_gap=(abs(quote/close-1)*100 if same_day_panel and finite(quote) and
                finite(close) and close>0 else None)
    reasons=[]
    next_step=""
    action="OBSERVAR"
    label="Mantener en observación"
    level="observacion"
    no_trade=True
    if kind in ("bono","on"):
        action="ANALIZAR_CONTRATO"
        label="Analizar vencimiento y TIR"
        reasons.append("El radar no valida flujos, rendimiento efectivo, moneda ni spread de este instrumento.")
        next_step="Consultar cupón, vencimiento, amortización, moneda, TIR y puntas con fuente oficial antes de evaluar."
        level="sin_valuacion"
    elif not finite(quote) or quote<=0:
        action="ESPERAR_DATOS";label="No operar: falta precio"
        reasons.append("No hay precio público numérico utilizable.")
        next_step="Esperar una nueva cotización y validar especie, moneda y plazo de liquidación."
        level="sin_datos"
    elif mismatch or (panel_gap is not None and panel_gap>0.5):
        action="REVISAR_DISCREPANCIA";label="No operar: revisar precios"
        reasons.append("El cierre de una fuente no coincide con el de otra para la misma fecha, o con el panel.")
        next_step="Conciliar cierre, fecha, especie y moneda; no calcular operaciones con valores contradictorios."
        level="riesgo_datos"
    elif status=="ENTRADA_TEORICA_PAPEL" and finite(a.get("entry_ref")) and finite(a.get("stop_ref")) and finite(a.get("target_ref")) and finite(a.get("rr_net_est")) and a["rr_net_est"]>=2 and tech_age is not None and tech_age<=MAX_DAY_AGE and chart and close_date==daily and age is not None and age<=MAX_DAY_AGE:
        action="SIMULAR_ENTRADA";label="Simular entrada; no comprar"
        reasons.append("La señal teórica cumple RSI35, niveles y relación riesgo/beneficio estimada de al menos 2:1.")
        reasons.append("La estrategia RSI35 no demostró rentabilidad en la prueba histórica.")
        next_step="Simular SOLO después de verificar apertura siguiente, bid/ask, liquidez, moneda y riesgo; nunca usar el cierre como orden ejecutable."
        level="papel"
    elif status=="CAIDA_CON_NOVEDAD_INVESTIGAR":
        action="INVESTIGAR_CAIDA";label="Revisar caída; esperar rebote confirmado"
        if finite(a.get("change_pct")):
            reasons.append("La cotización diferida muestra una variación de "+str(round(a["change_pct"],2))+"% y hay publicaciones relacionadas.")
        else:reasons.append("Se observan novedades relacionadas con una caída de panel.")
        reasons.append("La coincidencia con una noticia no prueba causalidad ni anticipa recuperación.")
        next_step="Leer la comunicación original, evaluar impacto y buscar nueva señal técnica; no comprar solo porque cayó."
        level="investigar"
    elif status=="ENTRADA_TEORICA_PAPEL":
        action="ESPERAR_VALIDACION";label="Señal incompleta: solo observar"
        reasons.append("El radar marcó una señal de papel, pero faltan velas recientes, niveles compatibles u otra validación necesaria.")
        next_step="Comprobar histórico y niveles de la misma rueda antes de considerar siquiera una simulación."
        level="sin_datos"
    elif status=="NOVEDAD_OFICIAL":
        action="REVISAR_CNV";label="Leer hecho relevante; esperar"
        reasons.append("Existe una presentación oficial asociada, pero no hay entrada técnica confirmada.")
        next_step="Consultar el documento en CNV, separar noticia de impacto y volver a evaluar luego del próximo cierre."
        level="investigar"
    elif not finite(score) or not daily or tech_age is None or tech_age>MAX_DAY_AGE:
        action="ESPERAR_TECNICO";label="Esperar datos técnicos válidos"
        reasons.append("No existe una serie técnica reciente y validada suficiente para fundamentar una entrada.")
        next_step="Revisar noticia y cotización sin operar; esperar al menos 400 sesiones de OHLCV consistentes para el radar RSI35."
        level="sin_datos"
    elif status=="VIGILANCIA_TECNICA" or (finite(score) and score>=60):
        action="VIGILAR_TECNICA";label="Vigilar; no entrar todavía"
        reasons.append("El radar informa calidad técnica "+str(round(score,1))+"/100, pero no una señal de entrada validada.")
        if finite(rsi):reasons.append("RSI 14 último: "+str(round(rsi,1))+".")
        next_step="Esperar nuevo cierre que cumpla la regla RSI35 y calcular el riesgo neto; corroborar puntas antes de simular."
        level="vigilancia"
    else:
        action="OBSERVAR";label="Observar; sin señal"
        reasons.append("El radar no detectó condiciones completas de entrada de papel.")
        if finite(rsi):reasons.append("RSI 14: "+str(round(rsi,1))+"; el RSI aislado no es señal de compra.")
        next_step="Volver a revisar tras un cierre diario nuevo; no anticipar compra ni venta sin contexto de cartera."
        level="observacion"
    if not feed_healthy:
        reasons.append("Al menos una fuente del panel informó error o cobertura parcial.")
        if action=="SIMULAR_ENTRADA":
            action="ESPERAR_FUENTES";label="No simular: fuentes parciales";level="riesgo_datos"
    data_quality=("SEGUNDA_FUENTE_COINCIDE" if verified else
                  "SEGUNDA_FUENTE_DISCREPA" if mismatch else
                  "SOLO_FUENTE_PRINCIPAL")
    return {
      "code":action,"label":label,"category":level,"paper_only":True,
      "reasons":reasons[:3],"next_step":next_step,
      "close_date":close_date,"technical_date":daily,
      "price_quality":data_quality,
      "independent_verified":verified,
      "independent_checked_date":cross.get("market_date") if cross else None,
      "internal_close_gap_pct":round(panel_gap,3) if panel_gap is not None else None,
      "strategy_proven":not audit_unproven,
      "real_trade_allowed":False,
      "disclaimer":"Orientación de investigación con precios demorados; no es una recomendación personalizada de compra/venta."
    }

def main():
    market=json.loads(OUT.read_text(encoding="utf-8"))
    charts=json.loads(CHARTS.read_text(encoding="utf-8")).get("symbols",{}) if CHARTS.exists() else {}
    independent=json.loads(CHECK.read_text(encoding="utf-8")).get("prices",{}) if CHECK.exists() else {}
    audit=json.loads(AUDIT.read_text(encoding="utf-8")) if AUDIT.exists() else {}
    # Conservative: never claim the historical strategy is proven based on the exploratory audit.
    audit_unproven=True
    feed_healthy=market.get("meta",{}).get("data_reliable") is True
    counts={}
    for a in market.get("assets",[]):
        rec=decision(a,charts.get(a.get("symbol")),independent.get(a.get("symbol")),audit_unproven,feed_healthy)
        a["recommendation"]=rec
        counts[rec["code"]]=counts.get(rec["code"],0)+1
    market.setdefault("meta",{})["recommendations_generated_at"]=NOW.isoformat()
    market["meta"]["recommendation_method"]="Rule-based cautious decisions, no price prediction, real_trade_allowed=false. Audit frozen and not proven."
    market.setdefault("summary",{})["recommendation_counts"]=counts
    OUT.write_text(json.dumps(market,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    print("RECOMMENDATIONS",json.dumps({"total":len(market.get("assets",[])),"counts":counts,
       "independent_checked":len(independent),"audit_status":audit.get("status")},ensure_ascii=False))
if __name__=="__main__":
    main()
