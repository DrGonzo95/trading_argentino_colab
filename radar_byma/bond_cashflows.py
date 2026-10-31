#!/usr/bin/env python3
"""Contractual Argentine sovereign bond cashflows, public-source OBSERVATION ONLY.

No current yield or total-return backtest is produced without same-currency
dated clean/dirty price, settlement, accrued interest and verified cash payments.
Source contract timetable may differ from actual execution/credit events.
"""
import csv,json,re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

OUT=Path("resultados/bonos")
OUT.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
KNOWN={"AL30":"https://finarg.ar/bonos/al30",
       "GD30":"https://finarg.ar/bonos/gd30",
       "GD35":"https://finarg.ar/bonos/gd35"}
def numeric(s):
    s=str(s).strip().replace("\u00a0","").replace(" ","")
    if not s:return None
    if "," in s: s=s.replace(".","").replace(",",".")
    try:return float(s)
    except ValueError:return None
def fetch(symbol,url,session):
    page=session.get(url,timeout=25);page.raise_for_status()
    soup=BeautifulSoup(page.text,"html.parser")
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    if symbol.lower() not in (title+" "+soup.get_text(" ",strip=True)[:500]).lower():
        raise ValueError("Identidad del instrumento no confirmada")
    all_tables=soup.select("table")
    rows=[]
    for table in all_tables:
        thead=table.find("tr")
        if not thead:continue
        head=" ".join(th.get_text(" ",strip=True).lower() for th in thead.find_all(["th","td"]))
        if not ("fecha" in head and "interés" in head and "capital" in head and "residual" in head):continue
        for tr in table.select("tr"):
            cells=[td.get_text(" ",strip=True) for td in tr.find_all(["td","th"])]
            if len(cells)<5:continue
            try:
                date=datetime.strptime(cells[0],"%d/%m/%Y").date()
                interest,capital,total,residual=map(numeric,cells[1:5])
                if any(x is None for x in (interest,capital,total,residual)):continue
                if min(interest,capital,total,residual)<0:raise ValueError("Flujos negativos")
                if abs(total-interest-capital)>0.011:raise ValueError("Flujo total no coincide")
                rows.append({"ticker":symbol,"fecha_contractual":str(date),
                             "interes_usd_por_vno_100":interest,
                             "amortizacion_usd_por_vno_100":capital,
                             "total_usd_por_vno_100":total,
                             "capital_residual_usd_por_vno_100":residual,
                             "estatus":"CRONOGRAMA_CONTRACTUAL_NO_COBRO_CONFIRMADO",
                             "fuente":url})
            except ValueError:
                continue
        if rows:break
    if not rows:raise ValueError("Tabla de flujos con validación numérica no encontrada")
    rows.sort(key=lambda r:r["fecha_contractual"])
    if len({r["fecha_contractual"] for r in rows})!=len(rows):raise ValueError("Duplicados de fecha")
    # Forward-only future schedule at source reference date, not full life cashflows.
    if len(rows)<2:raise ValueError("Cronograma insuficiente")
    previous=None
    for row in rows:
        residual=row["capital_residual_usd_por_vno_100"]
        if previous is not None and abs(previous-row["amortizacion_usd_por_vno_100"]-residual)>0.02:
            raise ValueError("Residual y amortización no se concilian")
        previous=residual
    return rows
def main():
    states={};cash=[]
    ses=requests.Session();ses.headers.update({"User-Agent":"Mozilla/5.0 (educational research; no orders)","Accept":"text/html"})
    for ticker,url in KNOWN.items():
        try:
            rows=fetch(ticker,url,ses)
            cash.extend(rows)
            states[ticker]={"estado":"FLUJOS_CONTRACTUALES_VALIDOS","cuotas_futuras":len(rows),
                    "proximo_pago_contractual":rows[0]["fecha_contractual"],
                    "total_flujos_usd_por_vno_100":round(sum(r["total_usd_por_vno_100"] for r in rows),5),
                    "ultima_amortizacion":rows[-1]["fecha_contractual"],"fuente":url}
        except Exception as e:
            states[ticker]={"estado":"SIN_FLUJOS_VERIFICADOS","motivo":type(e).__name__+": "+str(e)[:180],"fuente":url}
    for ticker in ("AL29","AL35","AE38","AL41","GD29","GD38","GD41","GD46","TX28","TX31"):
        states[ticker]={"estado":"SIN_FLUJOS_VERIFICADOS","motivo":"Sin contrato y cronograma validado en el integrador"}
    if cash:
        with (OUT/"flujos_contractuales_al30_gd30_gd35.csv").open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(cash[0]))
            writer.writeheader();writer.writerows(cash)
    payload={"consultado":NOW.isoformat(),"fuentes":states,
        "status":"OBSERVACION_SIN_TIR",
        "flujos_validos":sum(v["estado"]=="FLUJOS_CONTRACTUALES_VALIDOS" for v in states.values()),
        "limitaciones":[
            "Son pagos por VNO100 y moneda USD, no flujos en pesos ni comprobantes de cobro.",
            "FinArg presenta flujos futuros desde su fecha documental de corte, no flujo histórico completo para backtest.",
            "Sin precio comparable en USD de la especie y fecha de liquidación, NO calcular TIR.",
            "Acreditación real, riesgo crediticio, impuestos y diferenciales de cotización no verificados.",
            "Bonos CER requieren inflación/indexación y reglas de cálculo independientes." ]}
    (OUT/"estado_bonos.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print("BONO_FLOWS "+json.dumps({"estados":states,"flujos":len(cash)},ensure_ascii=False))
if __name__=="__main__":main()
