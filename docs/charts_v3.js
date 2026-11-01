"use strict";
/* PULSO BYMA v3 chart: standalone SVG OHLCV. Only published real historical candles.
   Never substitute price data or invent levels. Public feed = DELAYED, not tradable. */
(()=>{
const $=id=>document.getElementById(id);
const NS="http://www.w3.org/2000/svg";
const F=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const state={symbols:{},selected:null,requested:null,range:84,ready:false,error:null};
const isNum=x=>typeof x==="number"&&Number.isFinite(x);
const fmt=x=>isNum(x)?F.format(x):"—";
function el(tag,attrs={},txt){
 const n=document.createElementNS(NS,tag);
 for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));
 if(txt!=null)n.textContent=String(txt);
 return n;
}
function validBars(bars){
 if(!Array.isArray(bars)||bars.length<2)return false;
 let last="";
 return bars.every(a=>{
  if(!Array.isArray(a)||a.length!==6||typeof a[0]!=="string"||a[0]<=last)return false;
  last=a[0];
  const [_,o,h,l,c,v]=a;
  return [o,h,l,c,v].every(isNum)&&o>0&&l>0&&h>=Math.max(o,l,c)&&l<=Math.min(o,h,c)&&v>=0;
 });
}
function assetFor(sym){return typeof s!=="undefined"&&Array.isArray(s.items)?s.items.find(a=>a.symbol===sym):null;}
function note(msg){const box=$("chartEmpty");if(!box)return;box.textContent=msg;box.hidden=!msg;}
function updateInfo(){
 const sym=state.selected,rec=state.symbols[sym],a=assetFor(sym);
 $("chartSymbol").textContent=sym||"Sin datos";
 $("chartInfo").textContent=rec?("Velas 1D publicadas · "+rec.bars.length+" ruedas · última "+rec.last_candle+" · "+(rec.source||"IOL") +
   (rec.omitted_inconsistent_sessions?" · "+rec.omitted_inconsistent_sessions+" ruedas anómalas omitidas":"") ):
 "No hay histórico verificable";
 const ok=a?.status==="ENTRADA_TEORICA_PAPEL"&&[a.entry_ref,a.stop_ref,a.target_ref].every(isNum);
 $("chartTradeStatus").textContent=ok?"◉ Niveles teóricos de papel":"◌ Sin entrada confirmada";
 $("chartTradeStatus").className="chart-signal-label "+(ok?"signal-ok":"signal-off");
 const risk=$("chartRiskDetails");risk.replaceChildren();
 if(ok){
  for(const [label,value] of [["Entrada de papel",a.entry_ref],["Stop de papel",a.stop_ref],["Objetivo de papel",a.target_ref]]){
   const div=document.createElement("div");div.className="chart-trade-stat";
   const span=document.createElement("span");span.textContent=label;
   const strong=document.createElement("strong");strong.textContent="$ "+fmt(value);
   div.append(span,strong);risk.append(div);
  }
 }else{const d=document.createElement("div");d.className="chart-trade-none";
  d.textContent="Sin entrada validada. No hay niveles operativos; esto es seguimiento con información demorada.";risk.append(d);}
}
function redraw(){
 const root=$("chartFrame");if(!root)return;
 const current=$("chartDrawing");
 if(current)current.remove();
 updateInfo();
 const rec=state.symbols[state.selected];
 if(!rec){note(state.error||"No hay series históricas verificadas. Revisá el estado de datos.");return;}
 const bars=rec.bars.slice(-state.range);
 if(bars.length<2){note("La serie histórica es demasiado corta para graficarse.");return;}
 const W=1100,H=410, L=19,R=95,T=23,B=38,volumeH=85,gap=14;
 const OHLC_BOT=H-B-volumeH-gap,VTOP=OHLC_BOT+gap,VBOT=H-B;
 const asset=assetFor(state.selected);
 const levels=asset?.status==="ENTRADA_TEORICA_PAPEL"&&
  [asset.entry_ref,asset.stop_ref,asset.target_ref].every(isNum)?[
   {name:"ENTRADA",value:asset.entry_ref,color:"#a6c9ff"},
   {name:"STOP",value:asset.stop_ref,color:"#f58196"},
   {name:"OBJETIVO",value:asset.target_ref,color:"#50e4ad"}
  ]:[];
 const prices=bars.flatMap(b=>[b[2],b[3],...levels.map(l=>l.value)]);
 let low=Math.min(...prices),high=Math.max(...prices);
 const pad=Math.max((high-low)*.10,high*.002,1e-5);low-=pad;high+=pad;
 const valueY=v=>T+(high-v)/(high-low)*(OHLC_BOT-T);
 const cw=W-L-R;
 const valueX=i=>L+(i+.5)*cw/bars.length;
 const width=Math.max(1.2,Math.min(13,cw/bars.length*.57));
 const svg=el("svg",{id:"chartDrawing",viewBox:`0 0 ${W} ${H}`,role:"img",
  "aria-label":`Gráfico de velas diarias históricas de ${state.selected}, ${bars.length} sesiones; precios públicos demorados`,
  preserveAspectRatio:"none",style:"display:block;width:100%;height:100%;background:#0c1522"});
 const grid=el("g"),maGroup=el("g"),vGroup=el("g"),cGroup=el("g"),labels=el("g");
 for(let i=0;i<=5;i++){
  const y=T+(OHLC_BOT-T)*i/5,price=high-(high-low)*i/5;
  grid.append(el("line",{x1:L,x2:W-R+5,y1:y,y2:y,stroke:"#344357","stroke-width":"1","stroke-dasharray":"3 5"}));
  labels.append(el("text",{x:W-R+12,y:y+4,fill:"#a7b8ca","font-size":"12"},fmt(price)));
 }
 const maxVol=Math.max(1,...bars.map(b=>b[5]));
 bars.forEach((b,i)=>{
  const x=valueX(i),up=b[4]>=b[1],color=up?"#39d2a2":"#f07c90";
  const top=valueY(Math.max(b[1],b[4])),bottom=valueY(Math.min(b[1],b[4]));
  cGroup.append(el("line",{x1:x,y1:valueY(b[2]),x2:x,y2:valueY(b[3]),stroke:color,"stroke-width":"1.5"}));
  cGroup.append(el("rect",{x:x-width/2,y:top,width:width,height:Math.max(1.2,bottom-top),fill:color}));
  const vh=(VBOT-VTOP)*b[5]/maxVol;
  vGroup.append(el("rect",{x:x-width/2,y:VBOT-vh,width:width,height:vh,fill:color,opacity:".46"}));
  const hit=el("rect",{x:x-cw/bars.length/2,y:T,width:cw/bars.length,height:VBOT-T,fill:"transparent"});
  hit.addEventListener("pointerenter",()=>showQuote(b));
  hit.addEventListener("pointermove",()=>showQuote(b));
  hit.addEventListener("focus",()=>showQuote(b));
  cGroup.append(hit);
 });
 const period=bars.length>120?7:bars.length>25?6:Math.max(2,bars.length-1);
 for(let i=0;i<=period;i++){
  const k=Math.min(bars.length-1,Math.round(i*(bars.length-1)/period));
  labels.append(el("text",{x:valueX(k)-16,y:H-13,fill:"#93adbf","font-size":"12"},bars[k][0].slice(5).replace("-","/")));
 }
 function ma(period,color){
  const all=rec.bars;
  const points=[];
  for(let ix=Math.max(0,all.length-state.range);ix<all.length;ix++){
   if(ix<period-1)continue;
   let sum=0;
   for(let j=ix-period+1;j<=ix;j++)sum+=all[j][4];
   const v=sum/period;
   points.push(`${valueX(ix-(all.length-bars.length)).toFixed(2)},${valueY(v).toFixed(2)}`);
  }
  if(points.length>1)maGroup.append(el("polyline",{points:points.join(" "),fill:"none",stroke:color,
   "stroke-width":"1.8","stroke-linecap":"round","stroke-linejoin":"round"}));
 }
 ma(50,"#b4a0f8");ma(20,"#f2c16c");
 for(const l of levels){
  const yy=valueY(l.value);
  labels.append(el("line",{x1:L,y1:yy,x2:W-R,y2:yy,stroke:l.color,"stroke-width":"1.5","stroke-dasharray":"7 5"}));
  labels.append(el("text",{x:L+8,y:yy-5,fill:l.color,"font-size":"12","font-weight":"bold"},l.name));
  labels.append(el("text",{x:W-R+7,y:yy+4,fill:l.color,"font-size":"12"},fmt(l.value)));
 }
 labels.append(el("text",{x:L+5,y:VTOP+14,fill:"#829eb3","font-size":"11"},"VOLUMEN"));
 svg.append(grid,maGroup,vGroup,cGroup,labels);
 // Keep SVG independent from browser canvas context, DPR or external CDN.
 root.append(svg);
 if(state.requested&&!state.symbols[state.requested]){
  note(`El activo ${state.requested} no tiene velas publicadas. Se muestra ${state.selected} como referencia, NO como gráfico de ${state.requested}.`);
 }else note("");
 showQuote(bars.at(-1));
}
function showQuote(b){
 const q=$("chartHover");if(!q)return;
 q.hidden=false;
 q.textContent=b[0]+"  Apertura "+fmt(b[1])+"  Máximo "+fmt(b[2])+"  Mínimo "+fmt(b[3])+
  "  Cierre "+fmt(b[4])+"  Volumen "+fmt(b[5]);
}
function select(sym,request=true){
 if(request)state.requested=sym;
 if(state.symbols[sym])state.selected=sym;
 else if(!state.symbols[state.selected])state.selected=Object.keys(state.symbols)[0]||null;
 const picker=$("chartSymbolPicker");
 if(picker&&state.selected)picker.value=state.selected;
 redraw();
}
async function load(){
 try{
  const res=await fetch("./data/charts.json?v="+Date.now(),{cache:"no-store"});
  if(!res.ok)throw Error("HTTP "+res.status+" al descargar históricos");
  const json=await res.json();
  if(json.chart_data!=="DAILY_HISTORICAL_ONLY_NOT_LIVE")throw Error("Formato de datos no compatible");
  const approved=Object.entries(json.symbols||{}).filter(([_,v])=>validBars(v.bars));
  if(!approved.length)throw Error("No se encontraron series OHLCV válidas");
  state.symbols=Object.fromEntries(approved);state.ready=true;state.error=null;
  const picker=$("chartSymbolPicker");picker.replaceChildren();
  for(const name of Object.keys(state.symbols).sort()){
   const opt=document.createElement("option");opt.value=name;opt.textContent=name;picker.append(opt);
  }
  const count=$("chartDatasetCount");
  if(count)count.textContent=approved.length+" especies con velas 1D (no son datos en vivo)";
  select(state.requested||state.selected|| (state.symbols.CEPU?"CEPU":approved[0][0]),false);
 }catch(err){
  state.error="No se pudieron cargar las velas: "+(err?.message||String(err));
  state.ready=false;redraw();
  console.warn("PULSO chart feed:",err);
 }
}
for(const b of document.querySelectorAll("[data-chart-range]")){
 b.addEventListener("click",()=>{
  state.range=Number(b.dataset.chartRange);
  for(const x of document.querySelectorAll("[data-chart-range]"))
   x.classList.toggle("active",x===b);
  redraw();
 });
}
$("chartSymbolPicker")?.addEventListener("change",e=>{
 select(e.target.value);document.dispatchEvent(new CustomEvent("byma:chart-selected",{detail:{symbol:e.target.value}}));
});
document.addEventListener("byma:selection",e=>{if(e.detail?.symbol)select(e.detail.symbol);});
document.addEventListener("byma:data",()=>redraw());
window.addEventListener("resize",()=>{if(state.ready)redraw();});
load();
setInterval(load,300000);
})();
