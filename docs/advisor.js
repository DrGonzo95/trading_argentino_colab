"use strict";
/* PULSO / BYMA – conservative per-asset research instructions.
   Delayed public data: study or paper simulation only. RSI35 not validated for profitability. */
(function(root){
  const MAX_DELAY_HOURS=72;
  const fn=n=>typeof n==="number"&&Number.isFinite(n);
  const positive=n=>fn(n)&&n>0;
  const kinds=new Set(["accion","cedear"]);
  const datestr=d=>typeof d==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(d);
  const ageDays=(s,now)=>datestr(s)?(now-Date.parse(s+"T12:00:00Z"))/86400000:null;
  const num=n=>fn(n)?new Intl.NumberFormat("es-AR",{maximumFractionDigits:2}).format(n):"—";
  const classes={PAPER:"adv-paper",NEWS:"adv-news",WATCH:"adv-watch",WAIT:"adv-wait",DATA:"adv-data",BONDS:"adv-bond",CHECK:"adv-check"};
  let check=null,charts=null;
  function choice(code,action,why,next,risks,asset,meta){
    return {code,action,why,next,risks,css:classes[code],symbol:asset.symbol,
      source:meta?.generated_at||null,
      confidenceNote:"Categoría de seguimiento; no es un porcentaje de éxito ni una señal ejecutable."};
  }
  function evaluate(asset,meta={},opt={}){
    const now=opt.now instanceof Date?opt.now:new Date();
    const cc=opt.check===undefined?check:opt.check;
    const ch=opt.charts===undefined?charts:opt.charts;
    const kind=asset.kind;
    const risks=[];
    const missingQuote=!positive(asset.quote_price);
    const barDays=ageDays(asset.daily_bar_date,now.getTime());
    const barExpired=barDays===null||barDays<-.6||barDays>5.5;
    const generated=Date.parse(meta.generated_at||"");
    const feedAgeHours=Number.isFinite(generated)?(now.getTime()-generated)/3600000:Infinity;
    const staleFeed=feedAgeHours>MAX_DELAY_HOURS||feedAgeHours<-.25;
    const d=cc?.prices?.[asset.symbol]||null;
    const history=ch?.symbols?.[asset.symbol];
    const last=history?.bars?.at?.(-1)||null;
    const sameDate=d?.market_date===last?.[0];
    const independentMismatch=sameDate&&d?.status==="DIVERGENCE";
    const validatedTechnical=fn(asset.technical_score)&&asset.technical_score>=0&&
      datestr(asset.daily_bar_date)&&!barExpired;
    const hasPlot=!!(history?.bars&&history.bars.length>=2);
    if(!hasPlot)risks.push("Gráfico histórico no disponible para esta especie.");
    if(!d)risks.push("Cierre sin cotejo independiente publicado para el símbolo.");
    else if(!sameDate)risks.push("El cotejo externo no corresponde al mismo cierre del histórico.");
    if(!positive(asset.bid)||!positive(asset.ask))risks.push("No hay caja de puntas verificable en tiempo real.");
    else risks.push("Las puntas públicas son demoradas; confirmar con el broker.");
    if(asset.quote_currency_verified!==true)risks.push("Moneda/plazo de ejecución sin confirmar.");
    if(kind==="bono"||kind==="on")return choice("BONDS","Analizar condiciones, no operar desde el radar",
      "La renta fija requiere TIR, flujos de cupones, amortizaciones, moneda y plazo de liquidación; esta ficha no los concilia.",
      "Consultar el prospecto, flujo de pagos y las puntas actuales antes de evaluar la inversión.",risks,asset,meta);
    if(!kinds.has(kind))return choice("DATA","Solo observar",
      "El instrumento no tiene un protocolo de señal operativa implementado.",
      "Verificar especie, moneda y metodología antes de estudiarlo.",risks,asset,meta);
    if(missingQuote)return choice("DATA","No operar: falta precio",
      "No hay una cotización positiva para contrastar.",
      "Esperar la próxima descarga válida y cotejar el precio con una fuente independiente.",risks,asset,meta);
    if(independentMismatch)return choice("DATA","No operar: fuentes discrepantes",
      "Dos fuentes públicas reportan cierres distintos para la misma fecha (diferencia mayor al umbral de cotejo).",
      "Investigar especie, ajuste corporativo y cierre oficial antes de analizar otra señal.",risks,asset,meta);
    if(staleFeed){
      risks.push("Exportación del radar antigua o sin fecha válida.");
      return choice("WAIT","Esperar actualización de datos",
        "La última descarga disponible tiene más de 72 horas o no tiene fecha confiable.",
        "Actualizar el radar y verificar la sesión publicada antes de evaluar una nueva operación.",risks,asset,meta);
    }
    if(asset.warnings?.some?.(v=>/posible especie en otra moneda|duplicada por moneda/i.test(v))){
      return choice("DATA","No operar: verificar especie",
        "La identificación de moneda o modalidad de negociación puede no ser única.",
        "Confirmar símbolo exacto, moneda, plazo y ratio de conversión cuando corresponda.",risks,asset,meta);
    }
    const levels=[asset.entry_ref,asset.stop_ref,asset.target_ref];
    const setup=asset.status==="ENTRADA_TEORICA_PAPEL"&&
      levels.every(fn)&&0<levels[1]&&levels[1]<levels[0]&&levels[0]<levels[2]&&
      fn(asset.rr_net_est)&&asset.rr_net_est>=2&&validatedTechnical;
    if(setup){
      risks.push("La estrategia RSI35 todavía NO demostró rentabilidad fuera de muestra.");
      return choice("PAPER","Simular entrada; no comprar automáticamente",
        "El radar publicó un cruce técnico con niveles teóricos y R:R neta estimada ≥ 2; la señal se calculó al cierre.",
        "En la siguiente rueda comprobar apertura real, spread, liquidez y que el riesgo ficticio no supere 0,5% del capital (máx. 20% de exposición). Si cambian los niveles, recalcular y descartar la señal anterior.",risks,asset,meta);
    }
    if(asset.status==="ENTRADA_TEORICA_PAPEL")return choice("WAIT","Esperar: señal técnica incompleta",
      "La entrada indicada no pasó la validación actual de fecha, niveles o riesgo/beneficio.",
      "Recalcular con una rueda completa reciente y verificar R:R neta ≥ 2, liquidez y costos.",risks,asset,meta);
    if(asset.status==="CAIDA_CON_NOVEDAD_INVESTIGAR"){
      const official=fn(asset.events_official)&&asset.events_official>0;
      return choice("NEWS",official?"Revisar hecho relevante CNV":"Investigar noticia y caída",
        "El panel muestra una caída y una publicación cercana. La relación causal no está demostrada y no hay recuperación técnica confirmada.",
        "Leer la publicación original, verificar la fecha, descartar un ajuste corporativo y esperar un cierre técnico válido; evitar comprar solo porque bajó.",risks,asset,meta);
    }
    if(asset.status==="NOVEDAD_OFICIAL")return choice("CHECK","Leer documento CNV",
      "Hay una publicación oficial, pero no una señal técnica de entrada validada.",
      "Estudiar el impacto económico y esperar datos técnicos y precios recientes antes de sacar conclusiones.",risks,asset,meta);
    if(!validatedTechnical)return choice("DATA",hasPlot?"Solo observar: falta validación técnica":"No operar: historial insuficiente",
      hasPlot?"Hay velas para visualización, pero no una señal técnica reciente respaldada por la serie exigida.":"El radar no dispone de una serie validada para establecer niveles operativos.",
      "Reunir al menos 400 ruedas válidas, revisar ajustes corporativos y calcular indicadores antes de interpretar una entrada.",risks,asset,meta);
    if(asset.trend_bull===false)return choice("WAIT","Esperar mejora de tendencia",
      "La lectura técnica actual no supera el filtro de tendencia de largo plazo del radar.",
      "Vigilar un cierre con tendencia recuperada y nueva señal completa; no anticipar un giro.",risks,asset,meta);
    if(asset.status==="VIGILANCIA_TECNICA"||asset.trend_bull===true)return choice("WATCH","Vigilar próximo cierre",
      "Hay indicadores técnicos recientes, pero no un cruce RSI35 con entrada válida confirmado.",
      "Revisar al cierre si se cumple el patrón predefinido y después simular entrada a la apertura siguiente, sin operar con el precio demorado.",risks,asset,meta);
    return choice("WAIT","Esperar señal completa",
      "No se observó un patrón de entrada vigente que cumpla el modelo definido.",
      "Mantener en seguimiento y reevaluar cuando cambie una condición técnica verificable.",risks,asset,meta);
  }
  function notify(){if(typeof document!=="undefined")document.dispatchEvent(new CustomEvent("byma:advisor"));}
  function setChecks(v){check=v||null;notify()}
  function setCharts(v){charts=v||null;notify()}
  const api={evaluate,setChecks,setCharts,format:num,method:"RSI35 solo para papel; revisiones sin señal no son compras."};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  if(root)root.PULSOAdvice=api;
  if(typeof document!=="undefined"){
    Promise.allSettled([
      fetch("./data/quote_check.json?advisor="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():null),
      fetch("./data/charts.json?advisor="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():null)
    ]).then(r=>{
      if(r[0].status==="fulfilled")check=r[0].value;
      if(r[1].status==="fulfilled")charts=r[1].value;
      notify();
    });
  }
})(typeof window!=="undefined"?window:null);
