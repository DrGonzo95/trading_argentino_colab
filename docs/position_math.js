"use strict";
/* PULSO / BYMA position sizing. No broker orders, no live prices, no guaranteed stop fills.
 * Pure calculations for Node tests + browser. Hypothetical scenarios are NOT entry signals. */
(function(root){
 const FEE=.0055*1.21;       // estimated commission incl. VAT per side
 const SLIP=.001;             // modeled slippage per side, not observed spread
 const RISK=.005;             // 0.5% portfolio risk per hypothetical position
 const MAX_ALLOC=.20;         // 20% portfolio exposure per hypothetical position
 const valid=x=>typeof x==="number"&&Number.isFinite(x);
 const good=x=>valid(x)&&x>0;
 function daysOld(day,now){
   if(!/^\d{4}-\d{2}-\d{2}$/.test(String(day||"")))return null;
   const a=Date.parse(day+"T12:00:00Z");
   if(!Number.isFinite(a))return null;
   return (now.getTime()-a)/86400000;
 }
 function barsValid(bars){
   if(!Array.isArray(bars)||bars.length<25)return false;
   let last="";
   return bars.every(b=>{
     if(!Array.isArray(b)||b.length!==6||typeof b[0]!=="string"||b[0]<=last)return false;
     last=b[0];
     return b.slice(1).every(valid)&&b[1]>0&&b[3]>0&&b[5]>=0&&
       b[2]>=Math.max(b[1],b[3],b[4])&&b[3]<=Math.min(b[1],b[2],b[4]);
   });
 }
 function atr14(bars){
   if(!barsValid(bars))return null;
   const tr=[];
   for(let i=1;i<bars.length;i++){
     const [,,h,l]=bars[i],prev=bars[i-1][4];
     tr.push(Math.max(h-l,Math.abs(h-prev),Math.abs(l-prev)));
   }
   let a=tr.slice(0,14).reduce((v,n)=>v+n,0)/14;
   for(let i=14;i<tr.length;i++)a=(a*13+tr[i])/14;
   return valid(a)&&a>0?a:null;
 }
 function amount(capital,entry,stop,target){
   if(!good(capital)||!good(entry)||!good(stop)||!good(target)||!(stop<entry&&entry<target))return null;
   const buy=entry*(1+SLIP)*(1+FEE);
   const saleFactor=(1-SLIP)*(1-FEE);
   const lossUnit=buy-stop*saleFactor;
   const winUnit=target*saleFactor-buy;
   if(!good(lossUnit)||!valid(winUnit))return null;
   const units=Math.max(0,Math.floor(Math.min(capital*RISK/lossUnit,capital*MAX_ALLOC/buy)));
   return {units,entry,stop,target,cost:units*buy,loss:units*lossUnit,
       gain:units*winUnit,rr:winUnit/lossUnit,capital,unitCost:buy,unitLoss:lossUnit,
       feePerSidePct:FEE*100,slippagePerSidePct:SLIP*100,
       assumption:"Cierre histórico de referencia, comisión estimada y slippage supuesto. La pérdida real por gaps puede superar la del stop."};
 }
 function assess(asset,chart,capital=100000,now=new Date()){
   const symbol=String(asset?.symbol||"");
   const recommendation=asset?.recommendation||{};
   const base={symbol,kind:asset?.kind||"",openUnits:0,mode:"NO_ABRIR",scenario:null,
     reason:recommendation.next_step||"No hay una señal de entrada verificada.",
     action:recommendation.label||"No abrir",referenceDate:null,
     source:"Panel demorado e histórico IOL, sin precios ejecutables",capital};
   if(!["accion","cedear"].includes(asset?.kind))return {...base,reason:"Sin modelo de flujos, TIR, cupones y unidad nominal: no simular compra de bonos u ON."};
   if(!good(capital)||capital>1e12)return {...base,reason:"Capital de simulación inválido."};
   if(recommendation.price_quality==="SEGUNDA_FUENTE_DISCREPA"||recommendation.code==="REVISAR_DISCREPANCIA")
     return {...base,reason:"Diferencia de cierres entre fuentes: se suspende también el escenario."};
   const bars=chart?.bars;
   if(!barsValid(bars))return {...base,reason:"Sin suficientes velas OHLCV coherentes para calcular ATR14 (mínimo 25)."};
   const last=bars[bars.length-1];
   const age=daysOld(last[0],now);
   if(age===null||age<-.8||age>8.5)return {...base,reason:"Histórico anterior a la ventana de simulación: esperar actualización."};
   const c=last[4],atr=atr14(bars);
   if(!good(c)||!good(atr))return {...base,reason:"ATR o cierre histórico no calculable."};
   const scenarioBase={entry:c,stop:c*(1+SLIP)-1.2*atr,target:c*(1+SLIP)+3.5*atr};
   const whatif=amount(capital,scenarioBase.entry,scenarioBase.stop,scenarioBase.target);
   const maybe=whatif&&good(whatif.gain)?whatif:null;
   const out={...base,referenceDate:last[0],atr14:atr,scenario:maybe};
   // Only the *published, same-candle and current* RSI35 signal can become an
   // opening candidate for a hypothetical paper trade. Never execute a real order.
   const eligible=recommendation.code==="SIMULAR_ENTRADA"&&recommendation.real_trade_allowed===false&&
    asset.status==="ENTRADA_TEORICA_PAPEL"&&asset.daily_bar_date===last[0]&&
    recommendation.technical_date===last[0]&&
    [asset.entry_ref,asset.stop_ref,asset.target_ref,asset.rr_net_est].every(valid)&&asset.rr_net_est>=2;
   if(!eligible)return {...out,mode:maybe?"ESTUDIO_SIN_SENAL":"NO_ABRIR",
      reason:maybe?"Se muestran niveles hipotéticos basados en ATR14; no existe una entrada RSI35 validada.":"No hay configuración histórica suficiente."};
   const plan=amount(capital,asset.entry_ref,asset.stop_ref,asset.target_ref);
   if(!plan||plan.rr<2||plan.units<1)return {...out,mode:"NO_ABRIR",reason:"Relación neta menor a 2:1 o tamaño mínimo no compatible con 0,5% de riesgo y 20% de exposición."};
   return {...out,mode:"ENTRADA_SOLO_PAPEL",openUnits:plan.units,plan,
     reason:"Señal RSI35 al cierre publicada; cantidad y resultado solo hipotéticos. Deben recalcularse con apertura siguiente y puntas actuales."};
 }
 const api={assess,amount,atr14,barsValid,daysOld,FEE,SLIP,RISK,MAX_ALLOC};
 if(root)root.PULSOPositionMath=api;
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:null);
