#!/usr/bin/env python3
"""Publish public, automatically updated, delayed BYMA opportunities in GitHub Markdown."""
import json
from datetime import datetime
from pathlib import Path

source=Path("docs/data/market.json")
if not source.exists():
    raise RuntimeError("Dashboard JSON not available")
blob=json.loads(source.read_text(encoding="utf-8"))
assets=blob["assets"]
meta=blob["meta"]
summary=blob["summary"]

def safe(value):
    return str(value if value is not None else "").replace("|"," ").replace("\n"," ").replace("\r"," ")[:180]

def money(value):
    try:
        value=round(float(value),2)
        return "$"+format(value,",.2f").replace(",","_").replace(".",",").replace("_",".")
    except (ValueError,TypeError):
        return "No disponible"

def pct(value):
    try:
        return format(float(value),"+.2f")+"%"
    except (ValueError,TypeError):
        return "—"

def stamp(value):
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M (Argentina)")
    except (TypeError,ValueError):
        return "No disponible"

def rows(items):
    out=["| Símbolo | Precio público* | Var. panel | Prioridad | Fuente/noticia | Entrada / Stop / Objetivo |",
         "|---|---:|---:|---:|---|---|"]
    for a in items[:20]:
        events=a.get("events") or []
        ev=events[0] if events else None
        evidence=safe(ev["title"])[:95] if ev else "Revisión técnica diaria"
        if ev and str(ev.get("url") or "").startswith("https://"):
            evidence="["+evidence+"]("+ev["url"]+")"
        levels="No hay entrada confirmada"
        if a.get("entry_ref") is not None:
            levels=" / ".join([money(a.get("entry_ref")),money(a.get("stop_ref")),money(a.get("target_ref"))])
        out.append("| **"+safe(a["symbol"])+"** | "+money(a.get("quote_price"))+
                   " | "+pct(a.get("change_pct"))+" | "+safe(a.get("score"))+
                   " | "+evidence+" | "+levels+" |")
    if not items:
        out.append("| — | — | — | — | Sin señales que cumplan la clasificación | — |")
    return "\n".join(out)

paper=[a for a in assets if a["status"]=="ENTRADA_TEORICA_PAPEL"]
fall=[a for a in assets if a["status"]=="CAIDA_CON_NOVEDAD_INVESTIGAR"]
technical=[a for a in assets if a["status"]=="VIGILANCIA_TECNICA"]
parts=[
 "# PULSO BYMA — Listado público de oportunidades",
 "",
 "> **Datos públicos DEMORADOS, nunca en vivo.** Los precios no son ofertas ejecutables ni se garantiza rentabilidad.",
 "",
 "**Última descarga:** "+stamp(meta.get("generated_at"))+"; hora real de negociación desconocida.",
 "",
 "**Universo:** "+safe(summary.get("total"))+" especies, incluidos "+
 safe(summary.get("types",{}).get("accion"))+" acciones y "+
 safe(summary.get("types",{}).get("cedear"))+" CEDEARs.",
 "",
 "**Entradas ficticias teóricas:** "+str(len(paper))+". **Caídas con novedades para investigar:** "+
 str(len(fall))+". **Indicadores técnicos validados:** "+safe(summary.get("validated_tech"))+".",
 "",
 "## Entradas ficticias con niveles (no ejecutadas)",
 "",
 rows(paper),
 "",
 "## Alertas de caídas y noticias (no son compras confirmadas)",
 "",
 rows(fall),
 "",
 "La coincidencia entre una caída y una noticia no demuestra relación causal ni implica que habrá rebote.",
 "",
 "## Vigilancia técnica",
 "",
 rows(technical),
 "",
 "## Cómo interpretar el listado",
 "",
 "La prioridad es una medida heurística de **interés para investigar**, no probabilidad de ganancia.",
 "Los niveles de entrada, stop y objetivo son estimaciones para simulación únicamente. Sin spread y caja de puntas comprobados no hay precio ejecutable.",
 "",
 "Para detalles de los 1.883 símbolos: [archivo de datos completo](https://github.com/DrGonzo95/trading_argentino_colab/blob/main/docs/data/market.json).",
 "",
 "El código del panel interactivo existe en [docs](https://github.com/DrGonzo95/trading_argentino_colab/tree/main/docs); la publicación interactiva requiere habilitar GitHub Pages o conectar un hosting.",
 "",
 "Esta lista se reconstruye por tareas GitHub Actions, normalmente cada 15 minutos de rueda si el servicio ejecuta a horario. Para avisos individuales usá el radar de ChatGPT; no hay notificaciones push en este documento.",
 ""
]
result=Path("OPORTUNIDADES.md")
result.write_text("\n".join(parts),encoding="utf-8")
print("PUBLIC_MARKDOWN",{"path":str(result),"paper":len(paper),"news_dips":len(fall),"technical":len(technical)})
