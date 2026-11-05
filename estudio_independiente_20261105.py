"""Estudio aislado IOL sin radar, sin claves, sin órdenes reales ni simuladas."""
import io, json, math, re, time, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import requests

TICKERS=['PAMP','YPFD','IRSA','MOLI']
OUT=Path('informe_iol_independiente');OUT.mkdir(exist_ok=True)
CUTOFF=pd.Timestamp('2026-11-04')

def norm(x):
    return ''.join(c for c in unicodedata.normalize('NFD',str(x).lower()) if unicodedata.category(c)!='Mn')

def number(x):
    if pd.isna(x):return np.nan
    s=str(x).strip().replace(' ','').replace('\xa0','')
    if not s or s in ['-','—']:return np.nan
    if ',' in s and '.' in s:
        s=s.replace(',','') if s.rfind('.')>s.rfind(',') else s.replace('.','').replace(',','.')
    elif ',' in s:
        s=s.replace(',','') if re.fullmatch(r'\d{1,3}(,\d{3})+',s) else s.replace(',','.')
    return float(s)

def fetch(symbol):
    url='https://iol.invertironline.com/Titulo/DatosHistoricos'
    r=requests.get(url,params={'mercado':'BCBA','simbolo':symbol},
      headers={'User-Agent':'Mozilla/5.0 (research on public historical page; no login)'},timeout=25)
    r.raise_for_status()
    tabs=pd.read_html(io.StringIO(r.text),displayed_only=False)
    for t in tabs:
        cols=[norm(c) for c in t.columns]
        if any('fecha' in c for c in cols) and any('apertura' in c for c in cols) and any('volumen nominal' in c for c in cols):
            return t
    raise ValueError('Sin tabla histórica IOL utilizable')

def validate(t):
    rename={}
    for col in t.columns:
        c=norm(col)
        if 'fecha' in c:rename[col]='date'
        elif 'apertura' in c:rename[col]='open'
        elif 'maximo' in c:rename[col]='high'
        elif 'minimo' in c:rename[col]='low'
        elif 'volumen nominal' in c:rename[col]='volume'
        elif 'cierre ajustado' in c:rename[col]='adjusted'
        elif 'cierre' in c:rename[col]='close'
    t=t.rename(columns=rename)
    keys=['date','open','high','low','close','volume']
    if any(k not in t for k in keys):raise ValueError(f'Columnas faltantes: {list(t.columns)}')
    t=t[[k for k in keys+['adjusted'] if k in t]].copy()
    t['date']=pd.to_datetime(t.date,format='%m/%d/%Y',errors='coerce')
    if t.date.isna().any():raise ValueError('Fecha ambigua/no parseable')
    for k in keys[1:]+(['adjusted'] if 'adjusted' in t else []):t[k]=t[k].map(number)
    t=t[t.date<=CUTOFF].sort_values('date').reset_index(drop=True)
    if t.date.duplicated().any():raise ValueError('Fecha duplicada')
    if t[keys[1:]].isna().any().any() or (t[keys[1:]]<=0).any().any():
        raise ValueError('OHLCV ausente, cero o negativo')
    if ((t.high<t[['open','low','close']].max(axis=1))|(t.low>t[['open','high','close']].min(axis=1))).any():
        raise ValueError('OHLC inconsistente')
    if len(t)<220:raise ValueError(f'Solo {len(t)} ruedas OHLCV completas; mínimo 220')
    warnings=[]
    if 'adjusted' in t and (t.adjusted>0).all():
        factor=t.adjusted/t.close
        if (abs(factor-1)>.001).any():
            for k in ['open','high','low']:t[k]=t[k]*factor
            t['close']=t.adjusted
            warnings.append('OHLC ajustados; verificar eventos y volumen')
    if (t.close.pct_change().tail(220).abs()>.4).any():
        warnings.append('SALTO>40% dentro de 220 ruedas: bloquear señal hasta revisar split')
    if (t.date.diff().dt.days>10).any():
        warnings.append('Brecha de más de 10 días')
    return t,warnings

def wilder(x,n=14):
    a=np.asarray(x,dtype=float);y=np.full(len(a),np.nan)
    if len(a)>n and np.isfinite(a[1:n+1]).all():
        y[n]=np.mean(a[1:n+1])
        for i in range(n+1,len(a)):y[i]=(y[i-1]*(n-1)+a[i])/n
    return pd.Series(y,index=x.index)

def analyze(t):
    d=t.copy();c=d.close
    for n in [20,50,200]:
        d[f'sma{n}']=c.rolling(n).mean()
        d[f'ema{n}']=c.ewm(span=n,adjust=False,min_periods=n).mean()
    dif=c.diff();gain=wilder(dif.clip(lower=0));loss=wilder((-dif).clip(lower=0))
    d['rsi14']=100-100/(1+gain/loss.replace(0,np.nan))
    d.loc[(loss==0)&(gain>0),'rsi14']=100.
    m=c.ewm(span=12,adjust=False,min_periods=12).mean()-c.ewm(span=26,adjust=False,min_periods=26).mean()
    d['macd']=m;d['signal9']=m.ewm(span=9,adjust=False,min_periods=9).mean()
    d['macd_hist']=m-d.signal9
    tr=pd.concat([d.high-d.low,(d.high-c.shift(1)).abs(),(d.low-c.shift(1)).abs()],axis=1).max(axis=1)
    d['atr14']=wilder(tr)
    d['rvol20']=d.volume/d.volume.shift(1).rolling(20).mean()
    d['res20']=d.high.shift(1).rolling(20).max()
    d['low5']=d.low.shift(1).rolling(5).min()
    d['trend']=(c>d.ema50)&(d.ema50>d.ema200)&(d.ema50>d.ema50.shift(5))
    d['v2']=d.trend&(c>d.res20)&d.rsi14.between(52,75)&(d.macd_hist>0)&(d.rvol20>=1.2)
    d['rsi35']=(d.rsi14.shift(1)<=35)&(d.rsi14>35)&(c>d.ema200)
    return d

def test_v2(d):
    if len(d)<400:return {'estado':'NO_VALIDADA','razon':'menos de 400 ruedas'}
    border=int(len(d)*.7)
    trades=[];i=220;cost=.008655
    while i<len(d)-1:
        a=d.iloc[i]
        if not bool(a.v2):i+=1;continue
        entry=float(d.iloc[i+1].open)
        stop=min(float(a.low5),entry-1.2*float(a.atr14))
        take=entry+3.5*float(a.atr14)
        end=min(len(d)-1,i+5);px=float(d.iloc[end].close)
        for j in range(i+1,end+1):
            b=d.iloc[j]
            if b.low<=stop:end=j;px=min(stop,float(b.open));break
            if b.high>=take:end=j;px=take;break
        ret=(px*(1-cost)-entry*(1+cost))/(entry*(1+cost))
        trades.append((i,end,ret));i=end+1
    def report(v):
        return {'operaciones':len(v),'retorno_neto_compuesto':round(math.prod(1+r for r in v)-1,5) if v else None,
                'acierto':round(sum(r>0 for r in v)/len(v),3) if v else None}
    train=[r for i,j,r in trades if j<border]
    forward=[r for i,j,r in trades if i>=border]
    return {'estado':'EXPERIMENTAL_NO_VALIDADA','inicio_prueba':str(d.iloc[border].date.date()),'train':report(train),'test':report(forward),
            'supuestos':'señal cierre, entrada apertura siguiente, stop conservador, TP 3.5 ATR, máximo 5 días; 0.8655% costo por lado'}

def main():
    results={}
    for symbol in TICKERS:
        print('Intentando descargar:',symbol,flush=True)
        try:
            t,warnings=validate(fetch(symbol))
            d=analyze(t)
            d.to_csv(OUT/f'{symbol}_OHLCV_indicadores.csv',index=False)
            row=d.iloc[-1]
            indicators=['sma20','sma50','sma200','ema20','ema50','ema200','rsi14','macd','signal9','atr14','rvol20','res20','low5']
            results[symbol]={'filas_procesadas':len(d),'desde':str(d.iloc[0].date.date()),'hasta':str(row.date.date()),
                'ultimo_cierre_indicativo':float(row.close),
                'indicadores':{k:round(float(row[k]),5) if pd.notna(row[k]) else None for k in indicators},
                'v2_experimental':bool(row.v2),'rsi35_experimental':bool(row.rsi35),
                'advertencias':warnings,'backtest_experimental':test_v2(d),
                'alerta_entrada':False,
                'pendiente':'Precio local ARS T+1 y timestamp de negocio no corroborados en doble fuente; sin BID/ASK verificable'}
        except Exception as ex:
            results[symbol]={'alerta_entrada':False,'error':str(ex)}
        time.sleep(1)
    (OUT/'resultado.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
