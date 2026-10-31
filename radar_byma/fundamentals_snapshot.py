#!/usr/bin/env python3
"""Read secondary PUBLIC BCBA fundamentals for research, no paywall/keys.
Does not invent ratios, and never substitutes secondary numbers for CNV filings.
Only numeric cells explicitly labeled by publisher are accepted.
"""
import csv,json,re,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from events_public import ALIASES

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
OUT=Path("resultados/fundamentales");OUT.mkdir(parents=True,exist_ok=True)
SNAPSHOT=Path("resultados/discovery/snapshot.json")
SOURCE="https://stockanalysis.com/quote/bcba/{symbol}/statistics/"
META={"PE Ratio":"pe_ratio","PB Ratio":"pb_ratio","EV / EBITDA":"ev_ebitda",
      "Debt / Equity":"deuda_patrimonio","Debt / EBITDA":"deuda_ebitda",
      "Return on Equity (ROE)":"roe_pct","Return on Assets (ROA)":"roa_pct",
      "Return on Invested Capital (ROIC)":"roic_pct",
      "Current Ratio":"liquidez_corriente",
      "Revenue Growth":"crecimiento_ingresos_pct",
      "Net Income Growth":"crecimiento_resultados_pct",
      "Market Cap":"capitalizacion_publicada"}
FIELDS=set(META.values())
def parse(s):
    val=str(s).replace(",","").replace("%","").strip()
    if not val or val in ("-","n/a","N/A"):return None
    # No magnitudes with B/T; no unclear monetary currency.
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",val):return None
    x=float(val)
    return x if abs(x)<1e7 else None
def read_one(ticker,sess):
    url=SOURCE.format(symbol=ticker)
    resp=sess.get(url,timeout=16)
    resp.raise_for_status()
    soup=BeautifulSoup(resp.text,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    # Verification of *local* stock. Do not pick ADR or US equivalent by accident.
    normalized=title.upper()
    if f"BCBA:{ticker}" not in normalized and f"({ticker})" not in normalized:
        raise ValueError("La página no corresponde al símbolo BCBA")
    vals={}
    for tr in soup.select("tr"):
        texts=[v.get_text(" ",strip=True) for v in tr.find_all(["td","th"],recursive=False)]
        if len(texts)<2:continue
        label=texts[0].strip().replace("\u00a0"," ")
        field=META.get(label)
        if not field:continue
        parsed=parse(texts[1])
        if parsed is not None:vals[field]=parsed
    if len(vals)<3:
        # Some HTML tables are divs: fail closed rather than guess from page text.
        raise ValueError(f"Métricas etiquetadas insuficientes: {len(vals)}")
    return {"ticker":ticker,"estado":"RATIOS_PÚBLICOS_SECUNDARIOS","fecha_consulta":NOW.isoformat(),
             "fuente":url,"periodo_reportado":"VARÍA_POR_MÉTRICA_CONSULTAR_ORIGINAL",
             "fuente_primaria_verificada":False,"datos_no_reconciliados_con_CNV":True,
             "advertencia":"No comparar bancos con industriales; datos históricos/TTM en distintos períodos.",
             **vals}
def main():
    s=json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    listed={r["symbol"] for r in s["snapshot"] if r.get("class")=="accion"}
    coverage=sorted(listed & ALIASES.keys())
    # All 46 mapped companies; no missing symbol silently represented as available.
    sess=requests.Session();sess.headers.update({"User-Agent":"Mozilla/5.0 (academic public market research; read only)","Accept":"text/html"})
    results=[]
    for sym in coverage:
        try:results.append(read_one(sym,sess))
        except Exception as exc:
            results.append({"ticker":sym,"estado":"SIN_RATIOS_AUTOMATICOS",
                            "motivo":type(exc).__name__+": "+str(exc)[:160],
                            "fecha_consulta":NOW.isoformat(),"fuente":SOURCE.format(symbol=sym)})
        time.sleep(.25)
    fields=list(dict.fromkeys(k for r in results for k in r))
    with (OUT/"ratios_por_emisora.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
    good=[r for r in results if r["estado"]=="RATIOS_PÚBLICOS_SECUNDARIOS"]
    report={"ejecutado":NOW.isoformat(),"acciones_panel":len(listed),
            "acciones_con_nombre_confirmado":len(coverage),"con_ratios":len(good),
            "sin_ratios":len(coverage)-len(good),
            "metodologia":"Solo extracción estricta de valores numéricos etiquetados en una fuente pública secundaria, sin estimar ausentes.",
            "datos":[{"ticker":r["ticker"],"pe_ratio":r.get("pe_ratio"),
                     "pb_ratio":r.get("pb_ratio"),"deuda_ebitda":r.get("deuda_ebitda"),
                     "roe_pct":r.get("roe_pct"),"fuente":r["fuente"]} for r in good],
            "requisitos_para_valoracion":["Confirmar los balances oficiales CNV, moneda e inflación homogénea",
             "Análisis sectorial bancos distinto de industriales",
             "Observar tendencias trimestrales y anuales, flujo de caja real",
             "No usar ratios aislados ni una cotización demorada como recomendación de compra"]}
    (OUT/"estado.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("RATIOS_FUNDAMENTALES "+json.dumps({k:v for k,v in report.items() if k!="datos"},ensure_ascii=False))
    print("RATIOS_MUESTRA "+json.dumps(report["datos"][:6],ensure_ascii=False))
if __name__=="__main__":main()
