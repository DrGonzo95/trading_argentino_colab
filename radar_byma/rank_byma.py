#!/usr/bin/env python3
"""BYMA two-stage public radar, explicitly NOT real-time or a real broker.
Step 1: screen all quoted IOL panel instruments (including bonds and ONs).
Step 2: confirm stock/CEDEAR setups only with validated daily OHLCV.
Ranking is heuristic, descriptive; NEVER implies historical profitability.
"""
import csv,json,math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from research_advanced import features

ROOT=Path("resultados")
OUT=ROOT/"ranking"
OUT.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
BONDS={"bono","on"}
CHARGES=(.005+.0005)*1.21
SLIP=.001
RISK=.005
EXPOSURE=.20
def limit(x,low,high):
    return max(low,min(high,x))
def write_csv(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def one_asset(r,peer_max):
    amount=float(r.get("turnover_indicative") or 0)
    rate=r.get("variation_pct")
    sym=r["symbol"]
    typ=r["class"]
    own_cash=peer_max.get(typ,1)
    liquidity=round(60*min(1,math.log1p(amount)/max(1,math.log1p(own_cash))),1) if amount>0 else 0
    change=float(rate) if rate is not None else None
    # 20 pts for moderate movement; large leaps need event/corporate action review.
    smooth=0 if change is None else 20*limit(1-abs(abs(change)-1.5)/9,0,1)
    score=round(liquidity+smooth+(15 if r.get("last_delayed",0)>0 else 0),1)
    flag=[]
    if r.get("possible_fx_variant"):flag.append("posible_especie_duplicada_por_moneda")
    if amount<5e6:flag.append("poco_monto_indicativo")
    if change is not None and abs(change)>10:flag.append("variacion_extrema_verificar_evento")
    if not r.get("last_delayed"):flag.append("precio_ausente")
    return {"simbolo":sym,"tipo":typ,"ultimo_precio_demorado":r.get("last_delayed"),
            "variacion_diaria_pct":change,"monto_operado_indicativo":amount,
            "puntaje_preseleccion":score,"control":";".join(flag) or "solo_cribado_diferido",
            "fuente":r.get("provider"),"hora_cotizacion":"NO_VERIFICADA",
            "advertencia":"No es señal de compra ni puntuación de rentabilidad"}
def tech(candidate):
    sym=candidate["simbolo"]; typ=candidate["tipo"]
    if typ not in ("accion","cedear"):return None
    f=ROOT/f"{sym}_ohlcv.csv"
    if not f.exists():return {**candidate,"estado":"NO_HISTORICO_VALIDADO","puntaje_tecnico":None}
    try:
        d=pd.read_csv(f,parse_dates=["date"]).sort_values("date")
        if len(d)<400 or d.date.duplicated().any():raise ValueError("Serie insuficiente o duplicada")
        x=features(d);last=x.iloc[-1]
        age=(NOW.date()-last.date.date()).days
        if age>4 or age<0:raise ValueError(f"Última rueda antigua: {age} días")
        atr=float(last.atr);price=float(last.close)
        if not math.isfinite(atr) or atr<=0 or price<=0:raise ValueError("ATR/precio inválido")
        rsi=float(last.rsi14) if pd.notna(last.rsi14) else None
        mom60=float(last.mom60) if pd.notna(last.mom60) else 0
        rv=float(last.rv) if pd.notna(last.rv) else 0
        riskpercent=100*atr/price
        signal=bool(last["reversion_rsi14"])
        trend=bool(last.caution_bull)
        # Same frozen RSI35 criterion, no tuning after results.
        entry=price # reference CLOSE, next-day OPEN required for actual paper sizing
        est_buy=entry*(1+SLIP)
        paid=est_buy*(1+CHARGES)
        stop=est_buy-1.2*atr
        target=est_buy+3.5*atr
        riskunit=paid-stop*(1-CHARGES-SLIP)
        rewardunit=target*(1-CHARGES-SLIP)-paid
        rr=round(rewardunit/riskunit,3) if riskunit>0 else None
        affordable={}
        for capital in (50000,100000):
            units=math.floor(min(capital*RISK/riskunit,capital*EXPOSURE/paid)) if riskunit>0 and paid>0 else 0
            affordable[str(capital)]=max(0,int(units))
        # More robust technical quality score, not trained or normalized to expected returns.
        quality=((25 if trend else 0)+(25 if signal else 0)+
            (15 if rsi is not None and 35<=rsi<=65 else 0)+
            (15 if mom60>0 else 0)+
            (10 if rv>=1.0 else 0)+(10 if riskpercent<6 else 0))
        candidate.update({
            "estado":"SEÑAL_RSI35_PAPEL" if signal and rr is not None and rr>=2 else "OBSERVAR_SIN_ORDEN",
            "fecha_historico":str(last.date.date()),"ruedas":len(x),"puntaje_tecnico":quality,
            "rsi14":round(rsi,2) if rsi is not None else None,
            "momentum_60d_pct":round(mom60*100,2),"volumen_relativo":round(rv,2),
            "atr_pct":round(riskpercent,2),"en_tendencia_larga":trend,
            "rr_neto_referencia":rr,
            "entrada_teorica_basada_en_cierre":round(entry,3),
            "stop_teorico":round(stop,3),"objetivo_teorico":round(target,3),
            "unidades_referencia":affordable,
            "observacion":"RSI35: señal al CIERRE; solo simular entrada al precio de APERTURA de la próxima rueda validada. Puntas y liquidez no verificadas."
        })
        if signal and (rr is None or rr<2):candidate["estado"]="RECHAZAR_RIESGO_RETORNO"
        if signal and max(affordable.values())==0:candidate["estado"]="RECHAZAR_TAMAÑO_MINIMO"
        return candidate
    except Exception as e:
        return {**candidate,"estado":"HISTORICO_NO_UTILIZABLE","puntaje_tecnico":None,"motivo":str(e)[:170]}
def main():
    file=ROOT/"discovery"/"snapshot.json"
    if not file.exists():raise RuntimeError("No existe snapshot de paneles")
    snap=json.loads(file.read_text(encoding="utf-8"))
    if snap.get("errors"):
        print("ADVERTENCIA: paneles incompletos",snap["errors"])
    raw=snap.get("snapshot",[])
    if not raw:raise RuntimeError("Sin símbolos del panel")
    groups={name:[float(x.get("turnover_indicative") or 0) for x in raw if x["class"]==name] for name in ("accion","cedear","bono","on")}
    peer={name:max(vals) if vals else 1 for name,vals in groups.items()}
    screen=[one_asset(row,peer) for row in raw]
    for row in screen:
        flags=row["control"]
        valid=not ("poco_monto" in flags or "posible_especie" in flags or "variacion_extrema" in flags)
        row["apto_para_segunda_etapa"]=valid and row["tipo"] in ("accion","cedear")
        row["etapa_2"]="PENDIENTE_DE_HISTORICO" if row["apto_para_segunda_etapa"] else "NO_APLICA"
    screen.sort(key=lambda x:(x["tipo"],-x["puntaje_preseleccion"]))
    write_csv(OUT/"todos_los_instrumentos_preseleccion.csv",screen)
    top={g:[r for r in screen if r["tipo"]==g][:30] for g in groups}
    technical=[]
    # Cover EVERY historical download, not just most liquid. Unknown symbols excluded.
    source_symbols={r["simbolo"]:r for r in screen if r["tipo"] in ("accion","cedear")
                    and not "posible_especie" in r["control"]}
    checked={}
    for f in sorted(ROOT.glob("*_ohlcv.csv")):
        sym=f.stem.replace("_ohlcv","")
        if sym in source_symbols:
            row=tech(dict(source_symbols[sym]))
            if row:checked[sym]=row
    technical=sorted(checked.values(),key=lambda r:(
        0 if r.get("estado")=="SEÑAL_RSI35_PAPEL" else 1,
        -(r.get("puntaje_tecnico") or 0),
        -r["puntaje_preseleccion"]))
    write_csv(OUT/"acciones_cedears_analisis_tecnico.csv",technical)
    studies={g:top[g][:20] for g in ("bono","on")}
    candidates=[r for r in technical if r.get("estado")=="SEÑAL_RSI35_PAPEL"]
    signalable=[r for r in candidates if max(r["unidades_referencia"].values())>0]
    report={
        "scanned_at":snap.get("scanned_at"),"ranked_at":NOW.isoformat(),
        "panels_complete":not bool(snap.get("errors")),
        "all_quoted_count":len(screen),
        "breakdown":{g:sum(r["tipo"]==g for r in screen) for g in groups},
        "stock_cedear_screened":sum(r["tipo"] in ("accion","cedear") for r in screen),
        "daily_historic_validated":sum(r.get("puntaje_tecnico") is not None for r in technical),
        "technical_filled":len(technical),
        "rsi35_signal_watchlist":len(candidates),
        "candidates_reference_with_units":len(signalable),
        "top_equity_by_screen":top["accion"][:10],
        "top_cedear_by_screen":top["cedear"][:10],
        "top_by_technical_quality":technical[:12],
        "bond_liquidity_research_only":studies["bono"],
        "on_liquidity_research_only":studies["on"],
        "cost_assumptions":"0.50% broker +0.05% market rights, IVA 21%, slip 0.1% each side, all illustrative",
        "never_live":True,
        "restrictions":[
            "Panel turnover by settlement currency is unverified; cross-currency amounts are NOT comparable.",
            "Top screen lists are NOT investment recommendations; daily change and turnover do not predict gains.",
            "Daily technical RSI14/RSI35 signals only after completed session, and entry must be next session OPEN; displayed stop/target from previous CLOSE are NOT executable.",
            "Bonds and ONs ranked for REVIEW ONLY (no TIR, coupon schedule, amortization, spread or effective currency).",
            "A symbol without a verified >=400-session OHLCV is not eligible for trading recommendations.",
            "A capital allocation cannot be completed without a chosen portfolio amount and real brokerage fees.",
            "No automatic real orders or intraday live notifications."
        ]}
    (OUT/"ranking_actual.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print("RANKING_BYMA "+json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},ensure_ascii=False,default=str))
    print("TOP_TECNICOS "+json.dumps([{"s":r["simbolo"],"estado":r.get("estado"),"score":r.get("puntaje_tecnico"),"rsi":r.get("rsi14"),"rr":r.get("rr_neto_referencia")} for r in technical[:10]],ensure_ascii=False))
    print("SEÑALES_RSI35 "+json.dumps([{"s":r["simbolo"],"rr":r.get("rr_neto_referencia")} for r in signalable],ensure_ascii=False))
if __name__=="__main__":main()
