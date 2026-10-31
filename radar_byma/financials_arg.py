#!/usr/bin/env python3
"""Argentine CNV/issuer financial statement coverage and VERY conservative
numerical extraction from issuer-owned HTML tables, if fully identified.
No generic regex over financial PDFs: accounting unit, period and consolidation
must be confirmed. Unsupported issuer stays MISSING_NUMERIC, not zero.
"""
import csv,json,re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
DEST=Path("resultados/fundamentales")
DEST.mkdir(parents=True,exist_ok=True)
DISC=Path("resultados/discovery/snapshot.json")
ISSUERS={
 "BYMA":{"url":"https://www.byma.com.ar/relacion-con-inversores/informacion-financiera",
         "name":"Bolsas y Mercados Argentinos","unit":"MILLONES_ARS_VALOR_HISTORICO"}
}
def num(t):
    s=re.sub(r"\s+","",str(t)).replace("$","").replace("%","")
    if not s or s in ("-","—"):return None
    neg=s.startswith("(") and s.endswith(")")
    s=s.strip("()")
    if "," in s:s=s.replace(".","").replace(",",".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+",s):s=s.replace(".","")
    try:return -float(s) if neg else float(s)
    except ValueError:return None
def extract_byma(html):
    soup=BeautifulSoup(html,"html.parser")
    tables=soup.select("table")
    rows=[]
    for table in tables:
        heads=" ".join(table.get_text(" ",strip=True).lower().split())
        if "ars millones" not in heads or "2t26" not in heads or "2t25" not in heads:continue
        tr=table.select("tr")
        table_head=tr[0].get_text(" ",strip=True) if tr else ""
        if "2T26" not in table_head.upper() or "2T25" not in table_head.upper():
            continue
        for row in tr[1:]:
            cells=[td.get_text(" ",strip=True) for td in row.find_all(["td","th"])]
            if len(cells)<3:continue
            label=cells[0].strip()
            a,b=num(cells[1]),num(cells[2])
            if a is None or b is None or len(label)<4:continue
            rows.append({"ticker":"BYMA","emisor":"Bolsas y Mercados Argentinos",
              "concepto_fuente":label,
              "valor_2t_2026_millones_ars_historicos":a,
              "valor_2t_2025_millones_ars_historicos":b,
              "variacion_nominal_interanual_pct":round((a/b-1)*100,3) if b>0 else None,
              "valor_real_interanual_pct":None,
              "moneda_escala":"ARS_MILLONES_HISTORICOS",
              "fuente":ISSUERS["BYMA"]["url"],
              "verificacion":"TABLA_CORPORATIVA_LABELED_COMPARABLE; inflación NO AJUSTADA"})
    return rows
def main():
    session=requests.Session();session.headers.update({"User-Agent":"Mozilla/5.0 (public issuer financial-report research)"})
    coverage={}
    if DISC.exists():
        snap=json.loads(DISC.read_text(encoding="utf-8"))
        for r in snap.get("snapshot",[]):
            if r.get("class")=="accion":
                coverage[r["symbol"]]={"estado":"SIN_BALANCE_NUMERICO_ESTANDARIZADO",
                    "fuente_requerida":"CNV EEFF por emisor con fecha cierre, publicación, norma, moneda, escala y consolidación"}
    rows=[]
    for symbol,issuer in ISSUERS.items():
        try:
            resp=session.get(issuer["url"],timeout=22);resp.raise_for_status()
            results=extract_byma(resp.text)
            if results:
                rows+=results
                coverage[symbol]={"estado":"CIFRAS_DE_TABLA_CORPORATIVA_HISTORICAS",
                      "n_renglones":len(results),"fuente":issuer["url"],
                      "advertencia":"Comparación nominal, no evolución real ajustada por inflación"}
            else:coverage[symbol]={"estado":"TABLA_NO_ESTRUCTURADA_O_CAMBIO_DE_FORMATO",
                       "fuente":issuer["url"]}
        except Exception as e:
            coverage[symbol]={"estado":"FUENTE_NO_ACCESIBLE",
                 "detalle":type(e).__name__+": "+str(e)[:120],"fuente":issuer["url"]}
    if rows:
        with (DEST/"arg_emisor_tabla.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    state={"fecha":NOW.isoformat(),"acciones_en_panel":len(coverage),
        "emisores_con_cifras_extraidas":sum(x["estado"]=="CIFRAS_DE_TABLA_CORPORATIVA_HISTORICAS" for x in coverage.values()),
        "filas_positivas":len(rows),"estado_por_ticker":coverage,
        "masivo_con_ratios":"NO: CNV EEFF argentinos no tienen una API numérica homogénea pública validada en este pipeline.",
        "restricciones":["Las comparaciones de BYMA en ARS históricos NO tienen corrección por inflación, no inferir crecimiento real.",
                         "Los balances bancarios requieren normas y ratios especializados.",
                         "No unir ARS históricos con cifras USD SEC ni CEDEAR ARS para P/E.",
                         "Sin fuente verificable, los datos faltantes quedan ausentes, no cero."]}
    (DEST/"arg_estado.json").write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding="utf-8")
    print("ARG_FINANCIALS "+json.dumps({k:v for k,v in state.items() if k!="estado_por_ticker"},ensure_ascii=False))
if __name__=="__main__":main()
