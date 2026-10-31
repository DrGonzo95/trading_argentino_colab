#!/usr/bin/env python3
"""Broaden verified BYMA daily OHLCV coverage incrementally using public IOL pages.
Rotate across stocks, CEDEARs including lower-turnover instruments.
Use cached datasets as RESEARCH, never silently re-label as tradable if <400 bars,
without adjusted corporate actions, or without bid/ask and market-depth history.
"""
import ast,csv,json,os,re,time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
import pandas as pd,requests
from bs4 import BeautifulSoup

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
TODAY=NOW.date()
OUT=Path("resultados/expansion")
OUT.mkdir(parents=True,exist_ok=True)
CACHE=Path("radar_byma/cache/ohlcv")
CACHE.mkdir(parents=True,exist_ok=True)
PANELS=Path("resultados/discovery/snapshot.json")
BASE=Path("resultados")
PER_BATCH=int(os.getenv("BATCH_SIZE","46"))
MAX_CACHE=210
MAX_AGE_DAYS=14
GROUPS=("accion","cedear")
BROKER_WARNING="Se desconoce spread y profundidad histórica. No implica orden ejecutable."
SESS=requests.Session()
SESS.headers.update({"User-Agent":"Mozilla/5.0 (academic BYMA research paper; no private keys)","Accept":"text/html"})
def parsefloat(s):
    t=str(s).replace("\xa0","").replace("$","").replace(" ","").strip()
    if not t:return None
    if "," in t and "." in t:t=t.replace(",","") # IOL historical uses English-formatted numbers.
    elif "," in t:t=t.replace(",",".")
    try:return float(t)
    except ValueError:return None
def fetch(symbol):
    url=f"https://iol.invertironline.com/Titulo/DatosHistoricos?mercado=BCBA&simbolo={quote(symbol)}"
    rsp=SESS.get(url,timeout=26);rsp.raise_for_status()
    soup=BeautifulSoup(rsp.text,"html.parser")
    rows=[]
    for table in soup.select("table"):
        hd=table.get_text(" ",strip=True).lower()
        if not all(s in hd for s in ("apertura","cierre","volumen")):continue
        for tr in table.select("tr"):
            cells=[t.get_text(" ",strip=True) for t in tr.find_all(["th","td"])]
            if len(cells)<8:continue
            dt=pd.to_datetime(cells[0],format="%m/%d/%Y",errors="coerce")
            if pd.isna(dt) or dt.date()>TODAY:continue
            a=[parsefloat(cells[k]) for k in (1,2,3,4,7)]
            if any(v is None for v in a):continue
            rows.append([dt,*a])
    if len(rows)<200:raise ValueError(f"Serie corta {len(rows)} (<200)")
    d=pd.DataFrame(rows,columns=["date","open","high","low","close","volume"])
    d=d.sort_values("date").drop_duplicates("date",keep="last").reset_index(drop=True)
    if (d[["open","high","low","close"]]<=0).any().any() or (d.volume<0).any():raise ValueError("OHLCV inválido")
    irregular=(d.high<d[["open","low","close"]].max(axis=1)) | (d.low>d[["open","high","close"]].min(axis=1))
    deviations=pd.concat([(d[["open","low","close"]].max(axis=1)-d.high).clip(lower=0),
                          (d.low-d[["open","high","close"]].min(axis=1)).clip(lower=0)],axis=1).max(axis=1)/d.close
    nbad=int(irregular.sum())
    if nbad>max(1,int(.02*len(d))) or deviations.max()>.01:
        raise ValueError(f"OHLC inconsistente {nbad}/{len(d)}, max {deviations.max():.2%}")
    d["high"]=d[["open","high","low","close"]].max(axis=1)
    d["low"]=d[["open","high","low","close"]].min(axis=1)
    if ((d.open/d.close.shift()-1).abs()>.35).any():raise ValueError("Salto >35%, revisar split o evento")
    if d.date.diff().dt.days.max()>21:raise ValueError("Fechas con separación >21 días")
    if len(d)<400:status="SOLO_ESTUDIO_MENOS_400"
    else:status="OHLCV_VERIFICADO_PRELIMINAR_SIN_CORPORATE_ACTIONS"
    return d,{"estado":status,"ruedas":len(d),"primera":str(d.date.iloc[0].date()),
              "ultima":str(d.date.iloc[-1].date()),"correcciones_ohlc":nbad,"fuente":url,
              "precaucion":BROKER_WARNING}
def choose():
    if not PANELS.exists():raise RuntimeError("Snapshot de paneles no disponible")
    snapshot=json.loads(PANELS.read_text(encoding="utf-8"))
    if snapshot.get("errors"):raise RuntimeError("Paneles incompletos")
    raw=snapshot["snapshot"]
    # The hourly runner already downloads 49 default instruments; use nightly
    # requests to broaden coverage, not repeat the same validated symbols.
    module=ast.parse(Path("radar_byma/runner.py").read_text(encoding="utf-8"))
    base=set()
    for node in module.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="TICKERS" for t in node.targets):
            base=set(ast.literal_eval(node.value));break
    fresh_cache=set()
    for f in CACHE.glob("*.csv"):
        try:
            d=pd.read_csv(f,usecols=["date"],parse_dates=["date"])
            if len(d)>=400 and (TODAY-d.date.max().date()).days<=MAX_AGE_DAYS:fresh_cache.add(f.stem)
        except (OSError,ValueError):pass
    pools={}
    for group in GROUPS:
        all_codes={r["symbol"] for r in raw if r["class"]==group}
        rows=[r for r in raw if r["class"]==group and r.get("last_delayed",0)>0
              and r["symbol"] not in base and r["symbol"] not in fresh_cache
              and not (r["symbol"].endswith(("D","C")) and r["symbol"][:-1] in all_codes)
              and re.fullmatch(r"[A-Z][A-Z0-9]{0,11}",r["symbol"])]
        high=sorted([r for r in rows if float(r.get("turnover_indicative") or 0)>=5e6],
                    key=lambda r:-float(r.get("turnover_indicative") or 0))
        low=sorted([r for r in rows if float(r.get("turnover_indicative") or 0)<5e6],
                   key=lambda r:-float(r.get("turnover_indicative") or 0))
        pools[group]={"alta":high[:150],"baja":low[:100]}
    # Fixed batch composition, rotates day by day, keeps low-turnover in discovery.
    selected=[]
    target=[("accion","alta",15),("accion","baja",8),
            ("cedear","alta",16),("cedear","baja",7)]
    for group,tier,count in target:
        pool=pools[group][tier]
        if not pool:continue
        start=(NOW.timetuple().tm_yday*count)%len(pool)
        for k in range(min(count,len(pool))):
            selected.append((pool[(start+k)%len(pool)]["symbol"],group,tier))
    return selected[:PER_BATCH],{g:{tier:len(pools[g][tier]) for tier in ("alta","baja")} for g in GROUPS}
def main():
    chosen,counts=choose()
    rows=[]
    for idx,(sym,group,tier) in enumerate(chosen):
        target=CACHE/f"{sym}.csv"
        state={"symbol":sym,"group":group,"actividad":tier}
        try:
            if target.exists():
                d=pd.read_csv(target,usecols=["date"],parse_dates=["date"])
                age=(TODAY-d.date.max().date()).days
                if age<=MAX_AGE_DAYS and len(d)>=400:
                    state.update(estado="EN_CACHE_RECIENTE",ruedas=len(d),ultima=str(d.date.max().date()))
                    rows.append(state)
                    continue
            hist,info=fetch(sym)
            target.write_text(hist.to_csv(index=False),encoding="utf-8")
            state.update(info)
        except Exception as e:state.update(estado="RECHAZADO",motivo=type(e).__name__+": "+str(e)[:160])
        rows.append(state)
        time.sleep(.25)
    # Keep cache bounded; preferentially preserve most recently refreshed (deterministic by mtime).
    files=sorted(CACHE.glob("*.csv"),key=lambda x:(x.stat().st_mtime,x.name),reverse=True)
    for stale in files[MAX_CACHE:]:stale.unlink()
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/"cobertura_lote.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    report={"ejecutado":NOW.isoformat(),"considerados":len(chosen),
            "por_tipo_actividad":counts,"n_cache":len(list(CACHE.glob("*.csv"))),
            "aceptados_nuevos":sum(r["estado"].startswith("OHLCV_VERIFICADO") for r in rows),
            "en_cache":sum(r["estado"]=="EN_CACHE_RECIENTE" for r in rows),
            "solo_estudio":sum(r["estado"]=="SOLO_ESTUDIO_MENOS_400" for r in rows),
            "rechazados":sum(r["estado"]=="RECHAZADO" for r in rows),
            "advertencia":"OHLCV no prueba ajuste de dividendos/splits, profundidad ni spread histórico; no se incluyen bonos en el backtest con esta herramienta"}
    (OUT/"estado.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("EXPANSION_HISTORICOS "+json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
