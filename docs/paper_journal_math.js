"use strict";
/* PULSO BYMA - manual-only paper journal validation.
   No quote lookup, broker connection, order routing or inferred fills. */
(function(root,factory){
  const api=factory();
  if(typeof module==="object"&&module.exports)module.exports=api;
  root.PULSOPaperJournal=api;
})(typeof window!=="undefined"?window:globalThis,function(){
  const FEE=(0.005+0.0005)*1.21; // commission + exchange rights + VAT, hypothetical
  const SLIP=0.001;
  const RISK=0.005;
  const EXPOSURE=0.20;
  const finite=x=>typeof x==="number"&&Number.isFinite(x);
  function validate(data, today){
    const p={...data};
    const symbol=String(p.symbol||"").trim().toUpperCase();
    const kind=p.kind;
    const capital=Number(p.capital),entry=Number(p.entry),stop=Number(p.stop),
          target=Number(p.target),qty=Number(p.qty);
    if(!/^[A-Z0-9]{1,12}$/.test(symbol))return {valid:false,reason:"Símbolo local inválido."};
    if(!["accion","cedear"].includes(kind))return {valid:false,reason:"Solo acciones argentinas y CEDEARs, sin bonos/ON ni ADR USD."};
    if(![capital,entry,stop,target,qty].every(x=>finite(x)&&x>0)||!Number.isInteger(qty)||capital<1000||capital>1e12){
      return {valid:false,reason:"Cantidad entera, capital y precios positivos obligatorios."};
    }
    if(!(stop<entry&&target>entry))return {valid:false,reason:"El stop debe estar bajo entrada y el objetivo por encima."};
    const date=String(p.date||"");
    const current=String(today||new Date().toISOString().slice(0,10));
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date+"T12:00:00Z"))||date>current){
      return {valid:false,reason:"Fecha de simulación ausente, inválida o futura."};
    }
    if(p.confirm!==true)return {valid:false,reason:"Confirmá expresamente que es tu simulación manual, no una ejecución de mercado."};
    // Entry reference plus slippage + fee; conservative exit after slippage and fee.
    const unitCost=entry*(1+SLIP)*(1+FEE);
    const proceedsFactor=(1-SLIP)*(1-FEE);
    const unitRisk=unitCost-stop*proceedsFactor;
    const unitReward=target*proceedsFactor-unitCost;
    if(!(unitRisk>0&&unitReward>0))return {valid:false,reason:"Beneficio o riesgo neto inválido después de costos."};
    const spend=qty*unitCost,loss=qty*unitRisk,gain=qty*unitReward,rr=unitReward/unitRisk;
    const maxUnits=Math.max(0,Math.floor(Math.min(capital*RISK/unitRisk,capital*EXPOSURE/unitCost)));
    if(spend>capital*EXPOSURE+1e-7||loss>capital*RISK+1e-7){
      return {valid:false,reason:"Supera exposición 20% o riesgo teórico 0,5%. Máximo "+maxUnits+" unidades.",maxUnits,rr,spend,loss,gain};
    }
    if(rr<2-1e-9)return {valid:false,reason:"Relación beneficio/riesgo neta inferior a 2:1.",rr,spend,loss,gain,maxUnits};
    const source=String(p.source||"SIMULACION_MANUAL");
    const allowedSources=["SIMULACION_MANUAL","IOL_PUBLICO","RAVA_PUBLICO","BYMADATA_PUBLICO","OTRO_PUBLICO"];
    if(!allowedSources.includes(source))return {valid:false,reason:"Fuente declarada inválida."};
    const quoteAt=String(p.quoteAt||"");
    if(quoteAt&&!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(quoteAt))return {valid:false,reason:"Formato de fecha/hora no reconocido."};
    if(quoteAt&&quoteAt.slice(0,10)>current)return {valid:false,reason:"Hora de referencia en fecha futura."};
    return {valid:true,symbol,kind,capital,entry,stop,target,qty,date,source,quoteAt,
      spend,loss,gain,rr,maxUnits,unitCost,unitRisk,unitReward,
      riskPortfolioPct:100*loss/capital,capitalReturnTargetPct:100*gain/capital,
      feeEachSidePct:100*FEE,slipEachSidePct:100*SLIP,
      status:"ABIERTA_FICTICIA_MANUAL_NO_VERIFICADA",manual:true,
      disclaimer:"Precio y fecha declarados por el usuario. NO hay orden bursátil, fill, precio actual ni confirmación de caja de puntas."};
  }
  return {validate,constants:{FEE,SLIP,RISK,EXPOSURE}};
});
