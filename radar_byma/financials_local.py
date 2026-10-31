#!/usr/bin/env python3
"""Coverage of listed Argentine issuer annual numerical statements.
Uses visibly published third-party BCBA financial tables, never mislabels
them as CNV audited XBRL or PIT (point-in-time) historical facts.
The ARS series is NOMINAL and often reflects reporting/inflation accounting;
NEVER interpret nominal YoY as real growth or mix ARS with USD.
Runs a limited batch, saves a cumulative research-only ledger.
"""
import csv,json,math,re,time,os
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

NOW=datetime.now(ZoneInfo("America/Argentina/Cordoba"))
DATA=Path("resultados/fundamentales")
DATA.mkdir(parents=True,exist_ok=True)
STATE=Path("radar_byma/state/local_financials.json")
STATE.parent.mkdir(parents=True,exist_ok=True)
PANEL=Path("resultados/discovery/snapshot.json")
URL="https://stockanalysis.com/quote/bcba/{sym}/financials/"
BATCH=16
REFRESH_GOOD=timedelta(days=21)
RETRY_BAD=timedelta(days=5)
HEAD={"User-Agent":"Mozilla/5.0 (compatible; educational public market research)",
      "Accept":"text/html"}
S=requests.Session()
S.headers.update(HEAD)
LABS={
 "Revenue":"revenue",
 "Net Income":"net_income",
 "Operating Income":"operating_income",
 "Operating Cash Flow":"operating_cashflow",
 "Free Cash Flow":"free_cashflow",
 "Total Assets":"assets",
 "Total Liabilities":"liabilities",
 "Shareholders' Equity":"equity",
 "Total Debt":"debt",
 "Cash & Cash Equivalents":"cash",
 "Cash & Investments":"cash_and_investments"
}
def load():
    if not STATE.exists():return {"version":1,"records":{}}
    raw=json.loads(STATE.read_text(encoding="utf-8"))
    if raw.get("version")!=1:raise ValueError("Invalid local financials schema")
    return raw
def tickers():
    if not PANEL.exists():raise RuntimeError("First run discover_byma.py")
    p=json.loads(PANEL.read_text(encoding="utf-8"))
    all_syms={r.get("symbol","") for r in p.get("snapshot",[]) if r.get("class")=="accion"}
    return sorted(t for t in all_syms if re.fullmatch(r"[A-Z][A-Z0-9]{1,9}",t)
                  and not (t.endswith(("C","D")) and t[:-1] in all_syms))
def parse_num(s):
    t=str(s).strip().replace(",","").replace(" ","").replace("$","")
    if t in ("","-","—","N/A"):return None
    if t.startswith("(") and t.endswith(")"):t="-"+t[1:-1]
    try:
        v=float(t)
        return v if math.isfinite(v) else None
    except ValueError:return None
def find_annual(table,concepts):
    # Headers are FY 2025/FY 2024, not current TTM. Their column indices
    # are read from the SAME table and never inferred from page-wide headers.
    rows=table.find_all("tr")
    if not rows:return {}
    headers=[]
    for tr in rows[:5]:
        cells=[cell.get_text(" ",strip=True) for cell in tr.find_all(["td","th"])]
        years=[]
        for i,cell in enumerate(cells):
            m=re.search(r"\bFY\s*(20\d{2})\b",cell)
            if m:years.append((i,int(m.group(1))))
        if len(years)>=2:
            headers=sorted(years,key=lambda x:-x[1]);break
    if len(headers)<2:return {}
    y1=next((x for x in headers if x[1]<=NOW.year),None)
    y2=next((x for x in headers if y1 and x[1]==y1[1]-1),None)
    if not y1 or not y2:return {}
    result={"year":y1[1],"previous_year":y2[1]}
    for tr in rows:
        cells=[cell.get_text(" ",strip=True) for cell in tr.find_all(["td","th"])]
        if len(cells)<=max(y1[0],y2[0]):continue
        label=cells[0].strip().lower()
        for key,name in concepts.items():
            l=key.lower()
            # Avoid confusing e.g. "Revenue Growth" with "Revenue".
            if label!=l and not label.startswith(l+" "+l+" growth"):continue
            a,b=parse_num(cells[y1[0]]),parse_num(cells[y2[0]])
            if a is not None and b is not None:
                result[name]=a
                result[name+"_prev"]=b
    return result
def getpage(url):
    response=S.get(url,timeout=20)
    response.raise_for_status()
    text=response.text
    soup=BeautifulSoup(text,"html.parser")
    plain=" ".join(soup.get_text(" ",strip=True).split())
    unit=re.search(r"Financials in millions\s+(ARS|USD)\b",plain,re.I)
    if not unit:raise ValueError("Statement unit/scale not verifiable")
    if unit.group(1).upper()!="ARS":raise ValueError("Expected ARS local listing, got "+unit.group(1))
    return soup
def rows_for(soup,concepts):
    best={}
    for table in soup.select("table"):
        got=find_annual(table,concepts)
        if len(got)>len(best):best=got
    return best
def retrieve(sym):
    main=URL.format(sym=sym)
    paths=[(main,{"Revenue":"revenue","Net Income":"net_income","Operating Income":"operating_income"}),
           (main+"balance-sheet/",{"Total Assets":"assets","Total Liabilities":"liabilities",
             "Shareholders' Equity":"equity","Total Debt":"debt","Cash & Investments":"cash_and_investments"}),
           (main+"cash-flow-statement/",{"Operating Cash Flow":"operating_cashflow","Free Cash Flow":"free_cashflow"})]
    data={}
    for index,(url,concepts) in enumerate(paths):
        soup=getpage(url)
        found=rows_for(soup,concepts)
        if not found:raise ValueError("Annual table not parsed: "+url)
        if index and found.get("year")!=data.get("year"):
            raise ValueError("Financial statements fiscal year mismatch")
        data.update(found)
        time.sleep(.22)
    if not all(k in data for k in ("revenue","net_income","assets","equity","operating_cashflow")):
        raise ValueError("Missing required annual income/balance/cashflows")
    if data["revenue"]<=0 or data["revenue_prev"]<=0 or data["assets"]<=0:
        raise ValueError("Zero or nonpositive core statement")
    def ratio(a,b):
        return round(100*data[a]/data[b],3) if data.get(a) is not None and data.get(b) else None
    data.update({
        "ticker":sym,"unit":"MILLONES_ARS_NOMINALES_TABLA_TERCERO",
        "source":main,"balance_sheet_source":main+"balance-sheet/",
        "cash_flow_source":main+"cash-flow-statement/",
        "observed_at":NOW.isoformat(),"original_filing_date":None,
        "true_real_growth_not_available":True,
        "historical_backtest_eligible":False,
        "revenue_yoy_nominal_pct":round(100*(data["revenue"]/data["revenue_prev"]-1),3),
        "net_income_margin_pct":ratio("net_income","revenue"),
        "operating_income_margin_pct":ratio("operating_income","revenue"),
        "debt_to_equity_pct":ratio("debt","equity"),
        "operating_cash_to_revenue_pct":ratio("operating_cashflow","revenue"),
        "fcf_to_revenue_pct":ratio("free_cashflow","revenue"),
        "data_quality":"SECONDARY_ANNUAL_PARTIAL_NOT_OFFICIAL_NOT_POINT_IN_TIME"
    })
    return data
def main():
    universe=tickers()
    store=load()
    records=store["records"]
    ordered=[]
    for sym in universe:
        old=records.get(sym,{})
        try:asof=datetime.fromisoformat(old.get("checked_at",""))
        except (ValueError,TypeError):asof=NOW-timedelta(days=10000)
        age=NOW-asof
        threshold=REFRESH_GOOD if old.get("status")=="ANNUAL_FOUND" else RETRY_BAD
        if age>=threshold:ordered.append((sym,asof,old))
    ordered.sort(key=lambda x:(x[1],x[0]))
    # Batch selection purposely includes symbols that may be illiquid.
    selection=[x[0] for x in ordered[:BATCH]]
    batch=[]
    for sym in selection:
        try:
            statement=retrieve(sym)
            records[sym]={"status":"ANNUAL_FOUND","checked_at":NOW.isoformat(),
                          "statement":statement}
            batch.append({"ticker":sym,"status":"ANNUAL_FOUND","fy":statement["year"]})
        except Exception as e:
            records[sym]={"status":"NOT_VERIFIED","checked_at":NOW.isoformat(),
                          "reason":type(e).__name__+": "+str(e)[:130]}
            batch.append({"ticker":sym,"status":"NOT_VERIFIED","reason":str(e)[:110]})
        time.sleep(.4)
    store["last_run"]=NOW.isoformat()
    store["source"]="stockanalysis.com/quote/bcba (third-party summary; ARS millions)"
    store["all_listed"]=len(universe)
    STATE.write_text(json.dumps(store,ensure_ascii=False,indent=2),encoding="utf-8")
    valid=[x["statement"] for x in records.values() if x.get("status")=="ANNUAL_FOUND"]
    if valid:
        columns=list(dict.fromkeys(k for row in valid for k in row))
        with (DATA/"arg_terceros_comparativo.csv").open("w",newline="",encoding="utf-8") as file:
            wr=csv.DictWriter(file,fieldnames=columns);wr.writeheader();wr.writerows(valid)
    report={
        "date":NOW.isoformat(),"universe_arg_eligible_tickers":len(universe),
        "consulted_this_run":len(selection),"cumulative_checked":sum(x.get("status") in ("ANNUAL_FOUND","NOT_VERIFIED") for x in records.values()),
        "cumulative_with_valid_statements":len(valid),
        "remaining_unchecked":sum(s not in records for s in universe),
        "batch":batch,
        "restrictions":["Third-party local listing statements, NOT CNV official, statement date not independently checked.",
          "Money in millions ARS, YoY is NOMINAL, not inflation-adjusted and must not be interpreted as real growth.",
          "Different business sectors are not directly comparable by net margin or debt/equity.",
          "Missing financial data NEVER converted into zeros, orders, or a positive outlook.",
          "Historic figures cannot be backtested without official filing dates, adjusted inflation and corporate actions."]}
    (DATA/"arg_terceros_estado.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("LOCAL_FINANCIALS "+json.dumps({k:v for k,v in report.items() if k!="batch"},ensure_ascii=False))
    print("LOCAL_FINANCIALS_BATCH "+json.dumps(batch,ensure_ascii=False))
if __name__=="__main__":main()
