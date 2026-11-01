"use strict";
/* PULSO PRO: no synthetic market observations. Every price comes from published delayed market.json.
   Chart availability comes only from chart JSON. Backtest panel comes only from strategy_audit.json. */
(()=>{
const id=x=>document.getElementById(x);
const fmt=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const datefmt=new Intl.DateTimeFormat("es-AR",{dateStyle:"short",timeStyle:"short",timeZone:"America/Argentina/Cordoba"});
const n=x=>Number.isFinite(Number(x))&&x!==null&&x!==undefined?fmt.format(Number(x)):"—";
const cls=x=>Number(x)<0?"pro-neg":Number(x)>0?"pro-pos":"";
let history={},audit=null,quoteCheck=null,forwardData=null,mode="destacados",active=null,chartsReady=false;
function node(tag,className,txt){const e=document.createElement(tag);if(className)e.className=className;if(txt!==undefined)e.textContent=txt;return e;}
function setText(element,value){if(element)element.textContent=value;}
function items(){try{return typeof s!=="undefined"&&Array.isArray(s.items)?s.items:[];}catch(_){return [];}}
function hasChart(sym){return !!history[sym]?.bars?.length}
function current(){return items().find(x=>x.symbol===active)||null}
function scoreStatus(x){
  if(x.recommendation?.label)return x.recommendation.label;
  if(x.status==="ENTRADA_TEORICA_PAPEL")return "Papel: verificar apertura";
  if(x.status==="CAIDA_CON_NOVEDAD_INVESTIGAR")return "Investigar hecho, sin entrada";
  if(x.status==="VIGILANCIA_TECNICA")return "Vigilar condiciones";
  if(x.status==="NOVEDAD_OFICIAL")return "Noticia oficial, no señal";
  return "Seguimiento, sin señal";
}
function getRows(){
 const all=items().filter(x=>x.kind==="accion"||x.kind==="cedear");
 if(mode==="favoritos")return all.filter(x=>s.watch.has(x.symbol)).sort((a,b)=>b.score-a.score).slice(0,16);
 if(mode==="velas")return all.filter(x=>hasChart(x.symbol)).sort((a,b)=>b.score-a.score).slice(0,16);
 if(mode==="entradas")return all.filter(x=>x.status==="ENTRADA_TEORICA_PAPEL").sort((a,b)=>b.score-a.score).slice(0,16);
 return all.filter(x=>x.score>0&&(x.status==="CAIDA_CON_NOVEDAD_INVESTIGAR"||x.status==="ENTRADA_TEORICA_PAPEL"||hasChart(x.symbol))).sort((a,b)=>b.score-a.score).slice(0,12);
}
function inspect(symbol){
 active=symbol;
 const row=items().find(x=>x.symbol===symbol);
 if(row){
   s.selected=symbol;s.assetType="todos";s.filter="todos";s.query=symbol;
   if(id("assetType"))id("assetType").value="todos";
   if(id("statusFilter"))id("statusFilter").value="todos";
   if(id("search"))id("search").value=symbol;
   renderRows();window.renderDetail?.();
 }else document.dispatchEvent(new CustomEvent("byma:selection",{detail:{symbol}}));
 render();
 id("workstation")?.scrollIntoView({behavior:"smooth",block:"start"});
}
function renderCards(){
 const board=id("proBoard");if(!board)return;board.replaceChildren();
 const rows=getRows();
 if(!rows.length){
   board.appendChild(node("p","pro-detail",mode==="entradas"?"No hay señales de entrada que cumplan todas las reglas. Es correcto no operar.":mode==="favoritos"?"Todavía no guardaste activos. Entrá en una ficha y usá «Seguir».":"No hay históricos verificables para el filtro elegido."));return;
 }
 for(const x of rows){
   const b=node("button","pro-asset"+(x.symbol===active?" active":""));b.type="button";
   b.setAttribute("aria-label","Analizar "+x.symbol);
   const top=node("span","pro-asset-top"),symbol=node("span","pro-asset-title",x.symbol);
   const flag=node("span","pro-smallbadge"+(hasChart(x.symbol)?" available":""),hasChart(x.symbol)?"VELAS 1D":"SIN GRÁFICO");
   top.append(symbol,flag);
   const price=node("span","pro-asset-price",x.quote_price==null?"Precio no validado":"$ "+n(x.quote_price));
   const ch=node("span","pro-asset-change "+cls(x.change_pct),x.change_pct==null?"Var. —":(Number(x.change_pct)>0?"+":"")+n(x.change_pct)+"% · prioridad "+n(x.score));
   const desc=node("span","pro-detail",scoreStatus(x));
   const next=node("span","pro-asset-next",x.recommendation?.next_step||"Todavía no se publicó una evaluación con fuentes cotejadas.");
   const action=node("span","pro-action-tag "+(x.recommendation?.category||"sin_datos"),x.recommendation?.label||"Pendiente de evaluar");
   b.append(top,price,ch,action,desc,next);b.addEventListener("click",()=>inspect(x.symbol));board.append(b);
 }
}
function link(url,title){
 const a=node("a","",title);
 if(typeof url==="string"&&/^https:\/\//.test(url)){a.href=url;a.target="_blank";a.rel="noopener noreferrer";return a}
 return null;
}
function setAudit(){
 const root=id("proAuditStats");if(!root)return;root.replaceChildren();
 if(!audit){
   root.appendChild(node("p","pro-method","Auditoría histórica todavía no publicada; sin evidencia para afirmar rentabilidad."));return;
 }
 const test=audit.test||{};const train=audit.train||{};
 const fields=[
   ["Prueba fuera de muestra",n(test.trades)+" operaciones"],
   ["Aciertos netos",test.win_rate_pct==null?"Sin muestra":n(test.win_rate_pct)+"%"],
   ["Retorno neto promedio",test.mean_net_pct==null?"Sin muestra":n(test.mean_net_pct)+"%"],
   ["Factor de beneficio",test.profit_factor==null?"No calculable":n(test.profit_factor)],
   ["Caída máxima teórica",test.max_drawdown_pct==null?"Sin muestra":n(test.max_drawdown_pct)+"%"],
   ["Especies aptas",n(audit.valid_symbols)+" / "+n(audit.history_sources)]
 ];
 const grid=node("div","pro-risk-grid");
 fields.forEach(([name,val])=>{const b=node("div","pro-riskstat");b.append(node("span","",name),node("strong","",val));grid.append(b);});
 root.append(grid);
 root.append(node("p","pro-method",
  "Entrenamiento: "+n(train.trades)+" operaciones · corte cronológico: "+(audit.split_date||"no disponible")+
  ". Comisión estimada por lado "+n(audit.assumptions?.commission_iva_each_side_pct)+"% + deslizamiento "+n(audit.assumptions?.slippage_each_side_pct)+"%. Stop conservador antes del objetivo en velas ambiguas. "+
  "Son resultados por operación, NO rentabilidad de una cartera."));
 const states=forwardData?.portfolio_tracking||{};
 const fwd=states["100000"]||states["50000"]||null;
 if(fwd){
   root.append(node("p","pro-method",
    "SEGUIMIENTO PROSPECTIVO: "+n(fwd.closed_or_recorded_orders)+" operaciones registradas, "+
    n(fwd.open_positions)+" posiciones abiertas y "+n(fwd.pending_entries)+" pendientes"+
    " · última rueda procesada "+(forwardData.last_processed_session||"no disponible")+
    ". No se infiere rentabilidad con una muestra insuficiente."));
 }else root.append(node("p","pro-method","Seguimiento prospectivo todavía no publicado; no se supone ningún trade."));
 root.append(node("p","pro-nochart",
  "ESTRATEGIA NO VALIDADA. "+(audit.conclusion||"Sin evidencia suficiente.")+
  " La muestra sufre sesgo de selección y no dispone de spread ni precios ajustados de forma independiente."));
}
function renderSignal(){
 const a=current();const root=id("proSignal");if(!root)return;root.replaceChildren();
 if(!a){root.appendChild(node("p","", "Seleccioná una especie para interpretar la señal publicada."));return;}
 root.appendChild(node("h3","",a.symbol+" · "+(a.kind==="accion"?"acción":"CEDEAR")));
 root.appendChild(node("p","",scoreStatus(a)+". Precio público diferido: "+(a.quote_price==null?"sin valor":"$ "+n(a.quote_price))+"."));
 const rec=a.recommendation;
 if(rec){
   const explain=node("div","pro-recommendation");
   explain.append(node("span","pro-action-tag "+(rec.category||"sin_datos"),rec.label||"Sin evaluar"));
   (rec.reasons||[]).forEach(reason=>explain.append(node("p","pro-rec-reason",reason)));
   explain.append(node("strong","pro-rec-step","Próximo paso: "+(rec.next_step||"Esperar datos.")));
   explain.append(node("p","pro-method",rec.independent_verified?
     "Cierre histórico confirmado contra segundo proveedor. No equivale a un precio de ejecución.":
     "Cierre todavía no corroborado contra un segundo proveedor para la misma fecha."));
   root.append(explain);
 }
 const finalBar=hasChart(a.symbol)?history[a.symbol].bars.at(-1):null;
 const quoteGap=finalBar&&a.quote_price!=null?100*Math.abs(Number(a.quote_price)-finalBar[4])/finalBar[4]:null;
 const verifiedSecond=quoteCheck?.prices?.[a.symbol];
 const verifiedMessage=verifiedSecond?
   ("IOL $ "+n(verifiedSecond.historical_close)+" vs Gio Bursátil $ "+n(verifiedSecond.independent_close)+
    " · "+verifiedSecond.market_date+" · "+n(verifiedSecond.difference_pct)+"% · "+
    (verifiedSecond.status==="MATCH"?"Coincidencia (no precio ejecutable)":"DISCREPANCIA: investigar")):
   "No disponible para esta especie o fecha; sin confirmación de segundo proveedor";
 const checks=[
  ["Segundo proveedor (cierre)",verifiedMessage],
  ["Concordancia interna",quoteGap===null?"No comparable: falta precio o histórico":
    "Cierre histórico $ "+n(finalBar[4])+" ("+finalBar[0]+") vs panel $ "+n(a.quote_price)+
    " · diferencia "+n(quoteGap)+"%. "+(quoteGap>.5?"DESAJUSTE, no operar.":"Coincidencia interna, no cotejo independiente.")],
  ["Histórico diario",hasChart(a.symbol)?"Sí, "+history[a.symbol].bars.length+" velas; última "+history[a.symbol].last_candle:"No disponible / no validado"],
  ["RSI (14)",a.rsi14==null?"Sin cálculo validado":n(a.rsi14)],
  ["Calidad técnica",a.technical_score==null?"Sin puntuación técnica":n(a.technical_score)+"/100"],
  ["Precio negociable", "NO verificado (hora de operación y puntas no confirmadas)"],
  ["Catalizador",a.events?.length?(a.events.filter(e=>e.source==="CNV_OFICIAL").length+" publicaciones CNV entre "+a.events.length+" novedades"):"Sin noticia asociada verificable"],
  ["Entrada / stop / objetivo",a.status==="ENTRADA_TEORICA_PAPEL"&&[a.entry_ref,a.stop_ref,a.target_ref].every(x=>x!=null)?
      "$ "+n(a.entry_ref)+" / $ "+n(a.stop_ref)+" / $ "+n(a.target_ref)+" (solo papel)": "No hay setup validado para abrir posición"]
 ];
 checks.forEach(([k,v])=>{const line=node("div","pro-source-row");line.append(node("strong","",k+": "),node("span","",v));root.append(line);});
 if(!hasChart(a.symbol)){root.append(node("p","pro-nochart",
   "Sin OHLCV validado para graficar este activo. Se muestran solamente los datos conocidos; no se generarán velas sintéticas."));}
 if(a.events?.length){
   const refs=node("div","pro-source-row");
   a.events.slice(0,3).forEach(e=>{const el=link(e.url,(e.source==="CNV_OFICIAL"?"CNV: ":"Noticia: ")+(e.title||"Documento").slice(0,85));if(el)refs.append(el);});
   root.append(refs);
 }
 const actions=node("div","pro-source-row");
 const details=node("button","pro-cta","Abrir ficha completa y noticias");
 details.type="button";details.addEventListener("click",()=>{
   s.selected=a.symbol;s.assetType="todos";s.filter="todos";s.query=a.symbol;
   id("assetType").value="todos";id("statusFilter").value="todos";id("search").value=a.symbol;
   renderRows();window.renderDetail?.();
   id("detailPanel")?.scrollIntoView({behavior:"smooth",block:"start"});
 });
 const watch=node("button","pro-cta",s.watch.has(a.symbol)?"★ Quitar seguimiento":"☆ Guardar seguimiento");
 watch.type="button";watch.addEventListener("click",()=>{
   if(s.watch.has(a.symbol))s.watch.delete(a.symbol);else s.watch.add(a.symbol);
   persist("byma-watch-v1",Array.from(s.watch));render();
 });
 actions.append(details,watch);root.append(actions);
}
function render(){
 if(!id("proBoard"))return;
 const data=items();
 if(!active&&data.length){active=(getRows()[0]||data.find(x=>hasChart(x.symbol))||data[0]).symbol;}
 setText(id("proCoverage"),data.length+" catalogados · "+data.filter(x=>x.technical_score!=null).length+" con técnico · "+Object.keys(history).length+" con velas");
 const time=s?.meta?.generated_at ? new Date(s.meta.generated_at) :null;
 const label=time&&Number.isFinite(time.getTime())?datefmt.format(time)+" (exportación; hora de negociación desconocida)":"sin hora verificable";
 setText(id("proFreshness"),"Última exportación: "+label);
 renderCards();renderSignal();setAudit();
}
function setup(){
 const root=id("proTerminal");if(!root)return;
 root.innerHTML="";
 const head=node("div","pro-head"),title=node("div");
 title.append(node("span","kicker","PULSO TERMINAL · INVESTIGACIÓN / PAPEL"),node("h2","","Monitor profesional de señales y activos"),
   node("p","","Separá qué observar, qué está confirmado y qué no puede operarse. Siempre con datos públicos demorados; sin simulación de cotizaciones."));
 const nav=node("div","pro-source-row");
 const graph=node("button","pro-cta","◉ Ver gráfico de velas");
 graph.type="button";graph.addEventListener("click",()=>id("workstation")?.scrollIntoView({behavior:"smooth",block:"start"}));
 const portfolio=node("button","pro-cta","▤ Cartera simulada");
 portfolio.type="button";portfolio.addEventListener("click",()=>id("paper")?.scrollIntoView({behavior:"smooth",block:"start"}));
 const all=node("button","pro-cta","☷ Ver recomendaciones de todos");
 all.type="button";all.addEventListener("click",()=>{
   if(id("statusFilter"))id("statusFilter").value="todos";
   if(id("assetType"))id("assetType").value="acciones-cedears";
   if(id("search"))id("search").value="";
   s.filter="todos";s.assetType="acciones-cedears";s.query="";
   s.show=55;renderRows();
   document.querySelector(".work-area")?.scrollIntoView({behavior:"smooth",block:"start"});
 });
 nav.append(graph,portfolio,all);
 title.append(nav);
 head.append(title,node("span","pro-livepill","● DATOS DIFERIDOS · NO LIVE"));root.append(head);
 const main=node("div","pro-body"),bar=node("div","pro-controlbar"),switches=node("div","pro-switches");
 for(const [value,label] of [["destacados","En observación"],["velas","Con gráficos"],["entradas","Entradas de papel"],["favoritos","★ Mi seguimiento"]]){
   const b=node("button","",label);b.type="button";b.setAttribute("aria-pressed",String(value===mode));
   b.addEventListener("click",()=>{mode=value;switches.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));renderCards();});
   switches.append(b);
 }
 bar.append(switches,node("span","pro-coverage", "Comprobando cobertura…"));bar.lastChild.id="proCoverage";
 main.append(bar);
 const board=node("div","pro-board");board.id="proBoard";main.append(board);
 const foot=node("div","pro-audit");
 const signal=node("section","pro-panel");signal.id="proSignal";
 const auditBox=node("section","pro-panel");auditBox.append(node("h3","","Auditoría de la estrategia RSI35"),node("p","",
   "Backtest cronológico: señal al cierre, entrada al abrir la rueda siguiente, stop y objetivo con ATR. Comisión y deslizamiento descontados."));
 const stats=node("div","");stats.id="proAuditStats";auditBox.append(stats);
 const source=node("div","pro-source-row"),linkA=link("https://www.byma.com.ar/productos/productos-de-datos/market-data/apis","API y latencias de BYMA");
 if(linkA)source.append(linkA);
 const linkB=link("https://github.com/DrGonzo95/trading_argentino_colab/blob/main/radar_byma/strategy_audit.py","Código reproducible de la prueba");
 if(linkB)source.append(linkB);
 auditBox.append(source);
 foot.append(signal,auditBox);main.append(foot);
 const meta=node("p","pro-method",""),tm=node("span","pro-time");tm.id="proFreshness";meta.append(tm);
 main.append(meta);root.append(main);
}
async function load(){
 try{
 const response=await fetch("./data/charts.json?pro="+Date.now(),{cache:"no-store"});
 if(!response.ok)throw Error("HTTP "+response.status);
 const json=await response.json();
 if(json.chart_data!=="DAILY_HISTORICAL_ONLY_NOT_LIVE"||!json.symbols)throw Error("Formato inválido");
 history=Object.fromEntries(Object.entries(json.symbols).filter(([sym,x])=>
  Array.isArray(x.bars)&&x.bars.length>1&&x.bars.every(b=>
   Array.isArray(b)&&b.length===6&&Number.isFinite(b[1])&&
   b[2]>=Math.max(b[1],b[4])&&b[3]<=Math.min(b[1],b[4])&&b[5]>=0)));
 chartsReady=true;
 }catch(e){console.warn("PRO charts",e);chartsReady=false;history={};}
 try{const response=await fetch("./data/forward_status.json?pro="+Date.now(),{cache:"no-store"});
  if(response.ok){const j=await response.json();if(j.kind==="FORWARD_LEDGER_ONLY")forwardData=j;}
 }catch(e){console.warn("PRO forward status not available",e);}
 try{const response=await fetch("./data/quote_check.json?pro="+Date.now(),{cache:"no-store"});
  if(response.ok){const j=await response.json();quoteCheck=j;}
 }catch(e){console.warn("PRO second provider not available",e);}
 try{const response=await fetch("./data/strategy_audit.json?pro="+Date.now(),{cache:"no-store"});
   if(response.ok){const j=await response.json();if(j.version==="frozen-rsi35-v1")audit=j;}
 }catch(e){console.warn("PRO audit pending",e);}
 render();
}
setup();load();
document.addEventListener("byma:data",render);
document.addEventListener("byma:selection",e=>{active=e.detail?.symbol||active;render();});
document.addEventListener("change",e=>{if(e.target?.id==="chartSymbolPicker"){active=e.target.value;render();}});
})();
