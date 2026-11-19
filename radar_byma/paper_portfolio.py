#!/usr/bin/env python3
"""USD paper portfolio: next completed daily-close model, no broker orders.
The engine does not assert real exchange fills. Every virtual fill uses two
independently matching closing-price sources and explicit simulated costs.
"""
import json
import math
from datetime import datetime, timezone, date
from pathlib import Path
import requests
from underlying_cedears import independent_close, get_hist, indicators

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"docs/data/underlying_radar.json"
LEDGER=ROOT/"docs/data/paper_portfolio.json"
FEE=0.001
SLIPPAGE=0.001
MAX_DAYS=5

def blank():
    return {"schema":2,"currency":"USD","initial_cash":1000.0,
            "cash":1000.0,"positions":[],"closed":[],"events":[],
            "processed_report_at":None,"pending":[],"updated_at":None,
            "status":"USD_DAILY_CLOSE_PAPER_ONLY_NO_BROKER"}

def eligible(a):
    m=a.get("metrics") or {}
    return (a.get("quality_state")=="HISTORICO_VALIDO_PRELIMINAR"
        and a.get("bars_ohlcv",0)>=220
        and a.get("currency")=="USD"
        and a.get("independent_match") is True
        and a.get("research_state")=="VIGILANCIA_TECNICA_SUBYACENTE_NO_EJECUTABLE"
        and m.get("breakout_at_daily_close") is True
        and m.get("trend_confirmed") is True
        and (m.get("rvol20") or 0)>=1
        and (m.get("atr14_wilder") or 0)>0)

def confirmed_close(session,symbol):
    """Only a completed US session, with same-day Yahoo/Stooq closes within 1%.
    No fill if quote providers disagree, missing or have partial-day data.
    """
    bars,src=get_hist(session,symbol)
    last=bars[-1]
    independent=independent_close(session,symbol,last["date"])
    if not independent or abs(independent["close"]/last["close"]-1)>.01:
        raise ValueError("INDEPENDENT_CLOSE_NOT_MATCHED")
    return last,{"yahoo":src["url"],"stooq":independent["source"]}

def event(ledger,kind,symbol,day,price,qty,why,**extra):
    eid=f"{kind}:{symbol}:{day}"
    if any(e["id"]==eid for e in ledger["events"]):
        return
    ledger["events"].append({"id":eid,"type":kind,"symbol":symbol,
        "session_date":day,"price":round(price,4),"quantity":qty,
        "reason":why,"execution":"MODELLED_DAILY_CLOSE_NOT_REAL_FILL",**extra})

def process(report,ledger,session=None):
    stamp=report.get("generated_at")
    if not stamp or (ledger.get("processed_report_at") and stamp<=ledger["processed_report_at"]):
        return ledger
    if session is None: session=requests.Session()
    assets={a.get("underlying"):a for a in report.get("assets",[]) if a.get("underlying")}
    # Only existing positions and earlier pending signals are eligible to fill.
    # New signals are armed at the END, so never backfill the triggering day.
    for pos in list(ledger["positions"]):
        sym=pos["symbol"]
        try: bar,sources=confirmed_close(session,sym)
        except (requests.RequestException,ValueError,KeyError,TypeError): continue
        if bar["date"]<=pos["entry_date"] or bar["date"]<=pos.get("last_checked_date",""):
            continue
        pos["last_checked_date"]=bar["date"]
        pos["sessions_held"]=pos.get("sessions_held",0)+1
        close=bar["close"]
        reason=("STOP_DAILY_CLOSE" if close<=pos["stop"] else
                "TARGET_DAILY_CLOSE" if close>=pos["target"] else
                "TIME_EXIT_5_SESSIONS" if pos["sessions_held"]>=MAX_DAYS else None)
        if reason:
            sell=close*(1-SLIPPAGE)
            proceeds=pos["quantity"]*sell*(1-FEE)
            pnl=proceeds-pos["total_entry_cost"]
            ledger["cash"]=round(ledger["cash"]+proceeds,4)
            pos.update({"exit_date":bar["date"],"exit_price":round(sell,4),
                "exit_reason":reason,"net_pnl_usd":round(pnl,4),
                "exit_sources":sources})
            ledger["positions"].remove(pos)
            ledger["closed"].append(pos)
            event(ledger,"SELL",sym,bar["date"],sell,pos["quantity"],reason,
                net_pnl_usd=round(pnl,4),entry_price=pos["entry_price"],
                stop=pos["stop"],target=pos["target"],sources=sources)
    still=[]
    for sig in ledger.get("pending",[]):
        sym=sig["symbol"]
        if any(p["symbol"]==sym for p in ledger["positions"]):
            continue
        try: bar,sources=confirmed_close(session,sym)
        except (requests.RequestException,ValueError,KeyError,TypeError):
            still.append(sig);continue
        if bar["date"]<=sig["signal_close_date"]:
            still.append(sig);continue
        # Only act on the NEXT completed session, never a stale signal.
        from datetime import date as dtdate
        age=(dtdate.fromisoformat(bar["date"])-dtdate.fromisoformat(sig["signal_close_date"])).days
        if age>4:continue
        # Confirm continued strength, avoiding chasing a >1 ATR gap.
        if bar["close"]<sig["signal_close"] or bar["close"]>sig["signal_close"]+sig["atr"]:
            continue
        entry=bar["close"]*(1+SLIPPAGE)
        stop=round(entry-1.5*sig["atr"],4)
        target=round(entry+3.5*sig["atr"],4)
        if stop<=0:continue
        # 2:1 net after simulated 10bps fees and 10bps slippage each side.
        risk_unit=entry-stop+entry*FEE+stop*FEE
        reward_unit=target-entry-target*FEE-entry*FEE
        if reward_unit/risk_unit<2:continue
        equity=ledger["cash"]+sum(p["quantity"]*p["entry_price"] for p in ledger["positions"])
        qty=min(math.floor(equity*.02/risk_unit),
                math.floor(equity*.4/(entry*(1+FEE))),
                math.floor(ledger["cash"]/(entry*(1+FEE))))
        if qty<1:continue
        cost=qty*entry*(1+FEE)
        ledger["cash"]=round(ledger["cash"]-cost,4)
        pos={"symbol":sym,"currency":"USD","quantity":qty,
            "entry_date":bar["date"],"entry_price":round(entry,4),
            "total_entry_cost":round(cost,4),"stop":stop,"target":target,
            "sessions_held":0,"last_checked_date":bar["date"],
            "entry_sources":sources,"reason":"PREVIOUS_DAY_VERIFIED_BREAKOUT_NEXT_CLOSE_CONFIRMED",
            "execution":"MODELLED_DAILY_CLOSE_NOT_REAL_FILL"}
        ledger["positions"].append(pos)
        event(ledger,"BUY",sym,bar["date"],entry,qty,pos["reason"],
              stop=stop,target=target,estimated_entry_cost=round(cost,4),
              sources=sources)
    # Re-arm fresh signals; preserve still-pending ones for other tickers.
    armed={s["symbol"]:s for s in still}
    for a in report.get("assets",[]):
        if not eligible(a):continue
        m=a["metrics"];sym=a["underlying"]
        if sym in armed or any(p["symbol"]==sym for p in ledger["positions"]):
            continue
        armed[sym]={"symbol":sym,"cedear":a["cedear"],
            "signal_close_date":m["close_date"],"signal_close":m["last_close"],
            "atr":m["atr14_wilder"],"state":"WAIT_NEXT_COMPLETED_SESSION"}
    ledger["pending"]=list(armed.values())
    ledger["processed_report_at"]=stamp
    ledger["updated_at"]=datetime.now(timezone.utc).isoformat()
    ledger["status"]="USD_DAILY_CLOSE_PAPER_ONLY_NO_BROKER"
    return ledger

def main():
    if not REPORT.exists():raise SystemExit("No radar report")
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    ledger=json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else blank()
    ledger=process(report,ledger)
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    LEDGER.write_text(json.dumps(ledger,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"report":ledger["processed_report_at"],
        "pending":len(ledger["pending"]),"open":len(ledger["positions"]),
        "closed":len(ledger["closed"]),"events":len(ledger["events"]),
        "cash":ledger["cash"]}))

if __name__=="__main__":main()
