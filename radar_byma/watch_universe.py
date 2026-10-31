#!/usr/bin/env python3
"""BYMA multi-asset watch report. Only stock/CEDEAR paper-trading enabled elsewhere.
Bonds: price-level diagnostics ONLY; never cashflow/TIR or order guidance.
"""
import csv,json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from research_advanced import features

OUT=Path("resultados")
REPORT=OUT/"universo"
REPORT.mkdir(exist_ok=True)
STOCKS=["GGAL","YPFD","PAMP","CEPU","BMA","BBAR","BYMA","COME","ALUA","TXAR",
        "TGSU2","CRES","EDN","SUPV","VALO","LOMA","METR","TECO2","TGNO4","TRAN","IRSA","MIRG","HARG"]
CEDEARS=["AAPL","GOOGL","NVDA","SPY","QQQ","MSFT","AMZN","MELI","META","TSLA","KO","JPM","XOM"]
USD_BONDS=["AL29","AL30","AL35","AE38","AL41","GD29","GD30","GD35","GD38","GD41","GD46"]
CER_BONDS=["TX28","TX31"]
BONDS=USD_BONDS+CER_BONDS
ALL=STOCKS+CEDEARS+BONDS
now=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
def flag(status):
    if status=="SIN_SENAL": return "SIN_SEÑAL_CONFIRMADA_PAPEL"
    if status=="CANDIDATO_SOLO_PAPEL":return "OBSERVAR_Y_CONFIRMAR_PUNTAS"
    if status=="BONO_SOLO_SEGUIMIENTO_PRECIO":return "BONO_OBSERVACION_SIN_BACKTEST"
    return "DATOS_INSUFICIENTES_O_NO_VALIDOS"
def main():
    states={}
    status_file=OUT/"estado.csv"
    if status_file.exists():
        with status_file.open(encoding="utf-8-sig",newline="") as f:
            states={r["simbolo"]:r for r in csv.DictReader(f)}
    rows=[];bonds=[]
    for s in ALL:
        group="acción argentina" if s in STOCKS else "CEDEAR en ARS" if s in CEDEARS else ("bono soberano USD / especie ARS" if s in USD_BONDS else "bono CER / especie ARS")
        state=states.get(s,{})
        status=state.get("estado","SIN_DATOS")
        dfile=OUT/f"{s}_ohlcv.csv"
        row={"simbolo":s,"grupo":group,"estado_datos":status,
             "uso":"paper RSI14" if s in STOCKS+CEDEARS else "observación de precio sin PNL",
             "señal":flag(status),"fecha_ultima_rueda":state.get("ultima",""),
             "ruedas_validadas":int(state.get("velas",0) or 0),
             "reparaciones_ohlc":int(state.get("correcciones_ohlc",0) or 0)}
        if dfile.exists() and status in ("SIN_SENAL","CANDIDATO_SOLO_PAPEL","BONO_SOLO_SEGUIMIENTO_PRECIO"):
            try:
                d=pd.read_csv(dfile,parse_dates=["date"])
                last=d.iloc[-1]
                age=(now.date()-last.date.date()).days
                row["cierre_indicativo_ars"]=round(float(last.close),3)
                row["fecha_ultima_rueda"]=str(last.date.date())
                row["demora_dias_calendario"]=age
                if age>4 or age<0:row["señal"]="SERIE_DESACTUALIZADA"
                if s in BONDS:
                    # Prices may jump when coupons and amortizations are detached.
                    x=features(d)
                    one=x.iloc[-1]
                    row.update({"rsi14":round(float(one.rsi14),2),
                                "ema50":round(float(one.ema50),3),
                                "variacion_20_ruedas_precio_pct":round((float(one.close)/float(d.close.iloc[-21])-1)*100,3) if len(d)>20 else None,
                                "advertencia":"No contiene cupones, amortizaciones, TIR, duration ni moneda de liquidación confirmada. NO operar con este indicador."})
                    if age<=4:
                        row["señal"]="OBSERVACION_PRECIOS_SIN_ORDEN"
                    bonds.append(row.copy())
            except Exception as e:
                row["señal"]="ERROR_DERIVADOS"
                row["detalle"]=str(e)[:160]
        elif state.get("detalle"):
            row["detalle"]=state["detalle"]
        rows.append(row)
    counts={"universo":len(rows),"acciones":len(STOCKS),"cedears":len(CEDEARS),"bonos":len(BONDS),
            "series_validas":sum(r["ruedas_validadas"]>=400 and r["estado_datos"] in ("SIN_SENAL","CANDIDATO_SOLO_PAPEL","BONO_SOLO_SEGUIMIENTO_PRECIO") for r in rows),
            "bonos_observables":len(bonds),"acciones_cedears_validos":sum(r["uso"]=="paper RSI14" and r["estado_datos"] in ("SIN_SENAL","CANDIDATO_SOLO_PAPEL") for r in rows)}
    with (REPORT/"universo_completo.csv").open("w",newline="",encoding="utf-8") as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    with (REPORT/"bonos_observacion.csv").open("w",newline="",encoding="utf-8") as f:
        if bonds:
            fields=list(dict.fromkeys(k for row in bonds for k in row))
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(bonds)
    info={"fecha_revision":now.isoformat(),"tipos":counts,"bonos":bonds,"acciones_cedears":rows[:len(STOCKS+CEDEARS)],
          "restricciones":["El universo de 49 es una lista de seguimiento, no todas las especies de BYMA.",
          "Sin flujo de cupones/amortizaciones/TIR y sin libro de órdenes, no se dan órdenes de bonos.",
          "Series de IOL son diarias y diferidas, no precios en tiempo real.",
          "Los activos con históricos rechazados continúan en vigilancia pero sin señal operable."]}
    (REPORT/"reporte.json").write_text(json.dumps(info,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print("MULTI_ASSET_WATCH "+json.dumps({"tipos":counts,"bonos_observados":[r["simbolo"] for r in bonds],
                                          "rejected":[r["simbolo"] for r in rows if "ERROR" in r["estado_datos"] or r["estado_datos"].startswith("RECHAZADO")]},ensure_ascii=False))
if __name__=="__main__":main()
