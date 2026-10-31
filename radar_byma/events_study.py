#!/usr/bin/env python3
"""Dated public-event sentiment research + gated point-in-time event study.
Do not call a classifier trained; transparent small lexicon, low confidence.
Never treat headlines/social as broker buy instructions, or retroactively
assert a dated feed was known before the first time this radar observed it.
"""
import csv,hashlib,json,re,math
from datetime import datetime,date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

TZ=ZoneInfo("America/Argentina/Cordoba")
NOW=datetime.now(TZ)
DATA=Path("resultados")
EV=DATA/"eventos"
STATE=Path("radar_byma/state/event_history.json")
STATE.parent.mkdir(parents=True,exist_ok=True)
MIN_EVENTS=30
MIN_NAMES=8
MIN_SPAN_DAYS=60
COST_SIDE=.007655 # conservative 0.5% brokerage + 0.05% rights VAT, plus 0.1% slip
POS={"beneficio":1,"ganancia":1,"crecimiento":1,"record":1,"recorde":1,"aumento":.3,
     "recompra":.7,"dividendo":.4,"contrato":.4,"expansion":.3,
     "profit":1,"beat":1,"beats":1,"growth":1,"buyback":.7,"strong":.5}
NEG={"perdida":-1.4,"caida":-.5,"quiebra":-2,"incumplimiento":-2,"default":-2,
     "reestructuracion":-.6,"investigacion":-.6,"deuda":-.15,"demanda":-.6,
     "loss":-1.4,"fraud":-2,"miss":-1.1,"warning":-1,"bankruptcy":-2,"probe":-.8}
NEGATORS={"no","sin","not","never","ni"}
def load_csv(name):
    p=EV/name
    if not p.exists():return []
    with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def tokens(s):
    import unicodedata
    v=unicodedata.normalize("NFKD",str(s).lower())
    v="".join(c for c in v if not unicodedata.combining(c))
    return re.findall(r"[a-z]+",v)
def classify(title):
    t=tokens(title);matches=[];total=0
    for i,word in enumerate(t):
        v=POS.get(word,NEG.get(word,0))
        if not v:continue
        if any(x in NEGATORS for x in t[max(0,i-3):i]):v=-v
        total+=v;matches.append(word)
    label="positivo" if total>=1 else "negativo" if total<=-1 else "indeterminado"
    return round(total,2),label,matches
def jsonlist(raw):
    if isinstance(raw,list):return raw
    try:return json.loads(raw) if raw else []
    except (TypeError,ValueError):return []
def datestr(raw):
    try:return datetime.fromisoformat(str(raw)).astimezone(TZ)
    except (ValueError,TypeError):return None
def gather():
    events=[]
    for row in load_csv("hechos_relevantes_cnv.csv"):
        # Each identity must have come from issuer-name mapping, not a raw ticker substring.
        for ticker in jsonlist(row.get("tickers")):
            events.append({"ticker":ticker,"published":row.get("fecha_publicacion"),
                           "title":row.get("titulo",""),"url":row.get("url_documento"),
                           "source":"CNV_OFICIAL","topic":row.get("temas"),"confidence":"documental"})
    for row in load_csv("noticias_titulares.csv"):
        events.append({"ticker":row.get("ticker"),"published":row.get("fecha_publicacion"),
                       "title":row.get("titulo",""),"url":row.get("url_noticia"),
                       "source":"NEWS_HEADLINE","topic":row.get("temas"),"confidence":"headline_only"})
    for row in load_csv("redes_no_verificadas.csv"):
        for ticker in jsonlist(row.get("tickers")):
            events.append({"ticker":ticker,"published":row.get("fecha_publicacion"),
                           "title":row.get("titulo",""),"url":row.get("url"),
                           "source":"SOCIAL_PUBLIC","topic":[],"confidence":"rumour_unverified"})
    return [r for r in events if r["ticker"] and r["published"] and r["title"]]
def load_history():
    if not STATE.exists():return {"version":1,"events":{}}
    o=json.loads(STATE.read_text(encoding="utf-8"))
    if o.get("version")!=1:raise ValueError("event history format changed")
    return o
def build_history():
    hist=load_history()
    updates=0
    for event in gather():
        pub=datestr(event["published"])
        if pub is None or pub>NOW:continue
        url=event.get("url") or ""
        key=hashlib.sha256((event["ticker"]+"|"+event["source"]+"|"+url+"|"+event["title"]).encode()).hexdigest()
        if key not in hist["events"]:
            score,label,words=classify(event["title"])
            hist["events"][key]={**event,"sentiment_score_lexical":score,
                                  "sentiment":label,"palabras_coincidentes":words,
                                  "first_seen":NOW.isoformat(),
                                  "asof_usable":max(pub,NOW).isoformat(),
                                  "no_es_recomendacion":True}
            updates+=1
    # Keep until 3500 events, deterministic: oldest first_seen discarded.
    if len(hist["events"])>3500:
        old=sorted(hist["events"],key=lambda k:hist["events"][k]["first_seen"])
        for k in old[:len(old)-3500]:del hist["events"][k]
    if updates:STATE.write_text(json.dumps(hist,ensure_ascii=False,indent=2),encoding="utf-8")
    return hist,updates
def historical_prices():
    out={}
    files=list(DATA.glob("*_ohlcv.csv"))+list(Path("radar_byma/cache/ohlcv").glob("*.csv"))
    for f in files:
        ticker=f.stem.removesuffix("_ohlcv")
        if ticker in out:continue
        try:
            d=pd.read_csv(f,parse_dates=["date"]).sort_values("date").drop_duplicates("date")
            if len(d)<250:continue
            if (d[["open","high","low","close"]]<=0).any().any():continue
            out[ticker]=d
        except Exception:continue
    return out
def experiment(events,prices):
    # Locked ex-ante rule: only public issuer-name-linked official CNV or
    # company-name checked 3rd-party news, exclude social. Positive/negative
    # lexicon events; execute next session OPEN, exit 5 sessions later CLOSE.
    # The observed_on timestamp is necessary to prevent historic archive backfill.
    events=[e for e in events if e["source"] in ("CNV_OFICIAL","NEWS_HEADLINE")
            and e["sentiment"] in ("positivo","negativo")]
    possible=[]
    for e in events:
        if e["ticker"] not in prices:continue
        usable=datestr(e["asof_usable"])
        if not usable:continue
        d=prices[e["ticker"]]
        positions=d.index[d.date.dt.date>usable.date()].tolist()
        if len(positions)<6:continue
        entrypos=positions[0]; exitpos=positions[5]
        start=float(d.loc[entrypos,"open"]);end=float(d.loc[exitpos,"close"])
        if start<=0 or end<=0:continue
        pnl=(end*(1-COST_SIDE))/(start*(1+COST_SIDE))-1
        possible.append({"ticker":e["ticker"],"event_date":str(usable.date()),
            "entry":str(d.loc[entrypos,"date"].date()),"exit":str(d.loc[exitpos,"date"].date()),
            "sentiment":e["sentiment"],"source":e["source"],
            "return_net_pct":round(100*pnl,4),
            "event_url":e.get("url")})
    # Cluster independent events: one 5-day slot for each ticker.
    filtered=[];until={}
    for r in sorted(possible,key=lambda x:(x["entry"],x["ticker"])):
        if r["ticker"] in until and r["entry"]<=until[r["ticker"]]:continue
        filtered.append(r);until[r["ticker"]]=r["exit"]
    names={r["ticker"] for r in filtered}
    span=(max((date.fromisoformat(r["entry"]) for r in filtered),default=NOW.date())-
          min((date.fromisoformat(r["entry"]) for r in filtered),default=NOW.date())).days
    viable=(len(filtered)>=MIN_EVENTS and len(names)>=MIN_NAMES and span>=MIN_SPAN_DAYS
            and sum(r["sentiment"]=="positivo" for r in filtered)>=10
            and sum(r["sentiment"]=="negativo" for r in filtered)>=10)
    summary={"status":"EXPLORATORY_EVENT_STUDY_ONLY" if viable else "INSUFFICIENT_POINT_IN_TIME_HISTORY",
        "params_locked":"next trading day open to fifth later trading session close; fixed lexicon; fees+slip 0.7655% each side",
        "eligible_independent_events":len(filtered),"distinct_tickers":len(names),
        "span_days":span,"minimums":{"events":MIN_EVENTS,"tickers":MIN_NAMES,"calendar_span":MIN_SPAN_DAYS,
            "positive":10,"negative":10},
        "returns_withheld_due_to_low_sample":not viable,
        "note":"Even if gate met, this is hypothesis-generating, NOT independent validation; need walk-forward and market/sector baseline to make a claim."}
    if viable:
        for label in ("positivo","negativo"):
            subset=[x["return_net_pct"] for x in filtered if x["sentiment"]==label]
            summary[label]={"n":len(subset),"average_net_pct":round(sum(subset)/len(subset),3),
                            "win_rate":round(sum(x>0 for x in subset)/len(subset),3)}
    return summary,filtered
def main():
    hist,new=build_history()
    records=list(hist["events"].values())
    prices=historical_prices()
    study,trades=experiment(records,prices)
    with (EV/"observaciones_puntuales.csv").open("w",newline="",encoding="utf-8") as f:
        rows=[{"ticker":e["ticker"],"publicacion":e["published"],
               "primera_observacion":e["first_seen"],"fecha_utilizable":e["asof_usable"],
               "fuente":e["source"],"sentimiento_heuristico":e["sentiment"],
               "score":e["sentiment_score_lexical"],"url":e.get("url")}
              for e in records]
        if rows:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    report={"analizado":NOW.isoformat(),"events_stored":len(records),
      "newly_observed":new,"ticker_prices_available":len(prices),
      "lexicon_quality":"LOW, audit headlines manually; NOT a trained or validated sentiment model",
      "study":study,
      "prediction_status":"NOT_VALIDATED_DO_NOT_USE_FOR_TRADING",
      "no_future_data":"asof_usable=max(first observed by radar, publication date); never silently backfill"}
    (EV/"prediccion_estado.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if trades:
        with (EV/"event_study_dated_trades.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(trades[0]));w.writeheader();w.writerows(trades)
    print("EVENT_STUDY "+json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
