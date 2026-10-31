#!/usr/bin/env python3
"""Public corporate event and news OBSERVER for BYMA paper research.
Never labels a headline as validated fundamental financial performance,
never invents current balance ratios or uses social rumours to trigger buys.

Sources: CNV public significant events, issuer IR page, Google News public RSS.
RSS is media discovery (third party); official CNV filing has higher evidential value.
"""
import csv, json, os, re, time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT=Path("resultados")
OUT=ROOT/"eventos"
OUT.mkdir(parents=True, exist_ok=True)
TODAY=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
WINDOW=timedelta(days=7)
# Tickers mapped ONLY to widely recognizable issuer names; no blind match on substrings.
ISSUERS={
 "YPFD":["YPF S.A.","YPF SOCIEDAD ANONIMA","YPF SA"],
 "GGAL":["GRUPO FINANCIERO GALICIA"],
 "BMA":["BANCO MACRO"],
 "BBAR":["BANCO BBVA ARGENTINA","BBVA ARGENTINA"],
 "PAMP":["PAMPA ENERGIA"],
 "CEPU":["CENTRAL PUERTO"],
 "CRES":["CRESUD"],
 "TGSU2":["TRANSPORTADORA DE GAS DEL SUR"],
 "TGNO4":["TRANSPORTADORA DE GAS DEL NORTE"],
 "EDN":["EDENOR","EMPRESA DISTRIBUIDORA Y COMERCIALIZADORA NORTE"],
 "TECO2":["TELECOM ARGENTINA"],
 "TRAN":["TRANSENER"],
 "LOMA":["LOMA NEGRA"],
 "ALUA":["ALUAR"],
 "TXAR":["TERNIUM ARGENTINA"],
 "IRSA":["IRSA INVERSIONES"],
 "SUPV":["GRUPO SUPERVIELLE","BANCO SUPERVIELLE"],
 "MIRG":["MIRGOR"],
 "METR":["METROGAS"],
 "HARG":["HOLCIM ARGENTINA"],
 "COME":["SOCIEDAD COMERCIAL DEL PLATA"],
 "VALO":["GRUPO FINANCIERO VALORES"],
 "BYMA":["BOLSAS Y MERCADOS ARGENTINOS"],
 "AAPL":["APPLE INC"],
 "NVDA":["NVIDIA CORP"],
 "MSFT":["MICROSOFT CORP"],
 "GOOGL":["ALPHABET INC","GOOGLE"],
 "META":["META PLATFORMS"],
 "TSLA":["TESLA INC"],
 "AMZN":["AMAZON.COM"],
 "MELI":["MERCADOLIBRE INC"],
}
NEWS_QUERIES={
 "YPFD":"YPF Argentina resultados trimestrales petrolera",
 "GGAL":"Grupo Financiero Galicia resultados trimestrales",
 "BMA":"Banco Macro balance recompra Argentina",
 "BBAR":"BBVA Argentina balance resultados",
 "PAMP":"Pampa Energia resultados inversion",
 "CEPU":"Central Puerto resultados energia",
 "TGSU2":"Transportadora Gas del Sur resultados",
 "CRES":"Cresud balance agropecuario",
 "SUPV":"Grupo Supervielle resultados financieros",
 "TRAN":"Transener Argentina resultados",
 "BYMA":"BYMA Bolsas Mercados Argentinos resultados",
 "NVDA":"Nvidia earnings guidance",
 "AAPL":"Apple earnings guidance",
 "MSFT":"Microsoft earnings guidance",
 "MELI":"MercadoLibre earnings guidance",
 "AMZN":"Amazon earnings guidance",
 "META":"Meta Platforms earnings guidance",
 "TSLA":"Tesla earnings guidance",
 "GOOGL":"Alphabet earnings guidance"
}
CATEGORIES=[
 ("BALANCE_RESULTADOS",r"\b(resultados|balance|estados financieros|eeff|earnings|trimestre|trimestrales)\b"),
 ("DIVIDENDO_CUPON",r"\b(dividendos?|dividend|pago de cup[oó]n|amortizaci[oó]n)\b"),
 ("RECOMPRA",r"\b(recompra|adquisici[oó]n de acciones propias|buyback)\b"),
 ("FUSION_ADQUISICION",r"\b(fusi[oó]n|adquisici[oó]n|merger|acquisition|compr[óo] empresa)\b"),
 ("DEUDA_CAPITAL",r"\b(emisi[oó]n|financiaci[oó]n|deuda|reestructuraci[oó]n|default|on\b)\b"),
 ("REGULACION",r"\b(regulaci[oó]n|tarifas?|cnv|regulator|permiso|sanci[oó]n)\b")
]
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; PublicDisclosureEducation/1.0; no orders)",
         "Accept":"text/html,application/rss+xml,application/xml"}
SESSION=requests.Session()
SESSION.headers.update(HEADERS)
def normalize(value):
    import unicodedata
    value=unicodedata.normalize("NFKD",str(value))
    return "".join(c for c in value if not unicodedata.combining(c)).upper()
def tag(text):
    return [name for name,pattern in CATEGORIES if re.search(pattern,text,re.I)]
def identify(entity):
    name=normalize(entity)
    # Require token boundaries to avoid e.g. YPF matching YPFA or Grupo Valores.
    matches=[]
    for ticker,names in ISSUERS.items():
        for alias in names:
            if re.search(r"(?<![A-Z0-9])"+re.escape(normalize(alias))+r"(?![A-Z0-9])",name):
                matches.append(ticker);break
    return sorted(set(matches))
def parse_date(value):
    formats=("%d %b. %Y %H:%M","%d %b %Y %H:%M","%d/%m/%Y %H:%M","%Y-%m-%dT%H:%M:%S")
    for fmt in formats:
        try:return datetime.strptime(value.strip(),fmt).replace(tzinfo=ZoneInfo("America/Argentina/Cordoba"))
        except ValueError:pass
    try:
        x=parsedate_to_datetime(value)
        return x.astimezone(ZoneInfo("America/Argentina/Cordoba")) if x.tzinfo else x.replace(tzinfo=ZoneInfo("America/Argentina/Cordoba"))
    except (ValueError,TypeError):return None
def fetch_cnv():
    url="https://www.cnv.gov.ar/SitioWeb/HechosRelevantes"
    response=SESSION.get(url,timeout=18);response.raise_for_status()
    soup=BeautifulSoup(response.text,"html.parser")
    result=[]
    for table in soup.select("table"):
        labels=normalize(table.get_text(" ",strip=True)[:250])
        if not all(a in labels for a in ("FECHA","ENTIDAD","DESCRIPCION")):continue
        for tr in table.select("tr"):
            tds=tr.find_all("td")
            if len(tds)<3:continue
            fields=[td.get_text(" ",strip=True) for td in tds[:4]]
            entity,description=fields[1],fields[2]
            ticker=identify(entity)
            if not ticker:continue
            link=None
            for a in tds[-1].select("a[href]"):
                l=a.get("href","")
                if l.startswith("http"):link=l;break
                if l.startswith("/"):link="https://www.cnv.gov.ar"+l;break
            dt=parse_date(fields[0])
            if dt and (dt>TODAY or TODAY-dt>WINDOW):continue
            for t in ticker:
                result.append({"ticker":t,"empresa_fuente":entity,
                    "fecha_publicacion":dt.isoformat() if dt else None,
                    "titulo":description[:600],"categorias":";".join(tag(description)),
                    "fuente":"CNV_HECHO_RELEVANTE_OFICIAL",
                    "url":link or url,
                    "numero_documento":fields[3][:40] if len(fields)>3 else "",
                    "prioridad_fuente":"OFICIAL","estado":"REVISAR_DOCUMENTO_Y_BALANCE",
                    "no_fundamental_ratios":True})
    if not result:
        return result,"SIN_FILAS_CNV_VALIDABLES; no afirmar ausencia de hechos relevantes"
    return result,"OK"
def fetch_news(ticker,query):
    url="https://news.google.com/rss/search?"+urlencode({"q":query+" when:7d","hl":"es-419","gl":"AR","ceid":"AR:es-419"})
    r=SESSION.get(url,timeout=12);r.raise_for_status()
    from xml.etree import ElementTree as ET
    root=ET.fromstring(r.content)
    if root.tag!="rss":raise ValueError("RSS invalido")
    records=[]
    for item in root.findall(".//item")[:12]:
        title=item.findtext("title")
        link=item.findtext("link")
        published=item.findtext("pubDate")
        if not title or not link or not link.startswith("https://"):continue
        dt=parse_date(published) if published else None
        if dt and (dt>TODAY or TODAY-dt>WINDOW):continue
        pub=item.findtext("source")
        records.append({"ticker":ticker,"empresa_fuente":query,
          "fecha_publicacion":dt.isoformat() if dt else None,
          "titulo":title[:500],"categorias":";".join(tag(title)),
          "fuente":"GOOGLE_NEWS_RSS_TERCEROS","medio":pub[:100] if pub else None,
          "url":link.strip(),
          "prioridad_fuente":"NOTICIA_NO_CONFIRMADA_EN_DOCUMENTO",
          "estado":"VERIFICAR_EN_IR_O_CNV","no_fundamental_ratios":True})
    return records
def main():
    observations=[];errors={}
    try:
        official,status=fetch_cnv()
        observations+=official
        errors["cnv"]=None if status=="OK" else status
    except Exception as e:
        errors["cnv"]=type(e).__name__+": "+str(e)[:130]
    # A stable bounded subset for each run, not all BYMA issuers.
    tickers=list(NEWS_QUERIES)
    chunk=8
    slot=int(TODAY.strftime("%j"))%3
    chosen=tickers[slot*chunk:(slot+1)*chunk]
    if not chosen:chosen=tickers[:chunk]
    per_source={}
    for sym in chosen:
        try:
            rows=fetch_news(sym,NEWS_QUERIES[sym])
            per_source[sym]=len(rows)
            observations+=rows
        except Exception as e:
            errors["noticias_"+sym]=type(e).__name__+": "+str(e)[:120]
        time.sleep(.15)
    unique={}
    for row in observations:
        k=(row["ticker"],row["fuente"],row.get("url") or row["titulo"])
        unique[k]=row
    events=list(unique.values())
    events.sort(key=lambda x:(x["fecha_publicacion"] or "",x["prioridad_fuente"]=="OFICIAL"),reverse=True)
    if events:
        fields=list(dict.fromkeys(k for row in events for k in row))
        with (OUT/"eventos_empresas.csv").open("w",newline="",encoding="utf-8") as fp:
            wr=csv.DictWriter(fp,fieldnames=fields);wr.writeheader();wr.writerows(events)
    counts={}
    for row in events:
        counts[row["ticker"]]=counts.get(row["ticker"],0)+1
    summary={
        "fecha_revision":TODAY.isoformat(),
        "hechos_cnv_vinculados_con_identidad_confirmada":sum(x["fuente"]=="CNV_HECHO_RELEVANTE_OFICIAL" for x in events),
        "noticias_rss_referidas":sum(x["fuente"]=="GOOGLE_NEWS_RSS_TERCEROS" for x in events),
        "noticias_consultadas_para":chosen,
        "eventos_por_ticker":counts,
        "fuentes_con_problema":errors,
        "lectura_de_balances_numericos":"NO_IMPLEMENTADA: solo indexacion de anuncios",
        "redes_sociales":"NO_CONECTADAS: no confundir titulares con sentimiento social",
        "signal":"OBSERVACION; ninguna compra sin documento, ratios, precio, spread, backtest o fuente temporal validada",
        "restricciones":[
          "Solo se vinculan entidades CNV cuando la denominacion coincide con alias auditados; otras quedan sin mapear.",
          "CNV puede mostrar solo un subconjunto reciente de hechos relevantes; no es censo completo de balances.",
          "RSS de terceros puede tener duplicados, errores, rumores, desfases y filtrado por buscador; enlace no implica verificación.",
          "No entrenar ni backtestear señales de noticias sin historial por hora de publicación y datos archivados antes del precio.",
          "No usar información privada, grupos cerrados ni trading con información privilegiada.",
          "Una noticia favorable puede estar descontada en el precio; ningún resultado futuro se garantiza."]}
    (OUT/"estado_eventos.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("EVENT_MONITOR "+json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
