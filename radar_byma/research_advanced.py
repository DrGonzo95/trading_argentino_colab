#!/usr/bin/env python3
# Exploratory long-only research on locally traded ARS instruments.
# NOT brokerage advice, not real-time, no order execution.
import csv
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

DATA=Path("resultados")
OUT=Path("resultados/avanzado")
OUT.mkdir(parents=True,exist_ok=True)
FEE=0.003
SLIP=0.001
RISK=0.005
CONCENTRATION=0.20
MIN_RR=2.0
SPLIT=pd.Timestamp("2026-03-24")
BONDS={"AL29","AL30","AL35","AE38","AL41","GD29","GD30","GD35","GD38","GD41","GD46","TX28","TX31"}
STRATEGIES={
    "ruptura_20":{"stop":1.5,"target":4.0,"hold":20},
    "ruptura_55":{"stop":2.0,"target":5.6,"hold":30},
    "ruptura_10":{"stop":1.4,"target":3.9,"hold":18},
    "retroceso_rsi2":{"stop":1.2,"target":3.5,"hold":12},
    "retroceso_ema20":{"stop":1.5,"target":4.1,"hold":18},
    "reversion_bollinger":{"stop":1.5,"target":4.0,"hold":15},
    "recuperacion_rsi40":{"stop":1.3,"target":3.7,"hold":17},
    "cruce_macd":{"stop":1.5,"target":4.1,"hold":20},
    "momento_60":{"stop":1.8,"target":5.2,"hold":30},
    "momento_120":{"stop":2.0,"target":5.7,"hold":35},
    "reversion_rsi14":{"stop":1.2,"target":3.5,"hold":14},
    "ruptura_volumen":{"stop":1.6,"target":4.5,"hold":24}
}
def ewma(s,span,min_periods=None):
    return s.ewm(span=span,adjust=False,min_periods=min_periods or span).mean()
def features(d):
    x=d.copy().sort_values("date").drop_duplicates("date").reset_index(drop=True)
    x["date"]=pd.to_datetime(x.date)
    for n in (10,20,50,100,200):
        x[f"ema{n}"]=ewma(x.close,n)
    diff=x.close.diff()
    def rsi(n):
        up=diff.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        dn=(-diff).clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
        return 100-100/(1+up/dn.replace(0,np.nan))
    x["rsi14"]=rsi(14)
    x["rsi2"]=rsi(2)
    m=ewma(x.close,12)-ewma(x.close,26)
    x["macd"]=m
    x["macds"]=ewma(m,9)
    prev=x.close.shift(1)
    tr=pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()],axis=1).max(axis=1)
    x["atr"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    x["rv"]=x.volume/x.volume.shift(1).rolling(20).mean().replace(0,np.nan)
    for n in (10,20,55):
        x[f"prior_hi{n}"]=x.high.shift(1).rolling(n).max()
    x["boll_low"]=x.close.rolling(20).mean()-2*x.close.rolling(20).std()
    x["mom60"]=x.close/x.close.shift(60)-1
    x["mom120"]=x.close/x.close.shift(120)-1
    x["ret3"]=x.close/x.close.shift(3)-1
    x["bull"]=((x.close>x.ema200)&(x.ema50>x.ema200)&(x.ema50>x.ema50.shift(10))).fillna(False)
    x["caution_bull"]=(x.close>x.ema200).fillna(False)
    prior=x.shift(1)
    x["ruptura_20"]=x.bull&(x.close>x.prior_hi20)&(x.rv>=1)
    x["ruptura_55"]=x.bull&(x.close>x.prior_hi55)&(x.rv>=1)
    x["ruptura_10"]=x.bull&(x.close>x.prior_hi10)&(x.rv>=1.2)
    x["retroceso_rsi2"]=x.bull&(x.rsi2<20)&x.rsi14.between(35,75)
    x["retroceso_ema20"]=x.bull&(prior.close<prior.ema20)&(x.close>x.ema20)&(x.rv>.7)
    x["reversion_bollinger"]=x.caution_bull&(x.close<x.boll_low)&(x.rsi14<46)
    x["recuperacion_rsi40"]=x.bull&(prior.rsi14<40)&(x.rsi14>=40)
    x["cruce_macd"]=x.bull&(prior.macd<=prior.macds)&(x.macd>x.macds)
    x["momento_60"]=x.bull&(x.mom60>.10)&(x.close>x.prior_hi20)
    x["momento_120"]=x.caution_bull&(x.mom120>.25)&(x.close>x.prior_hi55)
    x["reversion_rsi14"]=x.caution_bull&(prior.rsi14<=35)&(x.rsi14>35)
    x["ruptura_volumen"]=x.bull&(x.close>x.prior_hi20)&(x.rv>1.5)&x.rsi14.between(53,80)
    return x.set_index("date",drop=False)
def load():
    files=sorted(DATA.glob("*_ohlcv.csv"))+sorted(Path("radar_byma/cache/ohlcv").glob("*.csv"))
    out={}
    reasons=[]
    for f in files:
        symbol=f.stem.removesuffix("_ohlcv")
        if symbol in out or symbol in BONDS:continue
        try:
            d=pd.read_csv(f,parse_dates=["date"])
            if len(d)<400:raise ValueError("Menos de 400 velas")
            if d.date.duplicated().any():raise ValueError("Fechas duplicadas")
            if (d[["open","high","low","close"]]<=0).any().any():raise ValueError("Precios <=0")
            out[symbol]=features(d)
        except Exception as e:reasons.append({"simbolo":symbol,"motivo":str(e)})
    return out,reasons
def simulate(data,name,start,finish,capital=100000,record=True):
    spec=STRATEGIES[name]
    days=sorted(set(t for d in data.values() for t in d.index if start<=t<=finish))
    cash=float(capital)
    holdings={}
    orders=[]
    curves=[]
    candidate_count=0
    rejection_count=0
    for day in days:
        day_values={s:d.loc[day] for s,d in data.items() if day in d.index}
        # Existing positions: stops before targets, so ambiguous bars are resolved conservatively.
        for sym,pos in list(holdings.items()):
            if sym not in day_values:continue
            bar=day_values[sym]
            entry_day=pos["open_day"]
            if day<entry_day:continue
            outcome=None;px=None
            if bar.open<=pos["stop"]:
                outcome="gap_stop";px=bar.open
            elif bar.open>=pos["target"]:
                outcome="gap_target";px=bar.open
            elif bar.low<=pos["stop"]:
                outcome="stop_or_both";px=pos["stop"]
            elif bar.high>=pos["target"]:
                outcome="take_profit";px=pos["target"]
            elif pos["bars_held"]>=spec["hold"]-1:
                outcome="time_exit";px=bar.close
            if outcome is not None:
                proceeds=float(px)*pos["n"]*(1-FEE-SLIP)
                cash+=proceeds
                pnl=proceeds-pos["spent"]
                orders.append({"estrategia":name,"ticker":sym,"compra":pos["entry_date"],"venta":str(day.date()),"cantidad":pos["n"],"entrada":round(pos["entry"],4),"stop":round(pos["stop"],4),"objetivo":round(pos["target"],4),"salida":round(float(px),4),"motivo":outcome,"beneficio_neto":round(pnl,2),"capital_inicial":capital})
                del holdings[sym]
            else:
                pos["bars_held"]+=1
        # Proposed entries: signal from previous bar, buy at next real open; no look-ahead.
        possibilities=[]
        for sym,d in data.items():
            if sym in holdings or day not in d.index:continue
            idx=d.index.get_loc(day)
            if not isinstance(idx,int) or idx<1:continue
            prev=d.iloc[idx-1]
            if prev.name>=day or prev.name<start-pd.Timedelta(days=14):continue
            if (prev.name>=finish):continue
            if bool(prev[name]) and np.isfinite(prev.atr) and prev.atr>0:
                candidate_count+=1
                ranking=float(prev.mom60) if np.isfinite(prev.mom60) else 0
                possibilities.append((ranking,sym,float(prev.atr),prev))
        possibilities.sort(reverse=True)
        mark_before=cash+sum(pos["n"]*float(day_values[sym].open) for sym,pos in holdings.items() if sym in day_values)
        for _,sym,atr,prev in possibilities:
            if len(holdings)>=5:break
            bar=day_values[sym]
            entry=float(bar.open)*(1+SLIP)
            stop=entry-spec["stop"]*atr
            target=entry+spec["target"]*atr
            if stop<=0:rejection_count+=1;continue
            entryunit=entry*(1+FEE)
            stop_net=stop*(1-FEE-SLIP)
            target_net=target*(1-FEE-SLIP)
            riskunit=entryunit-stop_net
            rewardunit=target_net-entryunit
            if not (riskunit>0 and rewardunit/riskunit>=MIN_RR):
                rejection_count+=1;continue
            n=min(int(math.floor(mark_before*RISK/riskunit)),
                  int(math.floor(mark_before*CONCENTRATION/entryunit)),
                  int(math.floor(cash/entryunit)))
            if n<=0:
                rejection_count+=1;continue
            spent=n*entryunit
            cash-=spent
            holdings[sym]={"n":n,"entry":entry,"stop":stop,"target":target,"spent":spent,"open_day":day,"entry_date":str(day.date()),"bars_held":0}
            # intraday entry at open: account for same-day gap-free stop or target touch.
            if bar.low<=stop or bar.high>=target:
                if bar.low<=stop:exit_price=stop;reason="stop_or_both_same_day"
                else:exit_price=target;reason="take_profit_same_day"
                proceeds=n*exit_price*(1-FEE-SLIP)
                cash+=proceeds
                orders.append({"estrategia":name,"ticker":sym,"compra":str(day.date()),"venta":str(day.date()),"cantidad":n,"entrada":round(entry,4),"stop":round(stop,4),"objetivo":round(target,4),"salida":round(exit_price,4),"motivo":reason,"beneficio_neto":round(proceeds-spent,2),"capital_inicial":capital})
                del holdings[sym]
        marked=cash+sum(pos["n"]*float(day_values[sym].close)*(1-FEE-SLIP) for sym,pos in holdings.items() if sym in day_values)
        curves.append({"fecha":str(day.date()),"capital":marked,"estrategia":name,"inicial":capital})
    if days:
        last=days[-1]
        for sym,pos in list(holdings.items()):
            d=data[sym]
            earlier=d.loc[d.index<=last]
            if earlier.empty:continue
            px=float(earlier.iloc[-1].close)
            proceeds=pos["n"]*px*(1-FEE-SLIP)
            cash+=proceeds
            orders.append({"estrategia":name,"ticker":sym,"compra":pos["entry_date"],"venta":str(last.date()),"cantidad":pos["n"],"entrada":round(pos["entry"],4),"stop":round(pos["stop"],4),"objetivo":round(pos["target"],4),"salida":round(px,4),"motivo":"fin_periodo","beneficio_neto":round(proceeds-pos["spent"],2),"capital_inicial":capital})
            del holdings[sym]
        curves[-1]["capital"]=cash
    equity=pd.Series([z["capital"] for z in curves],dtype=float)
    dd=equity.div(equity.cummax()).sub(1).min() if len(equity) else 0
    r=(cash/capital-1)*100
    wins=sum(x["beneficio_neto"]>0 for x in orders)
    return {"estrategia":name,"capital_inicial":capital,"desde":str(start.date()),"hasta":str(finish.date()),
            "capital_final":round(cash,2),"retorno_pct":round(r,3),"drawdown_max_pct":round(float(dd)*100,3),
            "operaciones":len(orders),"ganadoras":wins,"winrate_pct":round(wins/len(orders)*100,1) if orders else None,
            "señales_brutas":candidate_count,"rechazadas":rejection_count,
            "beneficio_promedio":round(sum(o["beneficio_neto"] for o in orders)/len(orders),2) if orders else None},orders,curves
def csvsave(name,rows):
    if not rows:return
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        fields=list(dict.fromkeys(y for z in rows for y in z))
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader();w.writerows(rows)
def main():
    data,rejected=load()
    if not data: raise RuntimeError("No hay históricos locales de 400 ruedas aceptados")
    # All strategies are pre-specified before test results are read, test is used once.
    begin=max(pd.Timestamp("2024-10-16"), min(d.index[0] for d in data.values()))
    cut=SPLIT
    finish=min(d.index[-1] for d in data.values())
    train=[];test=[];test_trades=[];curves=[]
    for name in STRATEGIES:
        summary,_,_=simulate(data,name,begin,cut,100000)
        train.append(summary)
    # Requirement at least 5 filled trades AND positive return AND loss/return sensible.
    eligible=[x for x in train if x["operaciones"]>=5 and x["retorno_pct"]>0 and x["drawdown_max_pct"]>-8]
    # Do not claim validated if there is no training sample meeting these constraints.
    eligible.sort(key=lambda x:(x["retorno_pct"]+x["drawdown_max_pct"], x["retorno_pct"]),reverse=True)
    selected=eligible[0]["estrategia"] if eligible else None
    # Only now run on untouched test window; display all models for audit, not to optimize selection.
    for name in STRATEGIES:
        summary,orders,equity=simulate(data,name,cut+pd.Timedelta(days=1),finish,100000)
        test.append(summary)
        test_trades.extend(orders)
        curves.extend(equity)
    scenario=[]
    if selected:
        for cap in (50000,100000):
            for phase,a,b in (("entrenamiento",begin,cut),("prueba",cut+pd.Timedelta(days=1),finish)):
                result,_,_=simulate(data,selected,a,b,cap)
                scenario.append({"fase":phase,**result})
    # Sensitivity is a POST-HOC robustness inspection, NOT fresh out-of-sample confirmation.
    # The RSI14 candidate was noticed after seeing the test. Never call it validated.
    global FEE,SLIP
    baseline_fee,baseline_slip=FEE,SLIP
    sensitivity=[]
    for label,fee,slip in (("base",.003,.001),("costo_alto",.005,.002),("costo_bajo",.0015,.001)):
        FEE,SLIP=fee,slip
        for cap in (50000,100000):
            for phase,a,b in (("entrenamiento",begin,cut),("prueba",cut+pd.Timedelta(days=1),finish)):
                result,_,_=simulate(data,"reversion_rsi14",a,b,cap)
                sensitivity.append({"escenario":label,"comision_por_lado":fee,"deslizamiento_por_lado":slip,"fase":phase,**result})
    FEE,SLIP=baseline_fee,baseline_slip
    csvsave("sensibilidad_RSI14.csv",sensitivity)
    csvsave("entrenamiento_12_modelos.csv",train)
    csvsave("prueba_12_modelos.csv",test)
    csvsave("trades_prueba.csv",test_trades)
    csvsave("equity_prueba.csv",curves)
    csvsave("modelo_elegido_carteras.csv",scenario)
    manifest={"modo":"paper_only","validez":"exploratorio_no_validado_comercialmente",
              "activos_incluidos":sorted(data),"activos_rechazados":rejected,
              "fecha_inicio":str(begin.date()),"corte_entrenamiento":str(cut.date()),"fecha_fin":str(finish.date()),
              "candidatos_entrenamiento":len(eligible),"modelo_preseleccionado":selected,
              "RSI14_posthoc":"Consistente en ambos periodos SOLO como observacion exploratoria; seleccionado despues de ver test. Exige prueba forward.",
              "seleccion_en_prueba":next((x for x in test if x["estrategia"]==selected),None),
              "advertencia":"Las doce estrategias y el umbral fueron fijados antes de observar el test. Backtest basado en barras diarias, sin CCL independiente, corporate actions completa ni profundidad de puntas. No garantiza rentabilidad ni es una orden."}
    (OUT/"resumen.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"resumen":manifest,"entrenamiento":train,"prueba":test},ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
