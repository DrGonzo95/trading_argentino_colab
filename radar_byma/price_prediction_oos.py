#!/usr/bin/env python3
"""Chronological OHLCV-only forward-price classifier for BYMA paper research.

Features observable at completed session T. Label references OPEN(T+1) to
CLOSE(T+5), with pessimistic costs. All training labels mature before
2026-03-25. One frozen logistic model, no search/tuning on holdout.
Out-of-sample portfolio implements position stops, integer qty and fees.
Never calls a backtest a validated predictive edge without prospective runs.
"""
import json,math,os,warnings
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score,accuracy_score,precision_score

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
OUT=Path("resultados/prediccion")
OUT.mkdir(parents=True,exist_ok=True)
CACHE=Path("radar_byma/cache/ohlcv")
CUTOFF=pd.Timestamp("2026-03-25")
FEE=.0055*1.21
SLIP=.001
BUY=1+FEE+SLIP
SELL=1-FEE-SLIP
CAPITAL=1_000_000.0
RISK=.005
CONCENTRATION=.2
MAX_OPEN=3
FEATURES=["momentum_5","momentum_20","momentum_60","rsi14",
          "atr_pct","vol20","volume_rel","ema50_dist",
          "ema200_dist","breakout20","gap_today","drawdown_20"]
PERIODS=5
MIN_TRAIN=800
MIN_TEST=250
MIN_TICKERS=7
P_THRESHOLD=.56
def load():
    result={};errors={}
    for file in sorted(CACHE.glob("*.csv")):
        symbol=file.stem
        if symbol in ("AL30","GD30","GD35"):continue
        try:
            d=pd.read_csv(file,parse_dates=["date"]).sort_values("date")
            if not all(k in d for k in ("date","open","high","low","close","volume")):
                raise ValueError("missing OHLCV")
            d=d.drop_duplicates("date",keep="last")
            if len(d)<400:raise ValueError("less than 400 bars")
            if d[["open","high","low","close"]].isna().any().any() or (d[["open","high","low","close"]]<=0).any().any():
                raise ValueError("bad OHLC")
            if d.date.dt.dayofweek.gt(4).any():raise ValueError("weekend dates present")
            d=d.set_index("date").sort_index()
            if (d.close.pct_change().abs()>.35).any():
                raise ValueError("unadjusted >35% gap/split risk")
            if ((d.high<d[["open","low","close"]].max(axis=1)) |
                (d.low>d[["open","high","close"]].min(axis=1))).mean()>.02:
                raise ValueError("inconsistent OHLC")
            result[symbol]=d
        except Exception as e:errors[symbol]=str(e)[:130]
    return result,errors
def features(x):
    close=x.close
    o=x.open; high=x.high;low=x.low
    ch=close.diff();u=ch.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    down=(-ch.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    ratio=u/(down.replace(0,np.nan))
    rsi=100-100/(1+ratio)
    prior=close.shift()
    true_range=pd.concat([(high-low).abs(),(high-prior).abs(),(low-prior).abs()],axis=1).max(axis=1)
    atr=true_range.rolling(14,min_periods=14).mean()
    e50=close.ewm(span=50,adjust=False).mean()
    e200=close.ewm(span=200,adjust=False).mean()
    z=pd.DataFrame(index=x.index)
    for n in (5,20,60):z[f"momentum_{n}"]=close.pct_change(n)
    z["rsi14"]=rsi/100
    z["atr_pct"]=atr/close
    z["atr"]=atr
    z["vol20"]=close.pct_change().rolling(20).std()
    z["volume_rel"]=x.volume/(x.volume.rolling(20).mean().replace(0,np.nan))
    z["ema50_dist"]=close/e50-1
    z["ema200_dist"]=close/e200-1
    z["breakout20"]=close/close.shift().rolling(20).max()-1
    z["gap_today"]=o/close.shift()-1
    z["drawdown_20"]=close/close.rolling(20).max()-1
    z["trend"]=close>e200
    return z
def build(prices):
    all_rows=[]
    precomputed={}
    for sym,d in prices.items():
        z=features(d)
        precomputed[sym]=(d,z)
        for i in range(205,len(d)-PERIODS):
            current=d.index[i]
            future=d.iloc[i+1:i+PERIODS+1]
            if len(future)<PERIODS or (future.index[-1]-current).days>15:continue
            close_date=future.index[-1]
            ent=float(future.open.iloc[0])
            end=float(future.close.iloc[-1])
            net=end*SELL/(ent*BUY)-1
            vals=z.iloc[i]
            xs=[vals[k] for k in FEATURES]
            if any(pd.isna(v) or not np.isfinite(v) for v in xs):continue
            if vals["atr"]<=0 or vals["volume_rel"]<=0:continue
            all_rows.append({
                "ticker":sym,"date":current,"outcome_end":close_date,"price_entry":ent,
                "label":int(net>0),"net_horizon":float(net),"atr":float(vals["atr"]),
                "momentum_20":float(vals["momentum_20"]),"trend":bool(vals["trend"]),
                **{k:float(vals[k]) for k in FEATURES}})
    df=pd.DataFrame(all_rows)
    return df,precomputed
def trade(d,decision,atr,capital,holding=PERIODS):
    available=d.index.searchsorted(decision,side="right")
    future=d.iloc[available:available+holding]
    if len(future)<holding:return None
    entry=float(future.open.iloc[0])
    stop=entry-1.5*atr
    target=entry+3.5*atr
    unitrisk=entry*BUY-stop*SELL
    if stop<=0 or unitrisk<=0:return None
    qty=max(0,math.floor(min(capital*RISK/unitrisk,capital*CONCENTRATION/(entry*BUY))))
    if qty<1:return None
    exitprice=float(future.close.iloc[-1]);reason="time"
    for item in future.itertuples():
        if item.open<=stop:exitprice=float(item.open);reason="stop_gap";break
        if item.open>=target:exitprice=float(item.open);reason="target_gap";break
        if item.low<=stop:exitprice=stop;reason="stop";break
        if item.high>=target:exitprice=target;reason="target";break
    return {"ticker":None,"entry":entry,"exit":exitprice,"qty":qty,
            "spent":qty*entry*BUY,"proceeds":qty*exitprice*SELL,
            "pnl":qty*(exitprice*SELL-entry*BUY),"reason":reason}
def simulate(df,prices,prob,method):
    dates=sorted(df.date.unique())
    dates=[d for d in dates if d>=CUTOFF]
    if not dates:return {"status":"NO_DATES"},[]
    # 5-session non-overlapping cohorts with frozen index start, same for both strategies.
    dates=dates[::PERIODS]
    equity=CAPITAL;history=[equity];trades=[]
    indexed=df.copy()
    indexed["probability"]=prob
    for dt in dates:
        choices=indexed[indexed.date==dt]
        if method=="ml":
            choices=choices[choices.probability>=P_THRESHOLD]
            choices=choices.sort_values(["probability","ticker"],ascending=[False,True])
        elif method=="momentum":
            choices=choices[(choices.trend==True)&(choices.momentum_20>0)]
            choices=choices.sort_values(["momentum_20","ticker"],ascending=[False,True])
        else:raise ValueError("bad benchmark")
        held=0;remaining=equity
        for row in choices.itertuples():
            if held>=MAX_OPEN:break
            trade_info=trade(prices[row.ticker],dt,row.atr,equity)
            if trade_info is None or trade_info["spent"]>remaining:continue
            trade_info["ticker"]=row.ticker
            trade_info["decision_date"]=str(dt.date())
            trade_info["score"]=round(row.probability,4) if method=="ml" else round(row.momentum_20,4)
            trades.append(trade_info)
            remaining-=trade_info["spent"]
            equity+=trade_info["pnl"]
            held+=1
        history.append(equity)
    peak=np.maximum.accumulate(history)
    maxdd=float(np.min(np.array(history)/peak-1))
    returns=[p["pnl"] for p in trades]
    firsthalf=[p for p in trades if p["decision_date"]<"2026-07-13"]
    secondhalf=[p for p in trades if p["decision_date"]>="2026-07-13"]
    def relative(rs):return round(100*sum(p["pnl"] for p in rs)/CAPITAL,4)
    stats={"initial_ars":CAPITAL,"final_ars":round(equity,2),
        "return_net_pct":round(100*(equity/CAPITAL-1),3),
        "max_drawdown_pct":round(100*maxdd,3),
        "trades":len(trades),"hit_ratio_pct":round(100*sum(x>0 for x in returns)/len(returns),2) if returns else None,
        "first_half_arithmetic_pct":relative(firsthalf),"second_half_arithmetic_pct":relative(secondhalf),
        "cost_assumption_each_side_pct":round(100*(FEE+SLIP),4),
        "position_risk_budget_pct":RISK*100,"max_asset_exposure_pct":CONCENTRATION*100,
        "liquidity_verified":False}
    return stats,trades
def run():
    result={"run_at":NOW.isoformat(),"method":"fixed pooled logistic regression on daily OHLCV, all feature values from date T",
      "source":"persisted public delayed ARS market prices, no normalized CCL or corporate action total returns",
      "cutoff":"2026-03-25","label":"NET price from next open to fifth future close",
      "hyperparams":"SimpleImputer(median)+StandardScaler+LogisticRegression(C=0.2,max_iter=400,random_state=42)",
      "expenses":"0.55% broker+rights times IVA21%, plus 0.10% slippage, EACH side",
      "status":"NOT_TESTED","live_signal_status":"DISABLED_NO_INDEPENDENT_PROSPECTIVE_VALIDATION"}
    prices,rejected=load()
    df,frames=build(prices)
    result.update({"universe":sorted(prices),"rejected":rejected,"samples":len(df)})
    if df.empty or len(prices)<MIN_TICKERS:
        result["status"]="TOO_FEW_INSTRUMENTS";return save(result)
    train=df[(df.outcome_end<CUTOFF)&(df.date<CUTOFF)]
    test=df[(df.date>=CUTOFF)&(df.outcome_end<=pd.Timestamp("2026-10-30"))]
    result.update({"train_events":len(train),"test_events":len(test),
      "train_tickers":train.ticker.nunique(),"test_tickers":test.ticker.nunique(),
      "train_latest_outcome":str(train.outcome_end.max()),"first_test_decision":str(test.date.min())})
    if len(train)<MIN_TRAIN or len(test)<MIN_TEST or test.ticker.nunique()<MIN_TICKERS:
        result["status"]="INSUFFICIENT_SEPARATED_SAMPLES";return save(result)
    model=Pipeline([("imputer",SimpleImputer(strategy="median")),
                     ("scale",StandardScaler()),
                     ("logreg",LogisticRegression(C=.2,max_iter=400,random_state=42))])
    model.fit(train[FEATURES],train.label)
    p=model.predict_proba(test[FEATURES])[:,1]
    baseline=float(test.label.mean())
    try:auc=float(roc_auc_score(test.label,p))
    except ValueError:auc=None
    result.update({
        "status":"OUT_OF_SAMPLE_RESEARCH_COMPLETED_NOT_PROSPECTIVELY_VALIDATED",
        "out_of_sample_auc":round(auc,4) if auc is not None else None,
        "oos_positive_net_move_frequency":round(baseline,4),
        "oos_predicted_positive_rate":round(float((p>=.5).mean()),4),
        "oos_accuracy_05":round(float(accuracy_score(test.label,p>=.5)),4),
        "oos_high_confidence_events":int((p>=P_THRESHOLD).sum()),
        "last_sampled_date":str(test.date.max().date())})
    simulated,trade_ml=simulate(test,prices,p,"ml")
    control,trade_control=simulate(test,prices,p,"momentum")
    result["model_paper"]=simulated
    result["control_momentum"]=control
    # Frozen credibility checks, not statistical proof.
    halves=simulated.get("first_half_arithmetic_pct",0)>0 and simulated.get("second_half_arithmetic_pct",0)>0
    robust=(simulated.get("trades",0)>=15 and simulated.get("return_net_pct",0)>0
            and simulated.get("return_net_pct",0)>control.get("return_net_pct",0)+1
            and halves and (auc or 0)>=.53
            and simulated.get("max_drawdown_pct",0)>-10)
    result["candidate_edge_on_holdout_heuristic"]=bool(robust)
    result["live_signal_status"]="DISABLED_REQUIRES_PROSPECTIVE_MONITORING"
    result["observations"]=[
      "OOS test was never used to fit parameters but researcher still inspected its results; cannot be reused as a fresh test.",
      "Correlated assets share macro/FX exposures and model may fit cross-sectional dependence.",
      "Stops are approximated using OHLC and may not fill in low-liquidity markets.",
      "Inflation/FX, dividends, corporate actions, bid/ask depth not fully accounted for.",
      "Even profitable historical performance does not assure future profitability.",
      "No real money orders; paper portfolio risk 0.5% per trade and 20% per asset."]
    with (OUT/"operaciones_modelo.csv").open("w",encoding="utf-8",newline="") as f:
        if trade_ml:
            import csv
            w=csv.DictWriter(f,fieldnames=list(trade_ml[0]));w.writeheader();w.writerows(trade_ml)
    with (OUT/"operaciones_control_momentum.csv").open("w",encoding="utf-8",newline="") as f:
        if trade_control:
            import csv
            w=csv.DictWriter(f,fieldnames=list(trade_control[0]));w.writeheader();w.writerows(trade_control)
    return save(result)
def save(result):
    (OUT/"resumen.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ML_PRICE_OOS "+json.dumps(result,ensure_ascii=False))
if __name__=="__main__":run()
