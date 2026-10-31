#!/usr/bin/env python3
"""Cauciones + RSI14: seguimiento forward solo en papel, con fuentes públicas.
No envía órdenes, no hace operaciones de caución y no solicita credenciales.
"""
import json, math, os, re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from research_advanced import features

ROOT=Path("radar_byma")
STATEFILE=ROOT/"data"/"forward_state.json"
OUT=Path("resultados")/"seguimiento"
OUT.mkdir(parents=True,exist_ok=True)
LOCAL=ZoneInfo("America/Argentina/Buenos_Aires")
NOW=datetime.now(LOCAL)
TODAY=pd.Timestamp(NOW.date())
PORTFOLIOS=(50000,100000)
FEE=.003
SLIP=.001
RISK=.005
MAX_EXPOSURE=.20
STOP_ATR=1.2
TARGET_ATR=3.5
MAX_HOLD=14
WATCH_START="2026-10-31"
QUOTE_URL="https://iol.invertironline.com/mercado/cotizaciones/argentina/cauciones"
IOL_MIN_CAPITAL=100000
# IOL indicative published charges: 0.15% monthly and market dues 0.045% per 90 days, plus 21% IVA.
# These are ONLY estimates; ALYC tier/custody/tax treatment and firm execution rates must be verified.
IOL_FEE_MONTHLY=.0015
IOL_DUES_90_DAYS=.00045
VAT=.21
def round2(x):return round(float(x),2)
def load_market():
    data={}
    issues={}
    for f in Path("resultados").glob("*_ohlcv.csv"):
        sym=f.stem.replace("_ohlcv","")
        try:
            d=pd.read_csv(f,parse_dates=["date"])
            if len(d)<400:raise ValueError("Series <400 ruedas")
            x=features(d)
            # Intraday price can be incomplete. Only include same-day bar if well after market closure.
            if NOW.hour<19 or NOW.weekday()>4:
                if NOW.weekday()>4:
                    limit=TODAY
                else:
                    limit=TODAY
            else:limit=TODAY+pd.Timedelta(days=1)
            x=x.loc[x.index<limit]
            if x.empty:raise ValueError("Sin ruedas cerradas")
            data[sym]=x
        except Exception as e:issues[sym]=str(e)
    return data,issues

def decode_rate(s):
    s=s.strip().replace("\xa0","")
    s=re.sub(r"[^\d,.-]","",s)
    return float(s.replace(".","").replace(",",".")) if s else float("nan")

def caucion_quotes():
    status={"fuente":QUOTE_URL,"caracter":"TASA_TOMADORA_RECIENTE_DE_PANEL_DIFERIDO; NO_ES_OFERTA_COLOCADORA_EJECUTABLE",
            "ejemplos_no_operables":[],"errores":[]}
    try:
        r=requests.get(QUOTE_URL,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"},timeout=25)
        r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser")
        raw=[]
        for table in soup.select("table"):
            for tr in table.select("tr"):
                td=[x.get_text(" ",strip=True) for x in tr.select("td")]
                if len(td)<7 or td[1].upper()!="PESOS":continue
                try:
                    days=int(td[0])
                    tna=decode_rate(td[5])
                    d=datetime.strptime(td[6],"%d/%m/%Y %H:%M:%S").replace(tzinfo=LOCAL)
                    if not(1<=days<=30 and .1<=tna<=200):continue
                    raw.append({"dias_calendario":days,"tna_pct":round2(tna),"fecha_pizarra":d.isoformat(),"momento":d})
                except (ValueError,IndexError,TypeError):pass
        if not raw:
            status["errores"].append("Sin tasas públicas legibles o todas inválidas; no generar recomendación")
            status["estado"]="SIN_TASA_VERIFICADA"
            return status
        # Reject data older than 4 calendar days, e.g. after a long weekend; no stale alerts.
        raw=[x for x in raw if timedelta(0)<=NOW-x["momento"]<=timedelta(days=4)]
        if not raw:
            status["estado"]="TASA_VENCIDA"
            status["errores"].append("Últimas cotizaciones demasiado antiguas")
            return status
        bestbyday={}
        for q in raw:
            # Never pick highest last trade as "best offer": choose latest timestamp for each tenor.
            day=q["dias_calendario"]
            if day not in bestbyday or q["momento"]>bestbyday[day]["momento"]:
                bestbyday[day]=q
        for day in sorted(bestbyday)[:12]:
            q=bestbyday[day]
            row={k:v for k,v in q.items() if k!="momento"}
            for capital in PORTFOLIOS:
                interest=capital*(q["tna_pct"]/100)*day/365
                fee=capital*(IOL_FEE_MONTHLY/30)*day*(1+VAT)
                dues=capital*(IOL_DUES_90_DAYS/90)*day*(1+VAT)
                net=interest-fee-dues
                row[f"neto_ejemplo_{capital}"]=round2(net) if capital>=IOL_MIN_CAPITAL else None
                row[f"elegible_iol_{capital}"]=capital>=IOL_MIN_CAPITAL
                row[f"interes_bruto_{capital}"]=round2(interest)
            status["ejemplos_no_operables"].append(row)
        status["estado"]="REFERENCIAS_CALCULADAS_NO_EJECUTABLES"
        status["comision_iol_mensual_hipotetica_pct"]=.15
        status["derecho_mercado_90d_hipotetico_pct"]=.045
        status["iva_aplicado_escenario_pct"]=21
        status["minimo_publicado_iol_ars"]=IOL_MIN_CAPITAL
    except Exception as e:
        status["estado"]="ERROR_FUENTE"
        status["errores"].append(str(e)[:250])
    return status

def fresh_state(data):
    latest=max((d.index[-1] for d in data.values()),default=None)
    last=str(latest.date()) if latest is not None else WATCH_START
    return {"schema":1,"created":NOW.isoformat(),"model":"RSI14_experimental_posthoc",
            "last_processed":last,"portfolios":{str(cap):{"cash":float(cap),"positions":{},"closed":[],"signals":[]} for cap in PORTFOLIOS}}

def load_state(data):
    if STATEFILE.exists():
        s=json.loads(STATEFILE.read_text(encoding="utf-8"))
        if s.get("schema")!=1:raise ValueError("Version de state no compatible")
        return s,False
    return fresh_state(data),True

def process_one_day(day,data,state):
    for cap in PORTFOLIOS:
        p=state["portfolios"][str(cap)]
        holdings=p["positions"]
        for symbol,pos in list(holdings.items()):
            d=data.get(symbol)
            if d is None or day not in d.index:continue
            bar=d.loc[day]
            count=pos["bars"]
            why=None
            if bar.open<=pos["stop"]:px=bar.open;why="gap_stop"
            elif bar.open>=pos["target"]:px=bar.open;why="gap_target"
            elif bar.low<=pos["stop"]:px=pos["stop"];why="stop_or_both_conservative"
            elif bar.high>=pos["target"]:px=pos["target"];why="take_profit"
            elif count>=MAX_HOLD-1:px=bar.close;why="time_exit"
            if why:
                returned=pos["shares"]*float(px)*(1-FEE-SLIP)
                p["cash"]+=returned
                p["closed"].append({"ticker":symbol,"entrada":pos["date"],"salida":str(day.date()),
                    "precio_entrada":pos["entry"],"precio_salida":round2(px),"cantidad":pos["shares"],
                    "resultado_neto":round2(returned-pos["spent"]),"motivo":why,
                    "tipo":"hipotetico_calculado_despues_del_cierre"})
                del holdings[symbol]
            else:pos["bars"]=count+1
        for symbol,d in data.items():
            if symbol in holdings or day not in d.index:continue
            idx=d.index.get_loc(day)
            if not isinstance(idx,int) or idx<1:continue
            prev=d.iloc[idx-1]
            if not bool(prev["reversion_rsi14"]):continue
            bar=d.loc[day]
            atr=float(prev.atr)
            if not (np.isfinite(atr) and atr>0):continue
            entry=float(bar.open)*(1+SLIP)
            stop=entry-STOP_ATR*atr
            target=entry+TARGET_ATR*atr
            costunit=entry*(1+FEE)
            lossunit=costunit-stop*(1-FEE-SLIP)
            gainunit=target*(1-FEE-SLIP)-costunit
            if stop<=0 or lossunit<=0 or gainunit/lossunit<2:continue
            equity=p["cash"]+sum(x["shares"]*x["entry"] for x in holdings.values())
            count=min(math.floor(equity*RISK/lossunit),math.floor(equity*MAX_EXPOSURE/costunit),math.floor(p["cash"]/costunit))
            if count<1:continue
            spent=count*costunit
            p["cash"]-=spent
            holdings[symbol]={"date":str(day.date()),"entry":round2(entry),"stop":round2(stop),
                   "target":round2(target),"shares":count,"spent":spent,"bars":0}
            p["signals"].append({"ticker":symbol,"señal_al_cierre":str(prev.date.date()),
                   "compra_hipotetica":str(day.date()),"cantidad":count,"precio_modelado":round2(entry),
                   "riesgo_unitario":round2(lossunit),"rr_neto_estimado":round(gainunit/lossunit,2)})
            # No same-day high/low "fill" here; after-close model with conservative next-day exits.
    state["last_processed"]=str(day.date())

def last_signals(data):
    out=[]
    for symbol,d in data.items():
        bar=d.iloc[-1]
        if bool(bar["reversion_rsi14"]) and bar.name>=TODAY-pd.Timedelta(days=7):
            out.append({"ticker":symbol,"fecha_cierre":str(bar.date.date()),"rsi14":round2(bar.rsi14),
                        "ema200":round2(bar.ema200),"cierre":round2(bar.close),
                        "estado":"SEÑAL_EN_OBSERVACIÓN; NO COMPRAR A PRECIO HISTÓRICO"})
    return out

def main():
    data,errors=load_market()
    state,initial=load_state(data)
    updated=initial
    days=sorted({stamp for d in data.values() for stamp in d.index if stamp>pd.Timestamp(state["last_processed"])})
    for day in days:
        process_one_day(day,data,state)
        updated=True
    # Persist ONLY when the seed or new fully closed bars create a state change.
    if updated:
        STATEFILE.parent.mkdir(exist_ok=True,parents=True)
        STATEFILE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    statuses=[]
    for cap in PORTFOLIOS:
        p=state["portfolios"][str(cap)]
        statuses.append({"capital":cap,"saldo_papel":round2(p["cash"]),"abiertas":p["positions"],
          "cerradas":len(p["closed"]),"resultado_neto_realizado":round2(sum(t["resultado_neto"] for t in p["closed"])),
          "ultimos_cierres":p["closed"][-5:]})
    report={"modo":"SOLO_SIMULACIÓN","fecha_consulta":NOW.isoformat(),"ultima_rueda_procesada":state["last_processed"],
           "estado_persistido":updated,"datos_validos":sorted(data),"errores":errors,
           "rsi14":{"estado":"EXPERIMENTAL_NO_VALIDADA","señales_actuales":last_signals(data),"carteras":statuses},
           "cauciones":caucion_quotes()}
    (OUT/"estado_actual.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"procesado":len(days),"fecha":NOW.isoformat(),"n_especies":len(data),
         "ultima_rueda":state["last_processed"],"estado_persistido":updated,
         "senales":report["rsi14"]["señales_actuales"],"carteras":statuses,
         "cauciones":report["cauciones"]},ensure_ascii=False,default=str))
if __name__=="__main__":main()
