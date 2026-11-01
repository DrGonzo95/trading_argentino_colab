"use strict";
/* PULSO – per-asset position simulator. No auto trades; no fake fills.
 * Uses price history for WHAT-IF calculations, not investment advice. */
(()=>{
const $=id=>document.getElementById(id);
const fmt=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const cash=x=>typeof x==="number"&&Number.isFinite(x)?"$ "+fmt.format(x):"—";
const count=x=>typeof x==="number"&&Number.isFinite(x)?fmt.format(x):"—";
let charts={};let capital=100000;let filter="chart";let search="";
function assets(){try{return Array.isArray(s.items)?s.items:[]}catch{return []}}
function el(tag,css,text){const n=document.createElement(tag);if(css)n.className=css;if(text!==undefined)n.textContent=String(text);return n}
function plan(a){return window.PULSOPositionMath?.assess(a,charts[a.symbol],capital)||null}
function riskBadge(rec){
 return rec?.mode==="ENTRADA_SOLO_PAPEL"?"Abrir en PAPEL":"0 unidades a abrir";
}
function amountRow(parent,name,val){
 const item=el("div","sim-stat");item.append(el("span","",name),el("strong","",val));parent.append(item);
}
function renderAsset(a,root){
 if(!a||!root)return;
 const p=plan(a);
 if(!p)return;
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
     "ESCENARIO HIPOTÉTICO, NO RECOMENDADO: si se estudiara una operación basada en el último cierre y ATR14. La estrategia no dio entrada."));
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
  td.colSpan=9;tr.append(td);root.append(tr);return;
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
    scenario?cash(scenario.loss):"—"
  ];
  values.forEach((value,i)=>tr.append(el("td",i===1?(inPaper?"sim-mark-ready":"sim-mark-muted"):"",value)));
  const buttonCell=el("td");
  const btn=el("button","sim-link","Ver ficha");
  btn.type="button";btn.addEventListener("click",()=>showAsset(a.symbol));
  buttonCell.append(btn);tr.append(buttonCell);root.append(tr);
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
 try{
  const r=await fetch("./data/charts.json?positions="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw Error("No se pudo cargar histórico");
  const j=await r.json();
  if(j.chart_data!=="DAILY_HISTORICAL_ONLY_NOT_LIVE"||!j.symbols)throw Error("Histórico inválido");
  charts=j.symbols;
 }catch(e){console.warn("PULSO scenarios require historical feed",e);charts={};}
 render();
 if(typeof s!=="undefined"&&s.selected&&typeof renderDetail==="function")renderDetail();
}
function setup(){
 const capitalInput=$("positionCapital"),filterSelect=$("positionFilter"),searchInput=$("positionSearch");
 capitalInput?.addEventListener("input",()=>{
  const v=Number(capitalInput.value);
  if(!Number.isFinite(v)||v<1000||v>1e12){$("simCount").textContent="Ingresá capital entre $1.000 y $1 billón.";return;}
  capital=v;render();
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
