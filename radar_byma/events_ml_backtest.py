#!/usr/bin/env python3
"""Time-ordered ML news signal experiment, no claim of proven predictability.

Never trains on unobserved future publication data. Fits only if a sufficiently
long archive of independently matured event outcomes exists.
All model thresholds/hyperparameters fixed ex ante.
If not enough history, return NOT_TESTABLE, NOT A PROFITABLE MODEL.
"""
import csv,json,math
from datetime import date,datetime
from pathlib import Path
from statistics import mean
OUT=Path("resultados/eventos")
INPUT=OUT/"event_study_dated_trades.csv"
REPORT=OUT/"modelo_predictivo_estado.json"
MIN_N=160
MIN_TICKERS=16
MIN_SPAN=240
TRAIN_PCT=.65
def finish(d):
    REPORT.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
    print("EVENT_ML "+json.dumps(d,ensure_ascii=False))
def main():
    state={"status":"INSUFFICIENT_FROZEN_POINT_IN_TIME_HISTORY",
           "model":"LogisticRegression fixed C=0.2, only source/sentiment/ticker-agnostic text signals",
           "minimum_events":MIN_N,"minimum_tickers":MIN_TICKERS,"minimum_calendar_span":MIN_SPAN,
           "decision_rule":"Long-only when ex ante probability > 0.60; next session open, exit 5 sessions later, costs in PNL.",
           "no_future_leakage":"Training events and their full five-session outcomes must end before any scored test entry date",
           "live_use":"FORBIDDEN",
           "warning":"A time split and positive PNL alone do not prove a tradable edge; independent prospective validation required."}
    if not INPUT.exists():return finish(state)
    with INPUT.open(encoding="utf-8",newline="") as f:rows=list(csv.DictReader(f))
    clean=[]
    for r in rows:
        try:
            entry=date.fromisoformat(r["entry"]);exit=date.fromisoformat(r["exit"])
            pnl=float(r["return_net_pct"])
            if math.isfinite(pnl) and exit>=entry:
                clean.append({**r,"entry_date":entry,"exit_date":exit,"pnl":pnl})
        except (ValueError,KeyError):pass
    clean.sort(key=lambda x:(x["entry_date"],x["ticker"]))
    n=len(clean)
    tickers=len({r["ticker"] for r in clean})
    span=(clean[-1]["entry_date"]-clean[0]["entry_date"]).days if clean else 0
    state.update(n_matured=n,n_instruments=tickers,span_days=span)
    if n<MIN_N or tickers<MIN_TICKERS or span<MIN_SPAN:return finish(state)
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError:return finish({**state,"status":"SKLEARN_NOT_INSTALLED"})
    # Predeclared fixed categorical features; no historical future trends.
    def encode(row):
        return [1. if row["sentiment"]=="positivo" else 0.,
                1. if row["source"]=="CNV_OFICIAL" else 0.]
    cut=int(n*TRAIN_PCT)
    if cut<70 or n-cut<35:return finish(state)
    # Purge train events whose five-session outcome would not be known
    # on the FIRST test entry date.
    first_test=clean[cut]["entry_date"]
    train=[r for r in clean[:cut] if r["exit_date"]<first_test]
    test=clean[cut:]
    state.update(train_n=len(train),test_n=len(test),train_ends_before_test=all(x["exit_date"]<first_test for x in train))
    if len(train)<70 or len(test)<35:return finish(state)
    X=np.array([encode(r) for r in train],dtype=float)
    y=np.array([int(r["pnl"]>0) for r in train],dtype=int)
    if len(set(y))<2:return finish({**state,"status":"TRAIN_ONLY_ONE_CLASS"})
    model=LogisticRegression(C=.2,max_iter=250,class_weight="balanced",random_state=0)
    model.fit(X,y)
    prob=model.predict_proba(np.array([encode(r) for r in test],dtype=float))[:,1]
    picked=[r["pnl"] for r,p in zip(test,prob) if p>.6]
    untouched=[r["pnl"] for r in test]
    state.update(status="EXPLORATORY_OUT_OF_SAMPLE_COMPUTED_NOT_VALIDATED",
      test_signal_count=len(picked),
      test_signal_mean_net_pct=round(mean(picked),4) if picked else None,
      test_signal_hit_pct=round(100*sum(x>0 for x in picked)/len(picked),2) if picked else None,
      test_unfiltered_all_events_mean_net_pct=round(mean(untouched),4),
      test_signal_freq_pct=round(100*len(picked)/len(test),2),
      test_first_entry=str(first_test),test_last_entry=str(test[-1]["entry_date"]),
      limitations=["Only two binary textual features; sentiment is a crude lexicon, not semantic comprehension.",
                   "No causal comparison with same-day peers, no factor hedge, FX variation in ARS CEDEAR.",
                   "No actual bid/ask history, trades depend on 0.7655%/side estimated friction.",
                   "Source history stored only from first-seen and may omit delisted/bankrupt companies.",
                   "Do NOT turn on automated buys from this exploratory trial."])
    finish(state)
if __name__=="__main__":main()
