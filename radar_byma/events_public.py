#!/usr/bin/env python3
"""Public event radar for Argentine equities. No proprietary keys, no orders.

CNV events are official disclosures, news feeds are headlines and Reddit is
UNVERIFIED discussion. No fundamental ratios inferred from headlines.
Observe publication timestamp: no lookahead, no 'predictions' before publication.
"""
import csv,json,re,time,unicodedata
from datetime import datetime,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode,urljoin
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

TZ=ZoneInfo("America/Argentina/Cordoba")
NOW=datetime.now(TZ)
OUT=Path("resultados/eventos");OUT.mkdir(parents=True,exist_ok=True)
PANEL=Path("resultados/discovery/snapshot.json")
CNV="https://www.cnv.gov.ar/SitioWeb/HechosRelevantes"
RSS="https://news.google.com/rss/search"
SOCIAL="https://www.reddit.com/r/merval/new/.rss?limit=50"
# Exact company aliases, not short ambiguous ticker alone. Not comprehensive!
ALIASES={
"GGAL":["GRUPO FINANCIERO GALICIA","BANCO GALICIA"],
"YPFD":["YPF S.A.","YPF SA","YPF SOCIEDAD ANONIMA"],
"PAMP":["PAMPA ENERGIA"],
"BMA":["BANCO MACRO"],
"BBAR":["BBVA ARGENTINA","BANCO BBVA ARGENTINA"],
"CEPU":["CENTRAL PUERTO"],
"CRES":["CRESUD"],
"BYMA":["BOLSAS Y MERCADOS ARGENTINOS"],
"TXAR":["TERNIUM ARGENTINA"],
"TECO2":["TELECOM ARGENTINA"],
"ALUA":["ALUAR"],
"SUPV":["GRUPO SUPERVIELLE","BANCO SUPERVIELLE"],
"EDN":["EDENOR","EMPRESA DISTRIBUIDORA Y COMERCIALIZADORA NORTE"],
"LOMA":["LOMA NEGRA"],
"TGSU2":["TRANSPORTADORA DE GAS DEL SUR"],
"TGNO4":["TRANSPORTADORA DE GAS DEL NORTE"],
"TRAN":["TRANSENER"],
"IRSA":["IRSA INVERSIONES"],
"BOLT":["BOLDT"],
"METR":["METROGAS"],
"MIRG":["MIRGOR"],
"HARG":["HOLCIM ARGENTINA"],
"CELU":["CELULOSA ARGENTINA"],
"SAMI":["SOCIEDAD ANONIMA MOLINOS AGRO"],
"COME":["SOCIEDAD COMERCIAL DEL PLATA"],
"BHIP":["BANCO HIPOTECARIO"],
"MOLI":["MOLINOS RIO DE LA PLATA"],
"AGRO":["AGROMETAL"],
"RICH":["LABORATORIOS RICHMOND"],
"AUSO":["AUTOPISTAS DEL SOL"],
"DGCU2":["DISTRIBUIDORA DE GAS CUYANA"],
"CVH":["CABLEVISION HOLDING"],
"INVJ":["INVERSORA JURAMENTO"],
"VALO":["GRUPO FINANCIERO VALO"],
"FERR":["FERRUM"],
"LEDE":["LEDESMA"],
"CTIO":["CONSULTATIO"],
"LONG":["LONGVIE"],
"SEMI":["SEMINO"],
"CGPA2":["CAMUZZI GAS PAMPEANA"],
"POLL":["POLLEDO"],
"RIGO":["RIGOLLEAU"],
"CAPX":["CAPEX S.A.","CAPEX SOCIEDAD ANONIMA"],
"BPAT":["BANCO PATAGONIA"],
"CARC":["CARBOCLOR"],
"RIGO":["RIGOLLEAU"],
"GARO":["GAROVAGLIO Y ZORRAQUIN"],
}
# Common finance-relevant keywords; labels are triggers to READ original,
# NEVER bullish/bearish predictions.
TOPICS={
 "resultados_balance":r"\b(balance|balances|resultados|estado[s]? financiero[s]?|utilidad(?:es)?|ganancia[s]?|ebitda)\b",
 "dividendos":r"\b(dividendo[s]?|distribucion de utilidades|pago de dividendo)\b",
 "recompra":r"\b(recompra|adquisicion de acciones propias|buyback)\b",
 "financiamiento":r"\b(obligaciones negociables|emision|financiamiento|deuda|bonos|refinanciacion)\b",
 "adquisicion":r"\b(adquisicion|fusion|oferta publica de adquisicion|opa|compra de activos)\b",
 "riesgo":r"\b(default|incumplimiento|concurso preventivo|quiebra|intervencion judicial|reestructuracion)\b",
 "produccion":r"\b(produccion|reservas|ventas|inversion|exportacion|contrato)\b"
}
SPANISH_MONTHS={"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}
UA={"User-Agent":"Mozilla/5.0 (educational-public-finance-event-monitor; read-only)","Accept":"text/html,application/rss+xml,application/atom+xml"}
SESSION=requests.Session();SESSION.headers.update(UA)
def norm(s):
    s=unicodedata.normalize("NFKD",str(s))
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+"," ",s.upper()).strip()
def topics(text):
    n=norm(text).lower()
    return [k for k,p in TOPICS.items() if re.search(p,n)]
def matching_company(text):
    n=norm(text)
    matches=[]
    for ticker,names in ALIASES.items():
        if any(norm(name) in n for name in names):
            matches.append(ticker)
    return matches
def parse_cnv_date(s):
    x=norm(s).lower().replace(".","")
    m=re.search(r"(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\s+(\d{4})\s+(\d{1,2}):(\d{2})",x)
    if not m:return None
    dd,mo,yy,hh,mm=m.groups()
    return datetime(int(yy),SPANISH_MONTHS[mo],int(dd),int(hh),int(mm),tzinfo=TZ)
def cnv_events():
    resp=SESSION.get(CNV,timeout=35);resp.raise_for_status()
    soup=BeautifulSoup(resp.text,"html.parser")
    out=[]
    for table in soup.select("table"):
        h=table.get_text(" ",strip=True).upper()
        if not ("ENTIDAD" in h and "DESCRIPCI" in norm(h)):continue
        for tr in table.select("tr"):
            cells=tr.find_all("td")
            if len(cells)<3:continue
            timestamp=parse_cnv_date(cells[0].get_text(" ",strip=True))
            if timestamp is None or timestamp>NOW or timestamp<NOW-timedelta(days=21):continue
            company=cells[1].get_text(" ",strip=True)
            description=cells[2].get_text(" ",strip=True)
            sym=matching_company(company)
            a=tr.find("a",href=True)
            url=urljoin(CNV,a.get("href")) if a else CNV
            item={"fecha_publicacion":timestamp.isoformat(),"entidad":company,"titulo":description[:450],
                "tickers":sym,"temas":topics(description),"url_documento":url,"clase":"CNV_HECHO_RELEVANTE",
                "confianza":"FUENTE_OFICIAL_TEXTO_RESUMEN",
                "revisar_documento":True}
            out.append(item)
    if not out:raise ValueError("No se detectaron filas recientes de la CNV; no inventar hechos")
    return out
def headlines_for(ticker,name):
    # The full company name is essential; no ticker-only ambiguous news searches.
    q=f'"{name}" (acciones OR bolsa OR resultados OR dividendos) when:7d'
    args=urlencode({"q":q,"hl":"es-419","gl":"AR","ceid":"AR:es-419"})
    url=RSS+"?"+args
    rsp=SESSION.get(url,timeout=18,headers={"Accept":"application/rss+xml"})
    rsp.raise_for_status()
    root=ET.fromstring(rsp.content)
    channel=root.find("channel")
    if channel is None:raise ValueError("RSS sin canal")
    found=[]
    for item in channel.findall("item")[:15]:
        title=(item.findtext("title") or "").strip()
        rawdate=item.findtext("pubDate")
        if not rawdate or not title:continue
        try:stamp=parsedate_to_datetime(rawdate).astimezone(TZ)
        except (ValueError,TypeError):continue
        if stamp>NOW or stamp<NOW-timedelta(days=8):continue
        if norm(name) not in norm(title):continue
        src=item.find("source")
        found.append({"ticker":ticker,"fecha_publicacion":stamp.isoformat(),
                      "titulo":title[:350],"medio":src.text if src is not None else "",
                      "url_noticia":(item.findtext("link") or "").strip(),
                      "temas":topics(title),"confianza":"SOLO_TITULAR_NO_VERIFICADO",
                      "clase":"GOOGLE_NEWS_RSS","sujeto":"coincidencia_de_nombre"})
    return found
def public_social():
    try:
        rsp=SESSION.get(SOCIAL,timeout=14,headers={"Accept":"application/atom+xml"})
        rsp.raise_for_status()
        root=ET.fromstring(rsp.content)
        ns={"a":"http://www.w3.org/2005/Atom"}
        found=[]
        for item in root.findall("a:entry",ns):
            title=item.findtext("a:title",default="",namespaces=ns)
            if not title:continue
            rawdate=item.findtext("a:published",default="",namespaces=ns) or item.findtext("a:updated",default="",namespaces=ns)
            try:stamp=datetime.fromisoformat(rawdate.replace("Z","+00:00")).astimezone(TZ)
            except (ValueError,TypeError):continue
            if stamp>NOW or stamp<NOW-timedelta(days=7):continue
            candidates=[ticker for ticker in ALIASES if re.search(r"\b"+re.escape(ticker)+r"\b",norm(title))]
            if not candidates:continue
            link=item.find("a:link",ns)
            href=link.attrib.get("href","") if link is not None else ""
            found.append({"tickers":candidates,"titulo":title[:300],"fecha_publicacion":stamp.isoformat(),
                          "url":href,"clase":"SOCIAL_REDDIT_R_MERVAL","confianza":"OPINION_NO_VERIFICADA",
                          "relevancia":"SOLO_PARA_INVESTIGAR"})
        return found,"DISPONIBLE"
    except Exception as exc:return [],"NO_DISPONIBLE:"+type(exc).__name__+":"+str(exc)[:100]
def write_csv(name,rows):
    if not rows:return
    # Nested arrays encoded JSON, not python repr.
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
def main():
    snapshot=json.loads(PANEL.read_text(encoding="utf-8"))
    stocks=sorted({r["symbol"] for r in snapshot.get("snapshot",[]) if r.get("class")=="accion"})
    report={"revisado_en":NOW.isoformat(),"total_acciones_panel":len(stocks),
            "acciones_mapeadas_a_emisora":len(set(stocks)&set(ALIASES)),"fuente_cnv":CNV,
            "completo_balance_cuantitativo":False,"anotaciones":[],"errores":{}}
    mapped=set(stocks)&set(ALIASES)
    report["acciones_sin_mapeo"]=sorted(set(stocks)-mapped)
    filings=[]
    try:filings=cnv_events()
    except Exception as e:report["errores"]["cnv"]=type(e).__name__+": "+str(e)[:130]
    # Match event to ticker only by company name; unassigned official rows still preserved.
    official=[{**e,"tickers":[s for s in e["tickers"] if s in mapped]} for e in filings]
    official_matched=[x for x in official if x["tickers"]]
    report.update(total_hechos_cnv=len(official),hechos_cnv_coincidentes=len(official_matched))
    write_csv("hechos_relevantes_cnv.csv",official)
    # Searches prioritized by publicly mapped entities; keep bounded, no scraping private groups.
    # 32 queries, rotates coverage by date; no promise of complete per-company coverage per run.
    selection=sorted(mapped)
    if selection:
        shift=(NOW.toordinal()*32)%len(selection)
        selection=(selection[shift:]+selection[:shift])[:32]
    news=[]
    for ticker in selection:
        company=ALIASES[ticker][0]
        try:news.extend(headlines_for(ticker,company))
        except Exception as e:report["errores"]["rss_"+ticker]=type(e).__name__+":"+str(e)[:100]
        time.sleep(.15)
    # Preserve only links and timestamps, no unverified sentiment scoring.
    write_csv("noticias_titulares.csv",news)
    social,social_status=public_social()
    write_csv("redes_no_verificadas.csv",social)
    report.update(consultas_noticias=len(selection),noticias_con_nombre_coincidente=len(news),
                  estado_redes=social_status,publicaciones_sociales_mencionando_ticker=len(social))
    impact={s:{"ticker":s,"documentos_cnv":0,"titulares":0,"social_no_verificado":0,"temas":set()} for s in stocks}
    for x in official_matched:
        for s in x["tickers"]:
            impact[s]["documentos_cnv"]+=1;impact[s]["temas"].update(x["temas"])
    for x in news:
        if x["ticker"] in impact:
            impact[x["ticker"]]["titulares"]+=1;impact[x["ticker"]]["temas"].update(x["temas"])
    for x in social:
        for s in x["tickers"]:
            if s in impact:impact[s]["social_no_verificado"]+=1
    # Event attention, not future price prediction, not fundamental numeric score.
    ranked=[]
    for v in impact.values():
        v["temas"]=sorted(v["temas"])
        v["prioridad_lectura"]=min(100,30*v["documentos_cnv"]+6*v["titulares"]+1*v["social_no_verificado"])
        v["estado"]="REVISAR_DOCUMENTOS_PUBLICADOS" if v["documentos_cnv"] else "INVESTIGAR_NOTICIAS" if v["titulares"] else "SIN_EVENTOS_VERIFICADOS_EN_ESTE_BARRIDO"
        ranked.append(v)
    ranked.sort(key=lambda x:(-x["prioridad_lectura"],x["ticker"]))
    write_csv("ranking_lectura_eventos.csv",ranked)
    report["top_prioridad_revision"]=ranked[:15]
    report["restricciones"]=[
      "NO es análisis de ratios fundamentales, valor razonable, PER, EV/EBITDA ni crecimiento; faltan balances numéricos estandarizados por emisor.",
      "Publicaciones posteriores al cierre de rueda NO pueden ser usadas para predecir precio previo.",
      "Mención en noticias/redes no equivale a tono positivo o cambio fundamental; no autocomprar.",
      "Identidades de empresas se mapean a alias concretos: ticker solo es ambiguo y no se usa como verdad.",
      "Análisis de redes públicas depende de accesibilidad; si falla se declara NO DISPONIBLE.",
      "No hay datos en tiempo real, ni fuente privada, ni garantía de anticipar el mercado."
    ]
    (OUT/"reporte.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("EVENTOS_RESULTADO "+json.dumps({k:v for k,v in report.items() if k not in ("acciones_sin_mapeo","top_prioridad_revision","restricciones")},ensure_ascii=False))
    print("EVENTOS_TOP "+json.dumps(ranked[:10],ensure_ascii=False))
if __name__=="__main__":main()
