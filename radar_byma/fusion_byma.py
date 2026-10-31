#!/usr/bin/env python3
"""Evidence-first BYMA research ranking: official docs > dated numerical accounts
> verified technical history > stale public quote > unsupported social mentions.
NO order, no prediction, no claim of audited numeric coverage where missing.
"""
import csv,json,math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT=Path("resultados/integrado")
OUT.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
ROOT=Path("resultados")
STATE=Path("radar_byma/state")
def jread(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError,OSError):return {}
def readcsv(path):
    if not Path(path).exists():return []
    with open(path,encoding="utf-8",newline="") as fp:return list(csv.DictReader(fp))
def asfloat(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None
def recent(raw,days=5):
    try:
        when=datetime.fromisoformat(raw)
        if when.tzinfo is None:return False
        return -1<=(NOW-when.astimezone(NOW.tzinfo)).total_seconds()/86400<=days
    except (ValueError,TypeError):return False
def main():
    quote=jread(ROOT/"discovery"/"snapshot.json")
    if not quote.get("snapshot"):raise RuntimeError("No se puede rankear sin panel")
    technical=readcsv(ROOT/"ranking"/"acciones_cedears_analisis_tecnico.csv")
    technical_by={r["simbolo"]:r for r in technical}
    events=jread(STATE/"events_latest.json")
    sec=jread(STATE/"sec_latest.json")
    arg=jread(STATE/"arg_latest.json")
    study=jread(STATE/"events_study_latest.json")
    e_recent=recent(events.get("revisado_en")) and not events.get("errores",{}).get("cnv")
    s_recent=recent(sec.get("fecha"))
    a_recent=recent(arg.get("fecha"))
    ev_by={r["ticker"]:r for r in events.get("top_prioridad_revision",[]) if r.get("ticker")} if e_recent else {}
    sec_by={}
    if s_recent:
        for r in sec.get("resultados",[]):
            if r.get("ticker"):sec_by[r["ticker"]]=r
    ar_by=arg.get("estado_por_ticker",{}) if a_recent else {}
    rows=[]
    for quote_row in quote["snapshot"]:
        symbol=quote_row.get("symbol")
        group=quote_row.get("class")
        if not symbol or group not in ("accion","cedear","bono","on"):continue
        tech=technical_by.get(symbol,{})
        e=ev_by.get(symbol)
        fs=sec_by.get(symbol)
        fa=ar_by.get(symbol,{})
        tscore=asfloat(tech.get("puntaje_tecnico"))
        official=int(e.get("documentos_cnv") or 0) if e else 0
        headlines=int(e.get("titulares") or 0) if e else 0
        social=int(e.get("social_no_verificado") or 0) if e else 0
        metric=fs is not None or fa.get("estado")=="CIFRAS_DE_TABLA_CORPORATIVA_HISTORICAS"
        # A transparent observation priority, not a probabilistic trade score.
        score=(min(35,official*8)+min(12,headlines*2)+
               (min(30,tscore*.3) if tscore is not None else 0)+
               (12 if metric else 0))
        spread=asfloat(quote_row.get("spread_pct_delayed"))
        if spread is not None and spread>2:score=max(0,score-10)
        low=asfloat(quote_row.get("turnover_indicative")) or 0
        if low<=0:score=max(0,score-10)
        quality=[]
        if e_recent and e:quality.append("EMISOR_NOVEDAD_EN_CNV_O_RSS")
        if tscore is not None:quality.append("TECNICO_DATOS_DIARIOS_VALIDOS")
        if metric:quality.append("FUNDAMENTAL_NUMERICO_PARCIAL")
        if spread is not None:quality.append("SPREAD_PUBLICO_DEMORADO")
        if not quality:quality.append("SOLO_PANEL_PRECIO_DEMORADO")
        reasons=[]
        if group in ("bono","on"):
            reasons.append("SIN_TIR_CUPONES_TASA_MONEDA_Y_LIQUIDEZ_VERIFICADOS")
        else:
            if not metric:reasons.append("SIN_BALANCE_NUMERICO_VERIFICADO")
            if tscore is None:reasons.append("SIN_SERIE_TECNICA_VALIDADA")
        if not e_recent:reasons.append("NOTICIAS_NO_ACTUALIZADAS_O_NO_VINCULADAS")
        if spread is None:reasons.append("SPREAD_Y_PROFUNDIDAD_NO_VERIFICADOS")
        if low<5_000_000:reasons.append("BAJA_ACTIVIDAD_INDICATIVA")
        if study.get("prediction_status")!="VALIDATED":reasons.append("SIN_MODELO_PREDICTIVO_VALIDADO")
        # Data quality, not projected return. No live order book exists.
        trade="SIN_OPERACION_VERIFICADA"
        if tscore is not None and tech.get("estado")=="SEÑAL_RSI35_PAPEL":
            trade="ESTUDIAR_PAPER_SOLO_SI_SPREAD_Y_COTIZACION_FIRME"
        if group in ("bono","on"):trade="OBSERVACION_RENTA_FIJA_SOLAMENTE"
        rows.append({"ticker":symbol,"clase":group,
            "prioridad_investigacion_0_a_100":round(min(100,max(0,score)),1),
            "tecnico_puntaje_heuristico":tscore,
            "novedades_cnv_oficiales_vinculadas":official if e_recent else None,
            "titulares_asociados":headlines if e_recent else None,
            "menciones_sociales_sin_verificar":social if e_recent else None,
            "fundamental_numerico": "PARCIAL_VERIFICADO" if metric else "SIN_DATOS_VALIDOS",
            "fundamental_anual_cierre":fs.get("asof") if fs else None,
            "crecimiento_ventas_anual_sec_pct":fs.get("yoy_pct") if fs else None,
            "margen_neto_sec_pct":fs.get("net_margin_pct") if fs else None,
            "spread_pct_informativo":spread,
            "monto_operado_unidad_sin_verificar":low,
            "estado_operativo":trade,"evidencia":";".join(quality),
            "datos_faltantes":";".join(reasons),
            "precio_publico_dem":quote_row.get("last_delayed"),
            "cotizacion_tiempo_real":False})
    rows.sort(key=lambda r:(-r["prioridad_investigacion_0_a_100"],r["ticker"]))
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/"ranking_integral_todos.csv").open("w",newline="",encoding="utf-8") as fp:
        w=csv.DictWriter(fp,fieldnames=fields);w.writeheader();w.writerows(rows)
    for g in ("accion","cedear","bono","on"):
        subset=[r for r in rows if r["clase"]==g]
        if subset:
            with (OUT/f"ranking_{g}.csv").open("w",newline="",encoding="utf-8") as fp:
                w=csv.DictWriter(fp,fieldnames=fields);w.writeheader();w.writerows(subset)
    summary={"fecha":NOW.isoformat(),"paneles_consultados":len(rows),
      "accion":sum(r["clase"]=="accion" for r in rows),
      "cedear":sum(r["clase"]=="cedear" for r in rows),
      "bono":sum(r["clase"]=="bono" for r in rows),
      "on":sum(r["clase"]=="on" for r in rows),
      "con_historico_valido_para_indicadores":sum(r["tecnico_puntaje_heuristico"] is not None for r in rows),
      "con_fundamental_numerico_parcial":sum(r["fundamental_numerico"]=="PARCIAL_VERIFICADO" for r in rows),
      "novedades_verificadas_recientes":e_recent,
      "fundamentales_sec_estado":sec.get("SEC_API") if s_recent else "NO_ACTUALIZADO",
      "fundamentales_arg_numero_emisores":arg.get("emisores_con_cifras_extraidas") if a_recent else None,
      "modelo_de_noticias_estado":study.get("prediction_status","NO_EVALUADO"),
      "nuevas_operaciones_reales":0,
      "top_solo_investigacion":[{"ticker":r["ticker"],"clase":r["clase"],
              "prioridad":r["prioridad_investigacion_0_a_100"],
              "estado":r["estado_operativo"],
              "fundamentos":r["fundamental_numerico"],
              "faltantes":r["datos_faltantes"]} for r in rows[:15]],
      "no_promesas":[
        "El puntaje mide prioridad de investigación y cobertura documental, no retorno esperado.",
        "Las noticias y balances se observan en workflows distintos con fechas verificadas; estado desactualizado no agrega puntos.",
        "Las menciones en redes sociales no suman puntos de compra y pueden contener rumores.",
        "Fuentes SEC bloqueadas con HTTP403 no se sustituyen por datos inventados.",
        "Para operar faltan puntas reales, profundidad, impuestos y una validación prospectiva de la señal." ]}
    (OUT/"resumen.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FUSION_BYMA "+json.dumps({k:v for k,v in summary.items() if k!="top_solo_investigacion"},ensure_ascii=False))
    print("TOP_FUSION "+json.dumps(summary["top_solo_investigacion"][:7],ensure_ascii=False))
if __name__=="__main__":main()
