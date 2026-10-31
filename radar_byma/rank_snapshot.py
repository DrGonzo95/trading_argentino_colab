#!/usr/bin/env python3
"""Fast 1,883+ symbol panel screen. Descriptive only; no trading or yield signals."""
import csv,json,math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE=Path("resultados/discovery/snapshot.json")
OUT=Path("resultados/discovery")
def dump(path,items):
    if not items:return
    with path.open("w",encoding="utf-8",newline="") as fp:
        cols=list(dict.fromkeys(k for row in items for k in row))
        w=csv.DictWriter(fp,fieldnames=cols);w.writeheader();w.writerows(items)
def main():
    if not SOURCE.exists():raise RuntimeError("Sin paneles disponibles")
    j=json.loads(SOURCE.read_text(encoding="utf-8"))
    rows=j.get("snapshot",[])
    if not rows:raise RuntimeError("Escaneo vacío")
    grouped={g:[] for g in ("accion","cedear","bono","on")}
    for r in rows:
        if r.get("class") in grouped:grouped[r["class"]].append(r)
    allrank=[];top={};low_activity_top={}
    for group,values in grouped.items():
        # Prioritize liquidity over daily change. Amount units may not be comparable
        # across settlement currencies and species, so never use cross-class scores.
        peak=max((float(r.get("turnover_indicative") or 0) for r in values),default=1)
        codes={r["symbol"] for r in values}
        enriched=[]
        for r in values:
            amount=max(0,float(r.get("turnover_indicative") or 0))
            variation=r.get("variation_pct")
            v=float(variation) if variation is not None else None
            candidate=r["symbol"]
            fx=candidate.endswith(("D","C")) and candidate[:-1] in codes
            flags=[]
            if fx: flags.append("POSIBLE_ESPECIE_MONEDA_DUPLICADA")
            if amount<5_000_000: flags.append("BAJO_MONTO_INDICATIVO")
            if v is not None and abs(v)>10: flags.append("CAMBIO_EXTREMO_REVISION")
            price=float(r.get("last_delayed") or 0)
            if price<=0: flags.append("SIN_PRECIO")
            quality=round(70*math.log1p(amount)/max(1,math.log1p(peak))+
                          (15 if v is not None and abs(v)<=5 else 0)+
                          (15 if price>0 else 0),1)
            # Low turnover is a distinct RESEARCH tier, not automatic rejection.
            critical=any(x in flags for x in ("POSIBLE_ESPECIE_MONEDA_DUPLICADA","CAMBIO_EXTREMO_REVISION","SIN_PRECIO"))
            tier=("REVISAR_DATOS" if critical else
                  "OPORTUNIDAD_ESPECIAL_OBSERVACION" if amount<5_000_000 else "OBSERVACION")
            enriched.append({"simbolo":candidate,"clase":group,
                 "precio_publico_dem":price,
                 "variacion_diaria_pct":v,
                 "monto_operado_no_normalizado":amount,
                 "puntaje_cribado":quality,
                 "estado":tier,
                 "requiere_spread_profundiad_y_frecuencia_operacion":amount<5_000_000,
                 "motivos":";".join(flags),
                 "tipo_ranking":"liquidez_indicativa_no_es_prediccion"})
        enriched.sort(key=lambda z:(z["estado"]!="OBSERVACION",-z["puntaje_cribado"]))
        allrank+=enriched
        top[group]=enriched[:20]
        low_activity_top[group]=sorted((r for r in enriched if r["estado"]=="OPORTUNIDAD_ESPECIAL_OBSERVACION"),
                                       key=lambda r:-r["monto_operado_no_normalizado"])[:20]
    dump(OUT/"cribado_total.csv",allrank)
    obj={"fecha_escaneo":j.get("scanned_at"),"observaciones":len(allrank),
         "cuenta_por_tipo":{g:len(vals) for g,vals in grouped.items()},
         "paneles_con_error":j.get("errors",{}),"top_por_tipo":top,
         "baja_liquidez_observacion_por_tipo":low_activity_top,
         "baja_liquidez_cantidad_por_tipo":{g:sum(x["estado"]=="OPORTUNIDAD_ESPECIAL_OBSERVACION" for x in allrank if x["clase"]==g) for g in grouped},
         "advertencia":"Monedas de cotización y spreads no verificados. Ranking de calidad/actividad del panel, NO de rentabilidad, compra, precio ejecutable, solvencia ni TIR."}
    (OUT/"cribado_resumen.json").write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
    print("PANEL_CRIBADO "+json.dumps({"total":len(allrank),"tipos":obj["cuenta_por_tipo"],
          "errores":obj["paneles_con_error"],"top_por_tipo":{k:[r["simbolo"] for r in arr[:5]] for k,arr in top.items()}},ensure_ascii=False))
if __name__=="__main__":main()
