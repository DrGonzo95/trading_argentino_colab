"use strict";
/* PULSO – per-asset position simulator. No auto trades; no fake fills.
 * Uses price history for WHAT-IF calculations, not investment advice. */
(()=>{
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const cash=x=>typeof x==="number"&&Number.isFinite(x)?"$ "+fmt.format(x):"—";
const count=x=>typeof x==="number"&&Number.isFinite(x)?fmt.format(x):"—";
let charts={};let cross=null;let capital=100000;let filter="chart";let search="";
function assets(){try{return Array.isArray(s.items)?s.items:[]}catch{return []}}
function el(tag,css,text){const n=document.createElement(tag);if(css)n.className=css;if(text!==undefined)n.textContent=String(text);return n}
function plan(a){
 const fallback=window.PULSOPositionMath?.assess(a,charts[a.symbol],capital)||null;
 const analysis=window.PULSOResearch?.analyze(a,charts[a.symbol],{capital,cross});
 if(!analysis)return fallback;
 const candidate=analysis.plan;
 const base={...(fallback||{}),symbol:a.symbol,kind:a.kind,capital,referenceDate:analysis.date,openUnits:0};
 if(!candidate)return {...base,mode:"NO_ABRIR",plan:null,scenario:null,
  reason:analysis.risks?.[0]||"Histórico o valoración insuficiente para formular un escenario."};
 const amounts=window.PULSOPositionMath?.amount(capital,candidate.entry,candidate.stop,candidate.tp1);
 if(!amounts)return {...base,mode:"NO_ABRIR",plan:null,scenario:null,reason:"No se pudieron validar riesgo y tamaños del plan."};
 const accepted=candidate.type==="PAPEL_RSI35"&&candidate.validTrade;
 return {...base,mode:accepted?"ENTRADA_SOLO_PAPEL":"ESTUDIO_SIN_SENAL",
  openUnits:accepted?amounts.units:0,plan:accepted?amounts:null,scenario:amounts,
  reason:analysis.next+" "+candidate.method,
  tp2:candidate.tp2,referenceMethod:candidate.method};
}
function riskBadge(rec){
 return rec?.mode==="ENTRADA_SOLO_PAPEL"?"Abrir en PAPEL":"0 unidades a abrir";
}
function amountRow(parent,name,val){
 const item=el("div","sim-stat");item.append(el("span","",name),el("strong","",val));parent.append(item);
}

function paragraph(parent,message,css="research-note"){if(message)parent.append(el("p",css,message))}
function renderResearch(a,root){
 const research=window.PULSOResearch?.analyze(a,charts[a.symbol],{capital,cross});
 if(!research)return;
 const panel=el("section","detail-section research-panel");
 panel.append(el("h3","","Análisis técnico y potencial · "+a.symbol));
 const status=el("div","research-status",research.trend+" · "+research.state.replaceAll("_"," "));
 panel.append(status);
 if(research.date)paragraph(panel,"Cierre estudiado: "+research.date+" · "+research.source,"research-date");
 if(research.metrics){
  const m=research.metrics;
  const grid=el("div","sim-stats research-metrics");
  for(const [name,value,suffix] of [
   ["Cierre histórico",cash(m.close),""],["RSI 14",count(m.rsi14),""],
   ["EMA 20 / EMA 50",cash(m.ema20)+" / "+cash(m.ema50),""],
   ["EMA 200",cash(m.ema200),""],["ATR 14",cash(m.atr14),""],
   ["Momentum 20 ruedas",count(m.momentum20Pct),"%"],["Volumen relativo",count(m.volumeRatio),"×"],
   ["Soporte 20D",cash(m.support20),""],["Resistencia 20D",cash(m.resistance20),""]]){
    amountRow(grid,name,String(value)+(value==="—"?"":suffix));
   }
  panel.append(grid);
 }
 const possible=el("div","research-reasons");
 possible.append(el("h4","","¿Por qué podría tener potencial?"));
 if(research.potential.length)research.potential.forEach(v=>paragraph(possible,"+ "+v,"research-pro"));
 else paragraph(possible,"No hay argumentos alcistas suficientes validados; no se supone potencial por una caída.");
 (research.reasons||[]).forEach(v=>paragraph(possible,"− "+v,"research-con"));
 panel.append(possible);
 const plan=research.plan;
 if(plan){
  const levels=el("div","research-levels");
  levels.append(el("h4","",plan.type==="PAPEL_RSI35"?"Plan para simulación RSI35 (NO compra real)":"Escenario condicional (NO hay señal de entrada)"));
  paragraph(levels,plan.method,"research-date");
  const grid=el("div","sim-stats");
  for(const [name,value] of [
    ["Entrada de referencia",cash(plan.entry)],["Stop condicional",cash(plan.stop)],
    ["Take profit 1",cash(plan.tp1)],["Take profit 2",plan.tp2==null?"—":cash(plan.tp2)],
    ["Relación R:R neta al TP1",count(plan.rrNet)+":1"],
    ["Unidades para abrir por señal",String(plan.unitsToOpen)],
    ["Unidades en hipótesis",String(plan.units)],
    ["Pérdida estimada al stop",cash(plan.lossAtStop)],
    ["Ganancia estimada al TP1",cash(plan.gainAtTP1)]]){
      amountRow(grid,name,value);
    }
  levels.append(grid);
  paragraph(levels,plan.invalidation,"research-warning");
  paragraph(levels,plan.notes,"research-date");
  panel.append(levels);
 }else paragraph(panel,"SIN niveles de operación: no hay históricos suficientes, o existe un bloqueo de datos/valoración. No se inventan stops ni objetivos.","research-warning");
 const flags=el("div","research-risks");
 flags.append(el("h4","","Riesgos y datos pendientes"));
 research.risks.slice(0,6).forEach(v=>paragraph(flags,"• "+v,"research-warning"));
 panel.append(flags);
 paragraph(panel,research.next||"Revisar fuentes, precio y señal antes de considerar una simulación.","research-next");
 paragraph(panel,research.disclaimer,"research-date");
 root.append(panel);
}

function renderAsset(a,root){
 if(!a||!root)return;
 const p=plan(a);
 if(!p)return;
 renderResearch(a,root);
 const section=el("section","detail-section sim-detail");
 section.append(el("h3","","Simulación cuantificada · "+a.symbol));
 const header=el("div","sim-banner "+(p.mode==="ENTRADA_SOLO_PAPEL"?"sim-ready":"sim-paused"),
  p.mode==="ENTRADA_SOLO_PAPEL"?
  "Entrada simulada del radar (NO orden real): "+p.openUnits+" unidades":
  "Posición a abrir según la señal actual: 0 unidades");
 section.append(header);
 const current=p.plan||p.scenario;
 if(current){
  section.append(el("p","sim-intro",
    p.mode==="ENTRADA_SOLO_PAPEL"?
     "Plan de papel basado en el cierre y los niveles publicados. Actualizar con la próxima apertura antes de registrarlo.":
     "ESCENARIO HIPOTÉTICO, NO RECOMENDADO: si se estudiara una operación basada en el último cierre, soporte y ATR14. La estrategia no dio entrada."));
  const grid=el("div","sim-stats");
  amountRow(grid,"Entrada de referencia",cash(current.entry));
  amountRow(grid,"Stop hipotético",cash(current.stop));
  amountRow(grid,"Objetivo hipotético",cash(current.target));
  amountRow(grid,"Unidades en escenario",count(current.units));
  amountRow(grid,"Costo incl. gastos",cash(current.cost));
  amountRow(grid,"Pérdida si ejecuta al stop",cash(current.loss));
  amountRow(grid,"Resultado si ejecuta al objetivo",cash(current.gain));
  amountRow(grid,"R:R neta estimada",count(current.rr)+":1");
  section.append(grid);
  section.append(el("p","sim-foot","Capital usado: "+cash(capital)+" · Riesgo 0,5% · Exposición 20% por posición · Comisiones aprox. "+
    count(window.PULSOPositionMath.FEE*100)+"% y deslizamiento supuesto "+count(window.PULSOPositionMath.SLIP*100)+
    "% por lado · cierre de "+(p.referenceDate||"fecha desconocida")+". La pérdida real puede superar el stop."));
 }else{
  section.append(el("p","sim-intro","Sin suficientes datos verificables para calcular siquiera un escenario hipotético de entrada y salida."));
 }
 section.append(el("p","sim-foot","Próximo paso: "+p.reason));
 const jump=el("button","sim-link","Ver simulaciones de todos los activos");
 jump.type="button";jump.addEventListener("click",()=>$("positionSimulator")?.scrollIntoView({behavior:"smooth",block:"start"}));
 const see=el("button","sim-link sim-chart-link","Ver posición en el gráfico");
 see.type="button";see.addEventListener("click",()=>showChart(a.symbol));
 section.append(see);
  section.append(jump);root.append(section);
}
function filtered(){
 let rows=assets();
 if(filter==="chart")rows=rows.filter(a=>charts[a.symbol]?.bars?.length>=25);
 if(filter==="paper")rows=rows.filter(a=>a.recommendation?.code==="SIMULAR_ENTRADA");
 if(filter==="watch")rows=rows.filter(a=>s.watch?.has(a.symbol));
 if(search){const q=search.trim().toUpperCase();rows=rows.filter(a=>a.symbol.toUpperCase().includes(q));}
 return rows.sort((a,b)=>(b.recommendation?.code==="SIMULAR_ENTRADA")-
                         (a.recommendation?.code==="SIMULAR_ENTRADA") || (b.score||0)-(a.score||0));
}
function showChart(symbol){
 if(!assets().some(a=>a.symbol===symbol))return;
 document.dispatchEvent(new CustomEvent("byma:selection",{detail:{symbol}}));
 $("workstation")?.scrollIntoView({behavior:"smooth",block:"start"});
}
function showAsset(symbol){
 const a=assets().find(x=>x.symbol===symbol);if(!a)return;
 s.selected=symbol;s.filter="todos";s.assetType="todos";s.query=symbol;
 for(const [id,value] of [["assetType","todos"],["statusFilter","todos"],["search",symbol]]){
   if($(id))$(id).value=value;
 }
 if(typeof renderRows==="function")renderRows();
 if(typeof renderDetail==="function")renderDetail();
 $("detailPanel")?.scrollIntoView({behavior:"smooth",block:"start"});
}
function render(){
 const root=$("simPositionsBody");if(!root)return;root.replaceChildren();
 const rows=filtered();
 const plans=rows.map(a=>[a,plan(a)]);
 const eligible=plans.filter(([a,p])=>p?.mode==="ENTRADA_SOLO_PAPEL").length;
 const scenarios=plans.filter(([a,p])=>p?.scenario?.units>0).length;
 $("simCount").textContent=rows.length+" especies · "+eligible+" entradas de papel · "+scenarios+" escenarios calculables";
 $("simOpenCount").textContent=eligible+" entradas de papel";
 $("simCapitalLabel").textContent=cash(capital);
 $("simScenarioCount").textContent=scenarios+" hipótesis";
 if(!rows.length){
  const tr=el("tr"),td=el("td","sim-empty",filter==="paper"?
    "Sin señal RSI35 confirmada. No hay posiciones propuestas para abrir; corresponde esperar.":
    "No hay activos que cumplan este filtro. Elegí otra categoría o símbolo.");
  td.colSpan=12;tr.append(td);root.append(tr);return;
 }
 const maxShown=100;
 for(const [a,p] of plans.slice(0,maxShown)){
  const tr=el("tr");
  const inPaper=p?.mode==="ENTRADA_SOLO_PAPEL",scenario=p?.plan||p?.scenario;
  const values=[
    a.symbol+(a.kind==="cedear"?" · CD":""),
    inPaper?"PAPEL · pendiente apertura":"NO ABRIR",
    inPaper?count(p.openUnits)+" u.":"0 u.",
    scenario?cash(scenario.entry):"—",
    scenario?cash(scenario.stop):"—",
    scenario?cash(scenario.target):"—",
    scenario?count(scenario.units)+" u. (hip.)":"—",
    scenario?cash(scenario.cost):"—",
    scenario?cash(scenario.loss):"—",
    scenario?cash(scenario.gain):"—",
    scenario?count(scenario.rr)+":1":"—"
  ];
  values.forEach((value,i)=>tr.append(el("td",i===1?(inPaper?"sim-mark-ready":"sim-mark-muted"):"",value)));
  const buttonCell=el("td");
  const btn=el("button","sim-link","Ver ficha");
  btn.type="button";btn.addEventListener("click",()=>showAsset(a.symbol));
  const graph=el("button","sim-link sim-chart-link","Ver gráfico");
  graph.type="button";graph.addEventListener("click",()=>showChart(a.symbol));
  buttonCell.append(btn,graph);tr.append(buttonCell);root.append(tr);
 }
 $("simShowing").textContent="Mostrando "+Math.min(maxShown,rows.length)+" de "+rows.length+
  ". Para todas las especies, usá el buscador o exportá el CSV; los escenarios se calculan por separado, NO se suman como una cartera.";
}
function exportCSV(){
 const header=["simbolo","tipo","decision","unidades_abrir_papel","unidades_hipoteticas",
  "cierre_fecha","entrada_referencia","stop_hipotetico","objetivo_hipotetico",
  "costo_estimado","perdida_stop_estimada","ganancia_objetivo_estimada","rr_neta","motivo"];
 const q=x=>'"'+String(x??"").replace(/"/g,'""')+'"';
 const rows=[header];
 for(const a of assets()){
  const p=plan(a);const sc=p?.plan||p?.scenario;
  rows.push([a.symbol,a.kind,p?.mode||"NO_ABRIR",p?.openUnits||0,
    sc?.units??"",p?.referenceDate||"",sc?.entry??"",sc?.stop??"",sc?.target??"",
    sc?.cost??"",sc?.loss??"",sc?.gain??"",sc?.rr??"",p?.reason||""]);
 }
 const csv="\ufeff"+rows.map(r=>r.map(q).join(";")).join("\r\n");
 const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
 const anchor=document.createElement("a");anchor.href=url;anchor.download="pulso_simulaciones_por_activo.csv";
 anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function load(){
 const checks=await Promise.allSettled([
  fetch("./data/charts.json?positions="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():null),
  fetch("./data/quote_check.json?positions="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():null)
 ]);
 const j=checks[0].status==="fulfilled"?checks[0].value:null;
 if(j?.chart_data==="DAILY_HISTORICAL_ONLY_NOT_LIVE"&&j.symbols)charts=j.symbols;
 else{charts={};console.warn("PULSO historical feed unavailable");}
 cross=checks[1].status==="fulfilled"?checks[1].value:null;
 render();
 document.dispatchEvent(new CustomEvent("byma:positions"));
 if(typeof s!=="undefined"&&s.selected&&typeof renderDetail==="function")renderDetail();
}
function setup(){
 const capitalInput=$("positionCapital"),filterSelect=$("positionFilter"),searchInput=$("positionSearch");
 capitalInput?.addEventListener("input",()=>{
  const v=Number(capitalInput.value);
  if(!Number.isFinite(v)||v<1000||v>1e12){$("simCount").textContent="Ingresá capital entre $1.000 y $1 billón.";return;}
  capital=v;render();
  document.dispatchEvent(new CustomEvent("byma:positions"));
  if(s.selected&&typeof renderDetail==="function")renderDetail();
 });
 filterSelect?.addEventListener("change",()=>{filter=filterSelect.value;render()});
 searchInput?.addEventListener("input",()=>{search=searchInput.value;render()});
 $("positionExport")?.addEventListener("click",exportCSV);
 document.addEventListener("byma:data",render);
 document.addEventListener("byma:advisor",render);
 load();
}
window.PULSOPositions={renderAsset,plan,render,exportCSV};
setup();
})();
