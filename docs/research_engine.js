"use strict";
/* PULSO asset research v1 – explainable, deterministic daily OHLC technical research.
   Indicative what-if price levels are NOT broker orders or signals of proven profitability.
   No bond/ON yield, duration, maturity or coupon is inferred from an equity-style quote. */
(function(root){
 const finite=n=>typeof n==="number"&&Number.isFinite(n);
 const positive=n=>finite(n)&&n>0;
 const round=n=>finite(n)?Math.round(n*10000)/10000:null;
 function validate(bars){
   if(!Array.isArray(bars)||bars.length<56)return false;
   let last="";
   return bars.every(b=>{
     if(!Array.isArray(b)||b.length!==6||typeof b[0]!=="string"||b[0]<=last)return false;
     last=b[0];const [d,o,h,l,c,v]=b;
     return [o,h,l,c,v].every(finite)&&o>0&&l>0&&c>0&&v>=0&&
       h>=Math.max(o,l,c)&&l<=Math.min(o,c,h);
   });
 }
 function ema(values,period){
   if(values.length<period)return null;
   let e=values.slice(0,period).reduce((a,b)=>a+b,0)/period,k=2/(period+1);
   for(let i=period;i<values.length;i++)e=values[i]*k+e*(1-k);
   return e;
 }
 function rsi14(values){
   if(values.length<16)return null;
   let gain=0,loss=0;
   for(let i=1;i<=14;i++){const d=values[i]-values[i-1];gain+=Math.max(0,d);loss+=Math.max(0,-d);}
   gain/=14;loss/=14;
   for(let i=15;i<values.length;i++){
     const d=values[i]-values[i-1];
     gain=(gain*13+Math.max(0,d))/14;loss=(loss*13+Math.max(0,-d))/14;
   }
   if(gain===0&&loss===0)return 50;
   if(loss===0)return 100;
   return 100-100/(1+gain/loss);
 }
 function atr14(bars){
   const pm=typeof root?.PULSOPositionMath?.atr14==="function"?root.PULSOPositionMath.atr14:null;
   if(pm)return pm(bars);
   if(bars.length<16)return null;
   let v=[];
   for(let i=1;i<bars.length;i++)v.push(Math.max(bars[i][2]-bars[i][3],
     Math.abs(bars[i][2]-bars[i-1][4]),Math.abs(bars[i][3]-bars[i-1][4])));
   let a=v.slice(0,14).reduce((x,y)=>x+y,0)/14;
   for(let i=14;i<v.length;i++)a=(a*13+v[i])/14;
   return a;
 }
 function blank(asset,reason,kind="SIN_HISTORICO"){
   return {symbol:asset?.symbol||"",state:kind,confidence:"INSUFICIENTE",
     trend:"No evaluable",potential:[],risks:[reason],reasons:[],metrics:null,plan:null,
     date:null,source:null,disclaimer:"No es una sugerencia de operación real."};
 }
 function analyze(asset,history,opts={}){
   const kind=asset?.kind||"";
   if(kind==="bono"||kind==="on"){
     const out=blank(asset,"Faltan flujo de cupones, vencimiento, moneda, calendario de pagos, TIR y duration contrastados. Una cotización nominal no basta para determinar potencial ni stop/take profit.","RENTA_FIJA_SIN_VALUACION");
     out.trend="Renta fija: análisis fundamental pendiente";
     out.potential=[asset.events?.length?"Se registraron publicaciones; revisar sus documentos originales.":"Sin catalizador fundamental validado en el radar."];
     out.risks.push("Para bonos, la cotización puede ser por VN 100 y no por unidad; el cálculo del tamaño de la orden no es comparable a acciones.");
     out.next="Verificar prospecto, moneda y plazo, intereses corridos, TIR, spread, amortización y riesgo crediticio; recién luego analizar duration y niveles.";
     return out;
   }
   if(!["accion","cedear"].includes(kind))return blank(asset,"Tipo de especie no cubierto por el modelo técnico.");
   if(!validate(history?.bars))return blank(asset,"No existen 56 velas diarias consecutivamente ordenadas y coherentes para este símbolo.");
   const bars=history.bars;
   const last=bars.at(-1),date=last[0],close=last[4];
   const closes=bars.map(b=>b[4]), e20=ema(closes,20), e50=ema(closes,50), e200=ema(closes,200);
   const rsi=rsi14(closes),atr=atr14(bars);
   const old=close/closes.at(-21)-1;
   const prev=bars.slice(-21,-1);
   const prevHigh=Math.max(...prev.map(b=>b[2]));
   const prevLow=Math.min(...prev.map(b=>b[3]));
   const prevVol=prev.reduce((x,b)=>x+b[5],0)/prev.length;
   const volRatio=prevVol>0?last[5]/prevVol:null;
   const age=(opts.now instanceof Date?opts.now:new Date()).getTime()-Date.parse(date+"T12:00:00Z");
   const days=age/86400000;
   const freshness=days>=-.75&&days<=8.5;
   const cross=opts.cross?.prices?.[asset.symbol]||null;
   const mismatch=(cross?.status==="DIVERGENCE"&&cross?.market_date===date) ||
     asset.recommendation?.price_quality==="SEGUNDA_FUENTE_DISCREPA";
   const panelSameDate=String(asset.quote_retrieved_at||"").slice(0,10)===date;
   const gap=panelSameDate&&positive(asset.quote_price)?Math.abs(asset.quote_price/close-1)*100:null;
   const conflicts=gap!==null&&gap>.5;
   const positiveReasons=[],negativeReasons=[],risks=[];
   const evidence=[];
   if(e200!==null){
     if(close>e200&&e20>e50){positiveReasons.push("Cierre por encima de EMA200 y EMA20 por encima de EMA50: estructura alcista de mediano/largo plazo.");evidence.push("TREND");}
     else if(close<e200){negativeReasons.push("Cierre bajo EMA200: sesgo bajista de largo plazo.");}
     else negativeReasons.push("Medias móviles sin alineación alcista completa.");
   }else risks.push("Menos de 200 ruedas: sin EMA200 confiable.");
   if(old>.025){positiveReasons.push("Avance de "+round(old*100)+"% en 20 ruedas: momentum positivo observado.");evidence.push("MOM");}
   else if(old<-.025)negativeReasons.push("Caída de "+round(old*100)+"% en 20 ruedas: momentum negativo.");
   if(rsi>=45&&rsi<=68){positiveReasons.push("RSI14 "+round(rsi)+" en rango moderado: acompaña el movimiento sin sobrecompra extrema.");evidence.push("RSI");}
   else if(rsi>70)risks.push("RSI14 "+round(rsi)+": posible sobrecompra, no es confirmación de venta.");
   else if(rsi<35)risks.push("RSI14 "+round(rsi)+": debilidad/sobreventa, un rebote no está garantizado.");
   if(close>prevHigh&&volRatio!==null&&volRatio>=1.2){
     positiveReasons.push("Ruptura sobre el máximo de las 20 ruedas anteriores con volumen "+round(volRatio)+"× el promedio: confirmación de actividad observada.");
     evidence.push("BREAKOUT");
   }else if(close>prevHigh){
     positiveReasons.push("Supera el máximo de las 20 ruedas previas, pero falta confirmar volumen.");
     risks.push("Ruptura sin confirmación de volumen relativo >=1,2×.");
   }else if(volRatio!==null&&volRatio>=1.5){
     risks.push("Volumen elevado ("+round(volRatio)+"×) sin ruptura confirmada; puede reflejar distribución.");
   }
   const f=asset.fundamental;
   if(f&&f.sales_yoy_pct>0&&f.net_margin_pct>0){
     positiveReasons.push("Balance secundario: ventas nominales en alza y margen neto positivo en "+(f.fy||"último ejercicio")+".");
     risks.push("Balances secundarios NO ajustados por inflación ni validados al momento histórico: no prueban crecimiento real.");
   }else if(f?.net_margin_pct<0)negativeReasons.push("Margen neto anual informado negativo; revisar balance original.");
   if(Array.isArray(asset.events)&&asset.events.length){
     risks.push("Novedades recientes: leer las fuentes. No se supone impacto positivo ni causalidad.");
   }
   if(asset.status==="CAIDA_CON_NOVEDAD_INVESTIGAR")risks.push("Caída con publicación próxima: no presupone rebote.");
   if(asset.kind==="cedear")risks.push("CEDEAR: considerar ratio de conversión, CCL y precio del subyacente; no se modelan en este cálculo.");
   if(!freshness)risks.push("Cierre histórico fuera de la ventana de 8 días; niveles suspendidos.");
   if(mismatch||conflicts)risks.push("Inconsistencia entre fuentes/cotización del mismo día: no usar estos niveles.");
   if(!opts.cross?.prices?.[asset.symbol])risks.push("Cierre sin conciliación con segunda fuente.");
   if(!e200)risks.push("Cobertura histórica parcial para tendencias largas.");
   if(!positive(asset.bid)||!positive(asset.ask))risks.push("Spread y profundidad actuales no confirmados.");
   const trend=e200===null?"Largo plazo no evaluable":close>e200&&e20>e50?"Alcista observada":close<e200?"Bajista observada":"Mixta / lateral";
   const metrics={close:round(close),ema20:round(e20),ema50:round(e50),ema200:round(e200),rsi14:round(rsi),
     atr14:round(atr),atrPct:round(100*atr/close),momentum20Pct:round(old*100),
     volumeRatio:round(volRatio),support20:round(prevLow),resistance20:round(prevHigh),
     riskBelowSupportPct:round(100*(close-prevLow)/close),
     bars:bars.length};
   const stockQuality=positiveReasons.length>=2?"ARGUMENTOS_POSITIVOS":"ARGUMENTOS_INSUFICIENTES";
   const out={symbol:asset.symbol,state:stockQuality,trend,confidence:"EXPLORATORIO_NO_PROBADO",
     potential:positiveReasons.slice(0,5),reasons:negativeReasons,risks:risks.slice(0,8),
     metrics,date,source:history.source||"Histórico IOL público sin ajuste corporativo verificado",
     next:"Confirmar cierre y puntas actuales; nunca transformar directamente un escenario en orden.",
     disclaimer:"Señales descriptivas, no probabilidad de ganancia. Estrategia RSI35 no demostró rentabilidad fuera de muestra."};
   if(!freshness||mismatch||conflicts||!positive(atr))return {...out,state:"BLOQUEADO_POR_DATOS",plan:null};
   const math=root?.PULSOPositionMath;
   if(!math?.amount)return {...out,state:"CALCULADORA_NO_DISPONIBLE",plan:null};
   let levels,method,confirmed=false;
   if(asset.recommendation?.code==="SIMULAR_ENTRADA"&&asset.status==="ENTRADA_TEORICA_PAPEL"&&
       asset.daily_bar_date===date&&asset.recommendation.technical_date===date&&
       [asset.entry_ref,asset.stop_ref,asset.target_ref].every(positive)){
     levels={entry:asset.entry_ref,stop:asset.stop_ref,target:asset.target_ref};
     method="RSI35: niveles publicados a cierre; simulación solamente tras confirmar apertura posterior.";
     confirmed=true;
   }else{
     const entry=close;
     const distance=Math.max(1.5*atr,entry-prevLow+.2*atr);
     const stop=entry-distance;
     const target=Math.max(entry+3.5*atr, entry+2.4*distance);
     levels={entry,stop,target};
     method="ESCENARIO HIPOTÉTICO: entrada de referencia al cierre, stop debajo del soporte 20D o 1,5×ATR (el más distante), TP basado en 3,5×ATR o 2,4× riesgo bruto. No es una señal de compra.";
   }
   if(levels.stop<=0)return {...out,state:"STOP_NO_VALIDO",plan:null};
   const cap=positive(opts.capital)?opts.capital:100000;
   const calc=math.amount(cap,levels.entry,levels.stop,levels.target);
   if(!calc)return {...out,state:"NIVELES_NO_VALIDOS",plan:null};
   const potentialResistance=metrics.resistance20>levels.entry?metrics.resistance20:null;
   if(potentialResistance&&potentialResistance<levels.target)
     risks.push("Resistencia previa "+round(potentialResistance)+" antes del objetivo teórico; podría frenar el avance.");
   const t2=levels.entry+Math.max(4.5*atr,3.4*(levels.entry-levels.stop));
   const takeProfit2=confirmed?null:t2;
   const scenarioOK=calc.rr>=2&&calc.units>0;
   const state=confirmed&&scenarioOK?"PAPEL_VALIDADO":
     "HIPOTESIS_NO_SENAL";
   return {...out,state,
     risks:risks.slice(0,9),
     plan:{type:confirmed?"PAPEL_RSI35":"ESTUDIO_SIN_SENAL",
       entry:round(levels.entry),stop:round(levels.stop),tp1:round(levels.target),tp2:round(takeProfit2),
       support20:metrics.support20,resistance20:metrics.resistance20,
       rrNet:round(calc.rr),units:calc.units,
       unitsToOpen:confirmed&&scenarioOK?calc.units:0,
       cost:round(calc.cost),lossAtStop:round(calc.loss),gainAtTP1:round(calc.gain),
       method,capital:cap,validTrade:confirmed&&scenarioOK,
       invalidation:"Un cierre bajo soporte o stop invalida la hipótesis; confirmar gaps, spread y nueva apertura.",
       notes:"Las metas son geometría ATR/risgo, NO pronósticos. Comisiones ~0,6655% y slippage 0,1% por lado; pérdida por gap puede superar el stop."
     }
   };
 }
 const api={analyze,validate,ema,rsi14,atr14};
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 if(root)root.PULSOResearch=api;
})(typeof window!=="undefined"?window:null);
