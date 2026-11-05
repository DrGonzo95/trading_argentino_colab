"use strict";
const $=(id)=>document.getElementById(id);
const TZ="America/Argentina/Cordoba";
const formatNumber=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const formatMoney=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2,minimumFractionDigits:2});
const statusNames={
  "ENTRADA_TEORICA_PAPEL":"Entrada de papel",
  "CAIDA_CON_NOVEDAD_INVESTIGAR":"Caída + novedad",
  "VIGILANCIA_TECNICA":"Vigilancia técnica",
  "NOVEDAD_OFICIAL":"Hecho relevante",
  "SOLO_SEGUIMIENTO":"Observación"
};
const statusStyles={
  "ENTRADA_TEORICA_PAPEL":"paper","CAIDA_CON_NOVEDAD_INVESTIGAR":"catalyst",
  "VIGILANCIA_TECNICA":"technical","NOVEDAD_OFICIAL":"official",
  "SOLO_SEGUIMIENTO":""
};
const classes={"accion":"Acción argentina","cedear":"CEDEAR","bono":"Bono","on":"Obligación negociable"};
const s={items:[],meta:{},summary:{},selected:null,show:55,
  query:"",assetType:"acciones-cedears",filter:"relevantes",watch:new Set(),paper:[],
  latestFetch:0,paperSymbol:null};
function stored(key,fallback){
  try{const value=JSON.parse(localStorage.getItem(key));return value===null?fallback:value;}
  catch(e){return fallback;}
}
function persist(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch(e){console.warn("Almacenamiento local no disponible");}}
s.watch=new Set(stored("byma-watch-v1",[]));
s.paper=stored("byma-paper-v1",[]);
function el(type,css,text){
  const n=document.createElement(type);if(css)n.className=css;
  if(text!==undefined&&text!==null)n.textContent=String(text);
  return n;
}
function append(parent,...children){children.forEach(c=>{if(c)parent.appendChild(c);});return parent;}
function num(v){return v===null||v===undefined||!Number.isFinite(Number(v))?"—":formatNumber.format(Number(v));}
function money(v){return v===null||v===undefined||!Number.isFinite(Number(v))?"—":formatMoney.format(Number(v));}
function signed(v){if(v===null||v===undefined||!Number.isFinite(Number(v)))return "—";return (Number(v)>0?"+":"")+num(v)+"%";}
function kindName(v){return classes[v]||v;}
function pill(status){return el("span","chip "+(statusStyles[status]||""),statusNames[status]||"Solo observar");}
function scanTime(iso){
  if(!iso)return "Fecha no disponible";
  const d=new Date(iso);if(!Number.isFinite(d.getTime()))return "Hora no válida";
  return d.toLocaleString("es-AR",{timeZone:TZ,day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false})+" h";
}
function age(iso){
  if(!iso)return null;
  const ms=Date.now()-new Date(iso).getTime();
  return Number.isFinite(ms)?Math.round(ms/60000):null;
}
function clock(){
  $("marketClock").textContent=new Date().toLocaleTimeString("es-AR",{timeZone:TZ,hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false})+" ARG";
  const a=age(s.meta.generated_at);
  if(a===null){$("freshness").textContent="No hay datos publicados";return;}
  $("freshness").textContent=a<2?"Exportación reciente":("Datos exportados hace "+(a<120?a+" minutos":Math.round(a/60)+" horas"));
  const stale=a>55;
  const connection=$("connection").parentElement;
  connection.classList.toggle("is-error",stale||!s.meta.data_reliable);
  $("connection").textContent=stale?"Datos antiguos":s.meta.data_reliable?"Radar diferido":"Fuente parcial";
}
function refreshClock(){clock();}
function setStats(){
  $("statTotal").textContent=num(s.summary.total);
  $("statSignals").textContent=num(s.summary.paper_setups);
  $("statCatalysts").textContent=num(s.summary.watch_catalyst);
  $("statTech").textContent=num(s.summary.validated_tech);
  $("lastUpdate").textContent=scanTime(s.meta.source_snapshot_at||s.meta.generated_at);
  const failures=Object.keys(s.meta.provider_errors||{}).length;
  $("scanSummary").textContent=failures?failures+" fuentes parciales / no disponibles":"Última descarga · no hora de la operación";
  clock();
}
function filterItems(){
  const q=s.query.trim().toUpperCase();
  const filt=s.filter;const kind=s.assetType;
  return s.items.filter((r)=>{
    if(q&&!r.symbol.toUpperCase().includes(q))return false;
    if(kind==="acciones-cedears"&&r.kind!=="accion"&&r.kind!=="cedear")return false;
    if(kind!=="acciones-cedears"&&kind!=="todos"&&r.kind!==kind)return false;
    if(filt==="paper")return r.status==="ENTRADA_TEORICA_PAPEL";
    if(filt==="caidas")return r.status==="CAIDA_CON_NOVEDAD_INVESTIGAR";
    if(filt==="tecnicos")return r.technical_score!==null&&r.technical_score!==undefined;
    if(filt==="watch")return s.watch.has(r.symbol);
    if(filt==="decision_papel")return r.recommendation?.code==="SIMULAR_ENTRADA";
    if(filt==="decision_investigar")return ["INVESTIGAR_CAIDA","REVISAR_CNV"].includes(r.recommendation?.code);
    if(filt==="decision_esperar")return ["ESPERAR_TECNICO","ESPERAR_DATOS","REVISAR_DISCREPANCIA","ESPERAR_FUENTES","ESPERAR_VALIDACION"].includes(r.recommendation?.code);
    if(filt==="decision_vigilar")return ["VIGILAR_TECNICA","OBSERVAR"].includes(r.recommendation?.code);
    if(filt==="relevantes")return r.score>0;
    return true;
  });
}
function researchRec(r){
  return r?.recommendation||{code:"NO_EVALUADO",label:"Sin evaluación publicada",category:"sin_datos",
    reasons:["No hay evaluación actual verificable para esta especie."],
    next_step:"Actualizar el radar y revisar fecha y calidad de precios.",
    price_quality:"SOLO_FUENTE_PRINCIPAL"};
}
function recPill(r){
  const rec=researchRec(r);
  const chip=el("span","rec-pill "+(rec.category||"observacion"),rec.label);
  chip.title=rec.next_step||"";
  return chip;
}
function makeRow(r){
  const tr=el("tr","table-row"+(r.symbol===s.selected?" selected":""));
  tr.tabIndex=0;tr.setAttribute("aria-label","Ver "+r.symbol+" y sus datos");
  const first=el("td");append(first,el("span","ticker",r.symbol),el("span","ticker-kind",kindName(r.kind)));
  const quote=el("td","num",r.quote_price===null?"—":money(r.quote_price));
  const change=el("td","num "+(r.change_pct<0?"red":r.change_pct>0?"green":"muted"),signed(r.change_pct));
  const rank=el("td");const score=el("div","rank-bar");const track=el("div","rank-track");const fill=el("div","rank-fill");
  fill.style.width=Math.max(0,Math.min(100,Number(r.score)||0))+"%";
  append(track,fill);append(score,track,el("span","rank-number",num(r.score)));rank.appendChild(score);
  const stat=el("td");stat.appendChild(pill(r.status));
  const action=el("td");action.appendChild(recPill(r));
  const last=el("td","open-chevron","›");
  append(tr,first,quote,change,rank,stat,action,last);
  const select=()=>{s.selected=r.symbol;renderRows();renderDetail();if(window.innerWidth<901)$("detailPanel").scrollIntoView({behavior:"smooth",block:"start"});};
  tr.addEventListener("click",select);
  tr.addEventListener("keydown",(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select();}});
  return tr;
}
function renderRows(){
  const rows=filterItems();const body=$("assetsBody");body.replaceChildren();
  const visible=rows.slice(0,s.show);
  if(!visible.length){const tr=el("tr");const td=el("td","empty","No hay instrumentos que cumplan estos filtros. Probá otra búsqueda o seleccioná “Ver todos”.");td.colSpan=7;tr.appendChild(td);body.appendChild(tr);}
  else{const frag=document.createDocumentFragment();visible.forEach(r=>frag.appendChild(makeRow(r)));body.appendChild(frag);}
  $("matches").textContent=num(rows.length)+" resultados";
  $("paginationInfo").textContent="Mostrando "+num(visible.length)+" de "+num(rows.length);
  $("loadMore").hidden=rows.length<=s.show;
}
function dataTile(name,value,style){
  const card=el("div","data-item");append(card,el("small","",name),el("strong",style||"",value));return card;
}
function section(root,title){
  const div=el("section","detail-section");div.appendChild(el("h3","",title));root.appendChild(div);return div;
}
function infoRow(root,label,value,css){
  const item=el("div","small-rows");append(item,el("span","",label),el("span",css||"",value));root.appendChild(item);
}
function note(root,value,isWarn){
  root.appendChild(el("div","note"+(isWarn?" warn":""),value));
}
function importantSignals(){
  return s.items
    .filter(x=>x.status==="ENTRADA_TEORICA_PAPEL"||
               x.status==="CAIDA_CON_NOVEDAD_INVESTIGAR")
    .sort((a,b)=>(a.status==="ENTRADA_TEORICA_PAPEL"?0:1)-
                  (b.status==="ENTRADA_TEORICA_PAPEL"?0:1)||b.score-a.score)
    .slice(0,14);
}
function alertIdentity(x){
  // Same signal is NOT new merely because provider gets re-scraped.
  const mostRecent=(x.events||[])[0];
  const freshNews=mostRecent?(mostRecent.url||mostRecent.published||""):"";
  const day=x.daily_bar_date||String(s.meta.generated_at||"").slice(0,10);
  return [x.kind,x.symbol,x.status,day,freshNews].join("|");
}
function alertTitle(x){
  return (x.status==="ENTRADA_TEORICA_PAPEL"?"🧪 Entrada para simulación: ":"🔎 Caída + novedad: ")+x.symbol;
}
function renderAlerts(){
  const items=importantSignals();
  const container=$("alertsList");container.replaceChildren();
  $("alertCount").textContent=String(items.length);
  if(!items.length){
    container.appendChild(el("div","alert-placeholder",
      "No hay entradas de papel ni caídas con novedades en el último escaneo. No se generan alertas sin una condición concreta."));
    return;
  }
  const seen=new Set(stored("byma-alerts-seen-v1",[]));
  const ids=items.map(alertIdentity);
  const firstVisit=stored("byma-alerts-seen-v1",null)===null;
  const newlyObserved=items.filter(x=>!seen.has(alertIdentity(x)));
  const snapshotAge=age(s.meta.generated_at);
  const canNotify=!firstVisit&&snapshotAge!==null&&snapshotAge>=0&&snapshotAge<=55&&
       typeof Notification!=="undefined"&&Notification.permission==="granted";
  if(canNotify){
    newlyObserved.filter(x=>x.status==="ENTRADA_TEORICA_PAPEL" ||
      (x.status==="CAIDA_CON_NOVEDAD_INVESTIGAR" && x.events_official>0 && x.score>=32)
      ).slice(0,3).forEach(x=>{
      try{
        const confirmed=x.status==="ENTRADA_TEORICA_PAPEL";
        new Notification(alertTitle(x),{
          body:confirmed?
            "Entrada hipotética basada en vela diaria. NO precio vivo. Revisá stop, objetivo, liquidez y fecha.":
            "Caída con hecho oficial coincidente. AÚN SIN ENTRADA; analizar noticia y confirmar eventual rebote.",
          tag:"byma-alert-"+x.symbol+"-"+x.status
        });
      }catch(error){console.warn("Notificación bloqueada",error);}
    });
  }
  // Retain last known alert identity keys, not every continuously refreshed quote.
  persist("byma-alerts-seen-v1",Array.from(new Set([...seen,...ids])).slice(-350));
  for(const x of items){
    const button=el("button","alert-item");button.type="button";
    const tag=el("span","chip "+(statusStyles[x.status]||""),statusNames[x.status]);
    const left=el("span","alert-content");
    const title=el("strong","",x.symbol+" · "+kindName(x.kind));
    const info=el("span","alert-info",
      x.status==="ENTRADA_TEORICA_PAPEL"?
        "Entrada ref. "+money(x.entry_ref)+" · stop "+money(x.stop_ref)+" · objetivo "+money(x.target_ref):
        "Variación pública "+signed(x.change_pct)+" · noticia asociada; rebote NO confirmado");
    append(left,title,info);
    const right=el("span","alert-right");append(right,tag,el("span","alert-see","Ver ficha ›"));
    append(button,left,right);
    if(!firstVisit&&!seen.has(alertIdentity(x)))button.classList.add("alert-new");
    button.addEventListener("click",()=>{
      s.selected=x.symbol;s.assetType="todos";s.filter="todos";s.query=x.symbol;
      $("assetType").value="todos";$("statusFilter").value="todos";$("search").value=x.symbol;
      renderRows();renderDetail();$("detailPanel").scrollIntoView({behavior:"smooth",block:"start"});
    });
    container.appendChild(button);
  }
}
function updateNotificationButton(){
  const b=$("enableNotifications");
  if(!("Notification" in window)){
    b.textContent="Avisos del navegador no compatibles";b.disabled=true;return;
  }
  if(Notification.permission==="granted")b.textContent="✓ Avisos activos (página abierta)";
  else if(Notification.permission==="denied"){
    b.textContent="Avisos bloqueados por el navegador";b.disabled=true;
  }else b.textContent="♧ Activar avisos en este navegador";
}
async function requestAlerts(){
  if(!("Notification" in window))return;
  try{
    const permission=await Notification.requestPermission();
    updateNotificationButton();
    if(permission==="granted")
      alert("Se avisará de nuevas ENTRADAS DE PAPEL y caídas destacadas con documento oficial mientras la página permanezca abierta. No es push en segundo plano.");
  }catch(e){console.warn("No se pudo habilitar el permiso de aviso",e);}
}
function renderDetail(){
  const root=$("detailPanel");root.replaceChildren();
  const a=s.items.find(x=>x.symbol===s.selected);
  if(a)document.dispatchEvent(new CustomEvent("byma:selection",{detail:{symbol:a.symbol}}));
  if(!a){const empty=el("div","detail-placeholder");append(empty,el("div","symbol-art","⌁"),el("h3","","Elegí un instrumento"),el("p","","Seleccioná una fila para ver el análisis, niveles de referencia y simulador."));root.appendChild(empty);return;}
  const head=el("div","detail-head");const title=el("div");append(title,el("span","kicker",kindName(a.kind).toUpperCase()),el("h2","detail-symbol",a.symbol));head.appendChild(title);
  const watch=el("button","watch-btn"+(s.watch.has(a.symbol)?" active":""),s.watch.has(a.symbol)?"★ Siguiendo":"☆ Seguir");
  watch.type="button";watch.addEventListener("click",()=>{
    if(s.watch.has(a.symbol))s.watch.delete(a.symbol);else s.watch.add(a.symbol);
    persist("byma-watch-v1",Array.from(s.watch));renderDetail();if(s.filter==="watch")renderRows();
  });
  head.appendChild(watch);root.appendChild(head);
  const badge=el("div","detail-status");badge.appendChild(pill(a.status));root.appendChild(badge);
  const price=el("div","detail-price");const top=el("div","detail-price-top");const priceCol=el("div");
  append(priceCol,el("div","caption","ÚLTIMO PRECIO DE PANEL*"),el("strong","",money(a.quote_price)));
  append(top,priceCol,el("span","change "+(a.change_pct<0?"red":"green"),signed(a.change_pct)));
  append(price,top,el("div","caption","Fecha de descarga: "+scanTime(a.quote_retrieved_at)+" · hora real del precio desconocida"));
  root.appendChild(price);
  const rec=researchRec(a);
  const recommendation=section(root,"Qué hacer con esta especie");
  const recHeader=el("div","rec-head");
  recHeader.append(recPill(a),el("span","rec-small","Evaluación automática · investigación, NO orden real"));
  recommendation.append(recHeader);
  (rec.reasons||[]).forEach(reason=>note(recommendation,reason,rec.category==="riesgo_datos"));
  infoRow(recommendation,"Próximo paso",rec.next_step||"Esperar actualización con fuentes verificadas.");
  const qualityText=rec.price_quality==="SEGUNDA_FUENTE_COINCIDE"?
    "Cierre cotejado con segundo proveedor (no es precio ejecutable)":
    rec.price_quality==="SEGUNDA_FUENTE_DISCREPA"?"Discrepancia entre proveedores":
    "Sin contraste independiente de cierre disponible para esta fecha";
  infoRow(recommendation,"Verificación de precio",qualityText);
  infoRow(recommendation,"Fecha del histórico",rec.close_date||"No verificada");
  note(recommendation,"La estrategia RSI35 no tiene rentabilidad validada. Sin puntas actuales ni composición de tu cartera, ninguna etiqueta justifica una compra o venta real.",true);
  const tech=section(root,"Análisis técnico");const grid=el("div","detail-grid");
  append(grid,dataTile("RSI 14",num(a.rsi14)),dataTile("Volumen relativo",a.rvol===null?"—":num(a.rvol)+"x"),
    dataTile("Calidad técnica",a.technical_score===null?"Sin serie":num(a.technical_score)+"/100"),
    dataTile("Última rueda analizada",a.daily_bar_date||"No validada"));
  tech.appendChild(grid);
  if(a.status==="CAIDA_CON_NOVEDAD_INVESTIGAR")note(tech,"Caída de panel y noticia asociada: no está demostrado que esa publicación causara la caída ni que vaya a producirse un rebote.",true);
  const setup=section(root,"Entrada y salida para simulación");
  if(a.entry_ref!==null&&a.stop_ref!==null&&a.target_ref!==null){
    const setupGrid=el("div","detail-grid");
    append(setupGrid,dataTile("Entrada teórica / cierre",money(a.entry_ref)),
       dataTile("Stop hipotético",money(a.stop_ref),"red"),
       dataTile("Objetivo hipotético",money(a.target_ref),"green"),
       dataTile("R:R neta estimada",a.rr_net_est===null?"—":num(a.rr_net_est)+":1"));
    setup.appendChild(setupGrid);
    infoRow(setup,"Unidades estimadas · $50.000",a.example_qty_50k===null?"—":num(a.example_qty_50k));
    infoRow(setup,"Unidades estimadas · $100.000",a.example_qty_100k===null?"—":num(a.example_qty_100k));
    note(setup,"Niveles calculados desde el CIERRE de la última rueda validada, no desde el precio actual. Entrada a confirmar en próxima apertura, con riesgo máximo ilustrativo 0,5% y exposición 20%. Solo papel.",true);
  }else note(setup,"Sin señal técnica con entrada, stop y objetivo validados. No hay precio operativo calculado para esta especie. Podés realizar una simulación manual si definís vos los tres niveles.",true);
  window.PULSOPositions?.renderAsset(a,root);
  const fundamental=section(root,"Fundamentos");
  if(a.fundamental){
    infoRow(fundamental,"Ejercicio fiscal",a.fundamental.fy||"—");
    infoRow(fundamental,"Variación nominal ventas",signed(a.fundamental.sales_yoy_pct));
    infoRow(fundamental,"Margen neto",signed(a.fundamental.net_margin_pct));
    const link=el("a","","Ver tabla de origen ↗");
    if(a.fundamental.url&&/^https:\/\//.test(a.fundamental.url)){link.href=a.fundamental.url;link.rel="noopener noreferrer";link.target="_blank";fundamental.appendChild(link);}
    note(fundamental,"Fuente secundaria de cifras anuales; no se confirmó la fecha de presentación y no sirven para demostrar una ventaja histórica.");
  }else note(fundamental,"No hay balance numérico comparable validado para este símbolo. Los datos faltantes no se interpretan como pérdidas ni ganancias.");
  const news=section(root,"Novedades relacionadas");
  if(a.events&&a.events.length){
    a.events.forEach(ev=>{
      const line=el("div","news-item");let link=el("a","",ev.title||"Ver documento");
      if(ev.url&&/^https:\/\//.test(ev.url)){link.href=ev.url;link.rel="noopener noreferrer";link.target="_blank";}else{link=el("span","",ev.title||"Documento");}
      append(line,link,el("div","news-meta",(ev.source==="CNV_OFICIAL"?"CNV oficial":"Noticia de tercero")+" · "+scanTime(ev.published)));
      news.appendChild(line);
    });
  }else note(news,"Sin publicaciones asociadas y verificables dentro de la ventana de observación actual.");
  if(a.warnings&&a.warnings.length){
    const flags=section(root,"Lo que falta verificar");a.warnings.forEach(v=>note(flags,v,true));
  }
  const sim=el("button","detail-btn","＋ Registrar posición ficticia manual");
  sim.addEventListener("click",()=>openPaper(a));root.appendChild(sim);
  root.appendChild(el("div","footnote","* Los importes del panel no sustituyen la caja de puntas del broker. No se ejecutan operaciones reales."));
}
function onFilterChanged(){
  s.query=$("search").value;s.assetType=$("assetType").value;s.filter=$("statusFilter").value;
  s.show=55;renderRows();
}
function paperValid(){
  const api=window.PULSOPaperJournal;
  const today=new Date().toLocaleDateString("sv-SE",{timeZone:TZ});
  const values={
    symbol:$("paperSymbolInput").value,kind:$("paperKind").value,
    capital:Number($("capital").value),entry:Number($("paperEntry").value),
    stop:Number($("paperStop").value),target:Number($("paperTarget").value),
    qty:Number($("paperQty").value),date:$("paperDate").value,
    source:$("paperSource").value,quoteAt:$("paperQuoteAt").value,
    confirm:$("paperConfirm").checked
  };
  const result=api?.validate(values,today)||{valid:false,reason:"Cálculo de riesgos no disponible."};
  const riskText=Number.isFinite(result.loss)?
    " · Pérdida estimada "+money(result.loss)+" ("+num(100*result.loss/values.capital)+"% de cartera)"+
    " · Beneficio al objetivo "+money(result.gain)+" · R:R neta "+num(result.rr)+":1":"";
  $("paperCalc").textContent=result.valid?
    "SOLO PAPEL · "+result.qty+" unidades · Desembolso con costos "+money(result.spend)+riskText+
    ". Cumple riesgo ≤0,5%, exposición ≤20% y R:R neta ≥2:1. NO es una orden ni cotización ejecutable.":
    (result.reason||"Datos insuficientes.")+riskText+
    " Sin cumplir estas condiciones no se registra una posición ficticia.";
  return result;
}
function openPaper(item=null){
  $("dialogTitle").textContent=item?.symbol?
    "Registro manual ficticio · "+item.symbol:"Nueva posición ficticia manual";
  $("paperSymbolInput").value=item?.symbol||"";
  $("paperKind").value=["accion","cedear"].includes(item?.kind)?item.kind:"accion";
  // Never populate a supposedly executed entry from a stale provider price.
  $("paperEntry").value="";
  $("paperStop").value="";
  $("paperTarget").value="";
  $("paperQty").value="1";
  $("paperDate").value=new Date().toLocaleDateString("sv-SE",{timeZone:TZ});
  $("paperSource").value="SIMULACION_MANUAL";
  $("paperQuoteAt").value="";
  $("paperConfirm").checked=false;
  updatePaperCalc();
  $("paperDialog").showModal();
  $("paperSymbolInput").focus();
}
function updatePaperCalc(){$("submitPaper").disabled=!paperValid().valid;}
function renderPaper(){
  const body=$("paperBody");body.replaceChildren();
  if(!s.paper.length){const tr=el("tr");const td=el("td","empty","Todavía no registraste operaciones ficticias.");td.colSpan=7;tr.appendChild(td);body.appendChild(tr);return;}
  s.paper.slice().reverse().forEach(p=>{
    const tr=el("tr");const cells=[
      p.date,p.ticker,String(p.qty),money(p.entry),
      money(p.stop)+" / "+money(p.target),p.manual?"Manual · sin ejecución real":"Registro ficticio anterior"
    ];
    cells.forEach(v=>tr.appendChild(el("td","",v)));
    const td=el("td");const remove=el("button","ghost","✕");remove.title="Eliminar registro";remove.addEventListener("click",()=>{
      if(!confirm("¿Eliminar esta operación ficticia del navegador?"))return;
      s.paper=s.paper.filter(z=>z.id!==p.id);persist("byma-paper-v1",s.paper);renderPaper();document.dispatchEvent(new CustomEvent("byma:paper"));
    });
    const chart=el("button","ghost","Ver gráfico");
    chart.title="Ver los niveles de esta operación ficticia sobre las velas";
    chart.type="button";
    chart.addEventListener("click",()=>{
      const selector=$("chartPositionMode");
      if(selector){selector.value="paper";selector.dispatchEvent(new Event("change",{bubbles:true}));}
      document.dispatchEvent(new CustomEvent("byma:selection",{detail:{symbol:p.ticker}}));
      $("workstation")?.scrollIntoView({behavior:"smooth",block:"start"});
    });
    td.append(chart,remove);tr.appendChild(td);body.appendChild(tr);
  });
}
function exportCsv(){
  if(!s.paper.length){alert("Todavía no hay operaciones ficticias registradas.");return;}
  const cols=["date","ticker","kind","qty","entry","stop","target","capital","risk","spend","profit","rr","source","quoteAt","status","manual","createdAt"];
  const esc=(x)=>'"'+String(x===null||x===undefined?"":x).replace(/"/g,'""')+'"';
  const csv="\ufeff"+cols.join(";")+"\r\n"+s.paper.map(p=>cols.map(k=>esc(p[k])).join(";")).join("\r\n");
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download="simulaciones_byma.csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function loadMarket(){
  $("refreshBtn").disabled=true;
  try{
    const resp=await fetch("./data/market.json?fresh="+Date.now(),{cache:"no-store"});
    if(!resp.ok)throw new Error("HTTP "+resp.status+" (aún no se publicaron datos)");
    const d=await resp.json();
    if(!d.meta||!Array.isArray(d.assets)||!d.summary)throw new Error("Formato de datos incorrecto");
    s.items=d.assets;s.meta=d.meta;s.summary=d.summary;s.latestFetch=Date.now();
    setStats();renderRows();renderDetail();
    document.dispatchEvent(new CustomEvent("byma:data"));renderAlerts();
  }catch(e){
    $("connection").textContent="Sin datos disponibles";
    $("connection").parentElement.classList.add("is-error");
    $("freshness").textContent=e.message||"No se pudo cargar";
    if(!s.items.length)$("assetsBody").replaceChildren(append(el("tr"),Object.assign(el("td","empty","Todavía no se publicó el archivo de mercado. Probá “Actualizar” cuando termine la tarea de GitHub."),{colSpan:7})));
  }finally{$("refreshBtn").disabled=false;}
}
$("search").addEventListener("input",onFilterChanged);
$("assetType").addEventListener("change",onFilterChanged);
$("statusFilter").addEventListener("change",onFilterChanged);
$("refreshBtn").addEventListener("click",loadMarket);
$("enableNotifications").addEventListener("click",requestAlerts);
$("loadMore").addEventListener("click",()=>{s.show+=55;renderRows();});
$("closeDialog").addEventListener("click",()=>$("paperDialog").close());
$("cancelDialog").addEventListener("click",()=>$("paperDialog").close());
["paperSymbolInput","paperKind","capital","paperEntry","paperStop","paperTarget","paperQty","paperDate","paperSource","paperQuoteAt","paperConfirm"].forEach(id=>$(id).addEventListener("input",updatePaperCalc));
$("paperForm").addEventListener("submit",(event)=>{
  event.preventDefault();const val=paperValid();if(!val.valid)return;
  const id=String(Date.now())+"_"+Math.random().toString(36).slice(2,7);
  const entry={...val,id,ticker:val.symbol,risk:val.loss,profit:val.gain,createdAt:new Date().toISOString()};
  delete entry.valid;s.paper.push(entry);persist("byma-paper-v1",s.paper);renderPaper();document.dispatchEvent(new CustomEvent("byma:paper"));$("paperDialog").close();
  document.getElementById("paper").scrollIntoView({behavior:"smooth",block:"start"});
});
$("chartShowDetails")?.addEventListener("click",()=>{
  const symbol=$("chartSymbol")?.textContent||"";
  if(!s.items.some(x=>x.symbol===symbol))return;
  s.selected=symbol;s.assetType="todos";s.filter="todos";s.query=symbol;
  $("assetType").value="todos";$("statusFilter").value="todos";$("search").value=symbol;
  renderRows();renderDetail();
  $("detailPanel").scrollIntoView({behavior:"smooth",block:"start"});
});
$("newPaper").addEventListener("click",()=>openPaper());
$("exportCsv").addEventListener("click",exportCsv);
$("clearPaper").addEventListener("click",()=>{
  if(!s.paper.length)return;
  if(confirm("¿Borrar TODAS las operaciones ficticias guardadas en este navegador?")){
    s.paper=[];persist("byma-paper-v1",s.paper);renderPaper();
  }
});
renderPaper();
updateNotificationButton();
refreshClock();
loadMarket();
setInterval(refreshClock,10000);
setInterval(loadMarket,60000);
