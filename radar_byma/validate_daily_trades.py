#!/usr/bin/env python3
"""Radar diario de investigación/paper trading: fuentes públicas, nunca órdenes.
No afirma que haya visto todos los símbolos; no confunde marca de descarga con trade.
"""
import io, json, math, re, time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote
import requests
import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"docs/data/trade_validation.json"
TEXT=ROOT/"TRADES_EN_VIGILANCIA.md"
NOW=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
US_NOW=datetime.now(ZoneInfo("America/New_York"))
H_US={date(2026,11,26),date(2026,12,25)}
H_AR={date(2026,11,9),date(2026,11,10),date(2026,11,23),date(2026,12,8),date(2026,12,25),date(2026,12,31)}
# Lista inicial rotativa, no universo completo. No mezclar ADR en USD con papel local ARS.
US=[("AMD","NASDAQ"),("ATRO","NASDAQ"),("GIB","NYSE"),("NVDA","NASDAQ"),("MU","NASDAQ"),("AVGO","NASDAQ"),("MSFT","NASDAQ"),("COHR","NYSE"),("JPM","NYSE"),("XOM","NYSE")]
AR=[("GGAL","LIDER"),("PAMP","LIDER"),("YPFD","LIDER"),("EDN","LIDER"),("TXAR","GENERAL"),("BOLT","GENERAL"),("CEPU","LIDER"),("IRSA","LIDER"),("CGPA2","GENERAL"),("BMA","LIDER")]
session=requests.Session()
session.headers.update({"User-Agent":"Public equity research paper simulation contact via repository DrGonzo95/trading_argentino_colab","Accept":"text/csv,application/json,text/html"})
FEE_US=.0015; SLIP_US=.001; FEE_AR=(.005+.0005)*1.21;SLIP_AR=.001

def last_completed(market):
    z=US_NOW if market=="US" else NOW
    cutoff=16 if market=="US" else 18
    d=z.date() if z.hour>=cutoff+1 else z.date()-timedelta(days=1)
    holidays=H_US if market=="US" else H_AR
    while d.weekday()>=5 or d in holidays:d-=timedelta(days=1)
    return d

def yahoo(sym):
    end=int((NOW+timedelta(days=1)).timestamp())
    start=int((NOW-timedelta(days=1100)).timestamp())
    url="https://query1.finance.yahoo.com/v8/finance/chart/"+quote(sym)+"?"+urlencode({"period1":start,"period2":end,"interval":"1d"})
    res=session.get(url,timeout=20);res.raise_for_status()
    obj=res.json()["chart"]["result"][0]
    meta=obj["meta"]
    if meta.get("currency")!="USD" or meta.get("instrumentType")!="EQUITY":
        raise ValueError("Yahoo instrument/currency mismatch")
    if sym=="GIB" and "NY" not in str(meta.get("exchangeName","")).upper():
        # Exchange codes change; reject only if an exchange code is supplied and clearly alien.
        exchange=str(meta.get("exchangeName","")).upper()
        if exchange not in ("NYQ","NYSE","NEW YORK STOCK EXCHANGE"):raise ValueError("GIB exchange mismatch: "+exchange)
    quote_data=obj["indicators"]["quote"][0]
    zone=ZoneInfo("America/New_York")
    rows=[]
    for i,ts in enumerate(obj["timestamp"]):
        d=datetime.fromtimestamp(ts,timezone.utc).astimezone(zone).date()
        if d>last_completed("US"):continue
        try:
            vals=[quote_data[k][i] for k in ("open","high","low","close","volume")]
            if any(v is None for v in vals):continue
            rows.append([d,*vals])
        except (IndexError,KeyError):continue
    return pd.DataFrame(rows,columns=["date","open","high","low","close","volume"]),url

def stooq_last(sym):
    url="https://stooq.com/q/d/l/?"+urlencode({"s":sym.lower()+".us","i":"d","d1":(NOW.date()-timedelta(days=15)).strftime("%Y%m%d"),"d2":NOW.date().strftime("%Y%m%d")})
    try:
        r=session.get(url,timeout=17);r.raise_for_status()
        if not r.text.lstrip().startswith("Date,"):return None
        d=pd.read_csv(io.StringIO(r.text))
        if d.empty:return None
        last=d.iloc[-1]
        return {"session":str(pd.to_datetime(last["Date"]).date()),"close":float(last["Close"]),"source":url}
    except (requests.RequestException,ValueError,KeyError,IndexError,pd.errors.ParserError):
        return None

def parse_number(txt):
    s=str(txt).strip().replace("$","").replace("\u00a0","").replace(" ","")
    if not s or s in ("-","—"):return None
    if "," in s and "." in s:
        s=s.replace(",","")
    elif "," in s:s=s.replace(",",".")
    try:return float(s)
    except ValueError:return None

def iol(sym):
    url="https://iol.invertironline.com/Titulo/DatosHistoricos?"+urlencode({"mercado":"BCBA","simbolo":sym})
    r=session.get(url,timeout=20);r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    rows=[]
    for table in soup.select("table"):
        h=table.get_text(" ",strip=True).lower()
        if not all(k in h for k in ("apertura","cierre","volumen")):continue
        for tr in table.select("tr"):
            c=[x.get_text(" ",strip=True) for x in tr.find_all(["td","th"])]
            if len(c)<8:continue
            dt=pd.to_datetime(c[0],format="%m/%d/%Y",errors="coerce")
            if pd.isna(dt) or dt.date()>last_completed("AR"):continue
            v=[parse_number(c[j]) for j in (1,2,3,4,7)]
            if any(q is None for q in v):continue
            rows.append([dt.date(),*v])
    return pd.DataFrame(rows,columns=["date","open","high","low","close","volume"]),url

def check_bars(raw,market):
    if len(raw)<220:raise ValueError("OHLCV incompleto: "+str(len(raw))+"/220")
    d=raw.copy()
    d["date"]=pd.to_datetime(d["date"],errors="coerce")
    for key in ("open","high","low","close","volume"):d[key]=pd.to_numeric(d[key],errors="coerce")
    if d.isna().any().any():raise ValueError("Fechas o OHLCV nulos")
    if d.date.duplicated().any():raise ValueError("Ruedas duplicadas")
    d=d.sort_values("date").reset_index(drop=True)
    if (d[["open","high","low","close"]]<=0).any().any() or (d.volume<0).any():
        raise ValueError("OHLCV no positivos")
    if (d.high<d[["open","low","close"]].max(axis=1)-.001).any() or (d.low>d[["open","high","close"]].min(axis=1)+.001).any():
        raise ValueError("OHLC incoherente")
    if (d.date.diff().dt.days.dropna()>20).any():raise ValueError("Huecos de negociación >20 días")
    if (d.close.pct_change(fill_method=None).abs()>.45).any():
        raise ValueError("Movimiento >45%: comprobar split/corporate action")
    if (d.volume.tail(40)==0).sum()>4:raise ValueError("Demasiadas ruedas sin volumen")
    expected=last_completed(market)
    latest=d.date.iloc[-1].date()
    if latest<expected:raise ValueError("Ultima rueda desactualizada "+str(latest)+"; se espera "+str(expected))
    if latest>expected:raise ValueError("Rueda no cerrada")
    return d

def indicators(d):
    x=d.copy()
    for n in (20,50,200):x["ema"+str(n)]=x.close.ewm(span=n,adjust=False,min_periods=n).mean()
    diff=x.close.diff()
    u=diff.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    v=(-diff).clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    x["rsi14"]=100-100/(1+u/v.replace(0,float("nan")))
    e12=x.close.ewm(span=12,adjust=False,min_periods=12).mean()
    e26=x.close.ewm(span=26,adjust=False,min_periods=26).mean()
    x["macd"]=e12-e26
    x["macds"]=x.macd.ewm(span=9,adjust=False,min_periods=9).mean()
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift(1)).abs(),(x.low-x.close.shift(1)).abs()],axis=1).max(axis=1)
    x["atr14"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    x["rvol20"]=x.volume/x.volume.shift(1).rolling(20,min_periods=20).mean().replace(0,float("nan"))
    x["res20"]=x.high.shift(1).rolling(20,min_periods=20).max()
    essentials=["ema20","ema50","ema200","rsi14","macd","macds","atr14","rvol20","res20"]
    if any(not math.isfinite(float(x.iloc[-1][k])) for k in essentials):
        raise ValueError("Indicador incompleto o no numerico")
    return x

def plan(x,cost,eligible):
    a=x.iloc[-1]; b=x.iloc[-2]
    close=float(a.close); atr=float(a.atr14); high20=float(a.res20)
    trend=close>a.ema20>a.ema50>a.ema200 and a.ema50>b.ema50
    mom=52<=a.rsi14<=75 and a.macd>a.macds and a.macd>0
    near=close<high20 and high20/close-1<min(.045,1.5*atr/close)
    breakout=close>high20*1.001 and b.close<=b.res20*1.001
    if not (trend and mom):return "ESTUDIO_TECNICO_SIN_SETUP",None
    if near:return "PREALERTA_TECNICA_POR_CONFIRMAR",None
    if not (breakout and a.rvol20>=1.25):return "NO_ENTRADA_CONFIRMADA",None
    if not eligible:return "RUPTURA_SIN_COTIZACION_O_LIQUIDEZ_CONFIRMADA",None
    entry=round(close+.08*atr,2)
    stop=round(min(entry-1.2*atr,float(a.low)-.15*atr),2)
    tp1=round(entry+3.2*atr,2);tp2=round(entry+4.5*atr,2)
    paid=entry*(1+cost)
    risk=paid-stop*(1-cost)
    reward1=tp1*(1-cost)-paid
    reward2=tp2*(1-cost)-paid
    if risk<=0 or reward1/risk<2:return "R_R_NETO_MENOR_DE_DOS",None
    if (close-b.close)/b.close>.15:return "MOVIMIENTO_EXTENDIDO_EVITAR_PERSEGUIR",None
    return "SETUP_PAPEL_CONDICIONAL_NO_EJECUTABLE",{
        "entrada_limite_condicional":entry,"stop_teorico":stop,"tp1":tp1,"tp2":tp2,
        "rr_neta_tp1":round(reward1/risk,2),"rr_neta_tp2":round(reward2/risk,2),
        "riesgo_por_accion_con_costos":round(risk,4),
        "costo_por_accion_con_costos":round(paid,4),
        "costo_y_deslizamiento_por_lado_pct":round(cost*100,3),
        "riesgo_maximo_cartera_pct":.5,"exposicion_maxima_pct":20,
        "cantidad_formula":"floor(min(0.005*capital/riesgo_por_accion_con_costos,0.20*capital/costo_por_accion_con_costos))",
        "duracion_ruedas":"1-5","validez":"solo proxima rueda con precio/condiciones verificados",
        "ejecutado":False,"probabilidad":"NO_CALIBRADA",
        "advertencia":"SPREAD NO VERIFICADO - SIMULACION NO EJECUTABLE"}

def inspect(sym,exchange,market):
    out={"ticker":sym,"exchange":exchange,"mercado":market,
         "moneda":"USD" if market=="US" else "ARS","estado":"DATOS_NO_VALIDOS","probabilidad":"NO_CALIBRADA",
         "datos_precio":"Cierre diario; hora individual del último negocio NO verificada",
         "operacion_ficticia":None}
    try:
        raw,source=yahoo(sym) if market=="US" else iol(sym)
        out["fuente_ohlcv"]=source
        clean=check_bars(raw,market)
        x=indicators(clean)
        last=x.iloc[-1]
        out.update(ruedas_verificadas=len(x),primera=str(x.date.iloc[0].date()),ultima=str(x.date.iloc[-1].date()),
                   ultimo_cierre=round(float(last.close),4),maximo_ultima_rueda=round(float(last.high),4),
                   minimo_ultima_rueda=round(float(last.low),4),
                   ema20=round(float(last.ema20),3),ema50=round(float(last.ema50),3),ema200=round(float(last.ema200),3),
                   rsi14=round(float(last.rsi14),2),macd=round(float(last.macd),3),macd_signal=round(float(last.macds),3),
                   atr14=round(float(last.atr14),3),rvol20=round(float(last.rvol20),2),
                   resistencia20=round(float(last.res20),3))
        if market=="US":
            other=stooq_last(sym);out["segunda_fuente"]=other
            aligned=bool(other and other["session"]==out["ultima"] and abs(other["close"]/last.close-1)<.0075)
            liquidity=float((x.close*x.volume).tail(20).mean())>=5_000_000
            out["media_monto_20_usd"]=round(float((x.close*x.volume).tail(20).mean()),2)
        else:
            aligned=False;liquidity=False
            out["segunda_fuente"]="NO_VERIFICADA" # Requires same local ARS / settlement, not foreign ADR.
        out["dos_precios_concordantes"]=aligned
        out["liquidez_suficiente_para_simular"]=bool(liquidity)
        eligible=aligned and liquidity and market=="US"
        state,setup=plan(x, FEE_US+SLIP_US if market=="US" else FEE_AR+SLIP_AR, eligible)
        if market=="AR" and sym in ("BOLT","CGPA2"):
            state="ILÍQUIDA_SOLO_INVESTIGAR_SIN_PUNTAS";setup=None
        out["estado"]=state;out["operacion_ficticia"]=setup
    except Exception as exc:
        out["motivo_rechazo"]=type(exc).__name__+": "+str(exc)[:180]
    return out

def run():
    # All fixed candidates plus two rotated alternatives per market. Actual counts audited.
    order_us=US[:6]+[US[6+(NOW.timetuple().tm_yday%len(US[6:]))]]
    order_ar=AR[:6]+[AR[6+(NOW.timetuple().tm_yday%len(AR[6:]))]]
    checked=[]
    for market,items in (("US",order_us),("AR",order_ar)):
        for sym,exchange in items:
            checked.append(inspect(sym,exchange,market))
            time.sleep(.25)
    # Strictly suggestions, never market fills. Up to two candidate trades per week, not required.
    proposals=[r for r in checked if r["operacion_ficticia"]]
    proposals.sort(key=lambda r:(r.get("rvol20",0),r["operacion_ficticia"]["rr_neta_tp1"]),reverse=True)
    for r in proposals[2:]:
        r["estado"]="FUERA_DE_CUPO_SEMANAL_DE_INVESTIGACION";r["operacion_ficticia"]=None
    report={"fecha_revision":NOW.isoformat(),"fuentes":"Públicas sin claves: Yahoo chart, Stooq CSV, IOL historia",
            "universo":"Muestra dirigida/rotativa, no cobertura total",
            "objetivo":"0-2 trades de papel por semana, solamente si pasan todos los filtros",
            "controles":{"min_barras_setup":220,"barras_para_backtest":400,
                         "rr_neta_min":2,"riesgo_pct":.5,"exposicion_pct":20},
            "conteos":{m:{"especies_intentadas":sum(r["mercado"]==m for r in checked),
                           "con_ohlcv_220":sum(r["mercado"]==m and r.get("ruedas_verificadas",0)>=220 for r in checked),
                           "dos_precios_verificados":sum(r["mercado"]==m and r.get("dos_precios_concordantes") for r in checked),
                           "setups_ficticios":sum(r["mercado"]==m and r.get("operacion_ficticia") is not None for r in checked)} for m in ("US","AR")},
            "data":checked,
            "advertencias":["Datos EOD sin hora individual del último negocio; no son ejecución intradía",
                           "Sin garantía de spreads/profundidad, stop, retornos ni notificación oportuna",
                           "No se ejecutaron órdenes ni se registraron fills. No se calibró probabilidad." ]}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Trades en vigilancia · Nasdaq / NYSE / BYMA","",
           "> Investigación experimental. Datos demorados, operaciones NO ejecutadas.",
           "","Última ejecución: "+NOW.isoformat(),"",
           "| Símbolo | Bolsa | Cierre de rueda | Resistencia 20 | Ruedas | Validación | Trade ficticio |",
           "|---|---|---:|---:|---:|---|---|"]
    for r in checked:
        t=r.get("operacion_ficticia")
        detail=("Entrada {entrada_limite_condicional}, SL {stop_teorico}, TP1 {tp1}, TP2 {tp2}, R:R {rr_neta_tp1}".format(**t)) if t else "Ninguno"
        lines.append("| {ticker} | {exchange} | {ultimo_cierre} {moneda} ({ultima}) | {resistencia20} | {ruedas_verificadas} | {estado} | ".format(
            ticker=r["ticker"],exchange=r["exchange"],ultimo_cierre=r.get("ultimo_cierre","—"),moneda=r["moneda"],
            ultima=r.get("ultima","sin validar"),resistencia20=r.get("resistencia20","—"),ruedas_verificadas=r.get("ruedas_verificadas",0),
            estado=r["estado"])+detail+" |")
    lines.extend(["","**Fuente de auditoría:** [trade_validation.json](docs/data/trade_validation.json)",
                  "","La probabilidad de ganancia NO está calibrada. Propuestas solo hipotéticas y no ejecutables."])
    TEXT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"fecha":NOW.isoformat(),"conteos":report["conteos"],
                      "aprobados":[r["ticker"] for r in checked if r.get("operacion_ficticia")]},ensure_ascii=False))

if __name__=="__main__":run()
