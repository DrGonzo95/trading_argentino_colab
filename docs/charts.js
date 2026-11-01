"use strict";
/* PULSO/BYMA 1D professional canvas chart (no generated/fictitious candles).
   Observed OHLCV only. No external chart library or broker API. */
(()=>{
const $=id=>document.getElementById(id);
const state={data:null,selected:null,candles:[],asset:null,range:84,hover:-1,ready:false,ema20:[],ema50:[],ohlcSource:null};
const fmt=new Intl.NumberFormat("es-AR",{maximumFractionDigits:2});
const integer=new Intl.NumberFormat("es-AR",{maximumFractionDigits:0});
const num=n=>n===null||n===undefined||!Number.isFinite(+n)?"—":fmt.format(+n);
const money=n=>n===null||n===undefined||!Number.isFinite(+n)?"—":"$"+fmt.format(+n);
const readableDate=d=>{
  if(!d)return "—";
  const [y,m,day]=d.split("-");return day+"/"+m+"/"+y;
};
let lastGeometry=null;
function movingAverage(data,period){
  const result=[];let sum=0;
  for(let i=0;i<data.length;i++){
    sum+=data[i][4];if(i>=period)sum-=data[i-period][4];
    result.push(i>=period-1?sum/period:null);
  }
  return result;
}
function numberColor(value){
  return value>=0?"#3bd3a4":"#f07e8d";
}
function updateTop(){
  const a=state.asset;
  const first=$("chartSymbol"),sub=$("chartInfo"),status=$("chartTradeStatus");
  if(!first||!sub||!status)return;
  first.textContent=a?.symbol||state.selected||"—";
  const hist=state.data?.symbols?.[state.selected||""]||null;
  sub.textContent=hist?("Velas 1D · "+state.candles.length+" ruedas cargadas · último cierre "+readableDate(hist.last_candle)):
    "Sin histórico diario verificable para esta especie";
  if(a?.status==="ENTRADA_TEORICA_PAPEL" && a.entry_ref!==null && a.stop_ref!==null && a.target_ref!==null){
    status.className="chart-signal-label signal-ok";
    status.textContent="◉ Entrada teórica en papel";
  }else{
    status.className="chart-signal-label signal-off";
    status.textContent="◌ Sin entrada confirmada";
  }
  const risk=$("chartRiskDetails");
  if(risk){
    risk.replaceChildren();
    if(a?.status==="ENTRADA_TEORICA_PAPEL" && a.entry_ref!==null && a.stop_ref!==null && a.target_ref!==null){
      [["ENTRADA SIMULADA",money(a.entry_ref),"#d3e5f1"],["STOP TEÓRICO",money(a.stop_ref),"#f07e8d"],
       ["OBJETIVO",money(a.target_ref),"#3bd3a4"],["R:R NETA EST.",num(a.rr_net_est)+":1","#b7dfff"]].forEach(row=>{
         const div=document.createElement("div");div.className="chart-trade-stat";
         const label=document.createElement("span");label.textContent=row[0];
         const val=document.createElement("strong");val.textContent=row[1];val.style.color=row[2];
         div.append(label,val);risk.appendChild(div);
       });
    }else{
      const div=document.createElement("div");div.className="chart-trade-none";
      div.textContent="Sin señal de entrada validada. Seleccioná otra especie o revisá las oportunidades en observación. Nunca se inventan niveles de compra.";
      risk.appendChild(div);
    }
  }
}
function showUnavailable(message){
  const canvas=$("candleCanvas"),overlay=$("chartEmpty");
  if(canvas)canvas.style.opacity=".16";
  if(overlay){overlay.hidden=false;overlay.textContent=message;}
  $("chartHover").hidden=true;
  updateTop();
}
function setSelected(symbol){
  state.selected=symbol||null;
  state.hover=-1;
  if(typeof s!=="undefined"&&Array.isArray(s.items)){
    state.asset=s.items.find(a=>a.symbol===symbol)||null;
  }else state.asset=null;
  const history=state.data?.symbols?.[symbol||""]||null;
  state.candles=history&&Array.isArray(history.bars)?history.bars:[];
  state.ema20=movingAverage(state.candles,20);
  state.ema50=movingAverage(state.candles,50);
  updateTop();
  render();
}
function fitData(){
  if(!state.ready || !state.data)return;
  if(!state.selected){
    let choice=null;
    if(typeof s!=="undefined"&&Array.isArray(s.items)){
      choice=s.items.find(a=>a.status==="ENTRADA_TEORICA_PAPEL" && state.data.symbols[a.symbol]) ||
        s.items.find(a=>a.status==="CAIDA_CON_NOVEDAD_INVESTIGAR" && state.data.symbols[a.symbol]) ||
        s.items.find(a=>a.technical_score!==null && state.data.symbols[a.symbol]);
    }
    const symbol=choice?.symbol||Object.keys(state.data.symbols)[0]||null;
    setSelected(symbol);
  }else{
    setSelected(state.selected);
  }
}
function initCanvas(){
  const c=$("candleCanvas");
  if(!c)return null;
  const rect=c.getBoundingClientRect();
  if(rect.width<=0||rect.height<=0)return null;
  const ratio=Math.min(2.5,window.devicePixelRatio||1);
  c.width=Math.floor(rect.width*ratio);
  c.height=Math.floor(rect.height*ratio);
  const context=c.getContext("2d");
  context.setTransform(ratio,0,0,ratio,0,0);
  const W=rect.width,H=rect.height;
  context.clearRect(0,0,W,H);
  context.fillStyle="#0c1522";context.fillRect(0,0,W,H);
  const left=12,right=84,top=19,volumeH=76,bottom=28,gap=18;
  const candleBottom=H-bottom-volumeH-gap;
  return {c,ctx:context,W,H,left,right,top,volumeH,bottom,gap,candleBottom,
      chartW:W-left-right,chartH:candleBottom-top};
}
function drawLabel(ctx,text,x,y,color,bg){
  ctx.font="11px system-ui, sans-serif";
  ctx.textBaseline="middle";
  const width=ctx.measureText(text).width+12;
  ctx.fillStyle=bg||"#1e2b3c";ctx.fillRect(x,y-10,width,20);
  ctx.fillStyle=color||"#d6e5f2";ctx.fillText(text,x+6,y);
}
function render(){
  const canvasCtx=initCanvas();if(!canvasCtx)return;
  const {ctx,W,H,left,right,top,volumeH,candleBottom,chartW,chartH}=canvasCtx;
  if(!state.candles.length){
    showUnavailable(state.ready?"Sin velas diarias publicadas para este símbolo. No se grafican precios ficticios.":"Cargando velas…");
    lastGeometry=null;return;
  }
  $("candleCanvas").style.opacity="1";
  $("chartEmpty").hidden=true;
  const all=state.candles;
  const end=all.length,from=Math.max(0,end-state.range),bars=all.slice(from);
  const count=bars.length;
  if(count<2)return;
  const vals=bars.flatMap(r=>[r[2],r[3]]);
  const levels=[];
  const asset=state.asset;
  if(asset?.status==="ENTRADA_TEORICA_PAPEL" &&
      [asset.entry_ref,asset.stop_ref,asset.target_ref].every(x=>x!==null&&Number.isFinite(+x))){
    levels.push({label:"ENTRADA",value:+asset.entry_ref,color:"#9ec3f7"});
    levels.push({label:"STOP",value:+asset.stop_ref,color:"#f07e8d"});
    levels.push({label:"OBJETIVO",value:+asset.target_ref,color:"#3bd3a4"});
  }
  let ymin=Math.min(...vals,...levels.map(x=>x.value)), ymax=Math.max(...vals,...levels.map(x=>x.value));
  const span=Math.max(1e-8,ymax-ymin);const padding=span*.12;
  ymin-=padding;ymax+=padding;
  const y=val=>top+(ymax-val)/(ymax-ymin)*chartH;
  const x=i=>left+((i+.5)/count)*chartW;
  const barSpace=chartW/count;
  const candleW=Math.max(1,Math.min(11,barSpace*.59));
  const volTop=candleBottom+gap;
  const volBottom=H-bottom;
  const maxVolume=Math.max(...bars.map(d=>d[5]),1);
  ctx.strokeStyle="#29394b";ctx.lineWidth=.7;ctx.setLineDash([3,5]);
  ctx.textAlign="left";ctx.font="10px ui-monospace,monospace";
  for(let i=0;i<6;i++){
    const gy=top+chartH*i/5;const price=ymax-(ymax-ymin)*i/5;
    ctx.beginPath();ctx.moveTo(left,gy);ctx.lineTo(W-right+6,gy);ctx.stroke();
    ctx.fillStyle="#91a4ba";ctx.fillText(fmt.format(price),W-right+10,gy-3);
  }
  ctx.fillStyle="#8297a9";ctx.font="10px system-ui";
  const gridCount=Math.min(7,count);
  for(let i=0;i<=gridCount;i++){
    const index=Math.min(count-1,Math.round(i*(count-1)/gridCount));
    const label=readableDate(bars[index][0]).slice(0,5);
    ctx.fillText(label,Math.min(W-right-45,Math.max(left,x(index)-13)),H-9);
  }
  ctx.setLineDash([]);
  const e20=state.ema20.slice(from),e50=state.ema50.slice(from);
  function drawMA(arr,color){
    ctx.beginPath();ctx.lineWidth=1.6;ctx.strokeStyle=color;
    let first=true;
    arr.forEach((v,i)=>{if(v===null || v<ymin||v>ymax)return;
      if(first){ctx.moveTo(x(i),y(v));first=false;}else ctx.lineTo(x(i),y(v));});
    ctx.stroke();
  }
  // Draw MA behind candles.
  drawMA(e50,"#a597f4");drawMA(e20,"#f4c36e");
  for(let i=0;i<count;i++){
    const v=bars[i],up=v[4]>=v[1],color=numberColor(up?1:-1);
    ctx.strokeStyle=color;ctx.fillStyle=color;
    ctx.beginPath();ctx.moveTo(x(i),y(v[2]));ctx.lineTo(x(i),y(v[3]));ctx.lineWidth=1;ctx.stroke();
    const y1=y(Math.max(v[1],v[4])),y2=y(Math.min(v[1],v[4]));
    ctx.fillRect(x(i)-candleW/2,y1,candleW,Math.max(1.2,y2-y1));
    const volumeHeight=Math.max(0,(volBottom-volTop)*(v[5]/maxVolume));
    ctx.globalAlpha=.5;
    ctx.fillRect(x(i)-candleW/2,volBottom-volumeHeight,candleW,volumeHeight);
    ctx.globalAlpha=1;
  }
  ctx.beginPath();ctx.strokeStyle="#334457";ctx.moveTo(left,volTop-8);ctx.lineTo(W-right+6,volTop-8);ctx.stroke();
  ctx.font="10px system-ui";ctx.fillStyle="#89a0b1";ctx.fillText("VOLUMEN",left+4,volTop+10);
  if(levels.length){
    levels.forEach(l=>{
      const py=y(l.value);
      ctx.strokeStyle=l.color;ctx.lineWidth=1.4;ctx.setLineDash([6,4]);
      ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(W-right+5,py);ctx.stroke();ctx.setLineDash([]);
      const centerText=fmt.format(l.value);
      drawLabel(ctx,centerText,W-right+1,py,l.color,"#1f3142");
      ctx.font="bold 10px system-ui";ctx.fillStyle=l.color;
      ctx.fillText(l.label,left+7,Math.max(top+10,Math.min(candleBottom-6,py-10)));
    });
  }
  if(state.hover>=0 && state.hover<count){
    const selected=bars[state.hover];
    ctx.strokeStyle="#b8cadc";ctx.lineWidth=.8;ctx.setLineDash([4,4]);
    ctx.beginPath();ctx.moveTo(x(state.hover),top);ctx.lineTo(x(state.hover),volBottom);ctx.stroke();ctx.setLineDash([]);
    $("chartHover").hidden=false;
    $("chartHover").textContent=
      readableDate(selected[0])+"    O "+num(selected[1])+"    H "+num(selected[2])+"    L "+num(selected[3])+
      "    C "+num(selected[4])+"    VOL "+integer.format(selected[5]);
  }else{
    const last=bars[bars.length-1];
    $("chartHover").hidden=false;
    $("chartHover").textContent=readableDate(last[0])+"    O "+num(last[1])+"    H "+num(last[2])+"    L "+num(last[3])+
        "    C "+num(last[4])+"    VOL "+integer.format(last[5]);
  }
  lastGeometry={left,chartW,from,count,candleBottom,top};
}
function trackPointer(evt){
  if(!lastGeometry)return;
  const rect=$("candleCanvas").getBoundingClientRect();
  const pos=evt.clientX-rect.left;
  const {left,chartW,count}=lastGeometry;
  state.hover=pos>=left && pos<=left+chartW?
      Math.max(0,Math.min(count-1,Math.floor((pos-left)/chartW*count))):-1;
  render();
}
async function loadChartFeed(){
  try{
    const r=await fetch("./data/charts.json?v="+Date.now(),{cache:"no-store"});
    if(!r.ok)throw new Error("La exportación de velas todavía no está disponible.");
    const json=await r.json();
    if(json.chart_data!=="DAILY_HISTORICAL_ONLY_NOT_LIVE"||!json.symbols)throw new Error("Archivo de velas incorrecto");
    state.data=json;state.ready=true;
    fitData();
    const status=$("chartDatasetCount");
    if(status)status.textContent=Object.keys(json.symbols).length+" series diarias reales";
  }catch(e){
    state.ready=false;showUnavailable(e.message||"Históricos aún no disponibles.");
  }
}
$("candleCanvas")?.addEventListener("pointermove",trackPointer);
$("candleCanvas")?.addEventListener("pointerleave",()=>{state.hover=-1;render();});
$("candleCanvas")?.addEventListener("wheel",e=>{
  if(!state.candles.length)return;
  e.preventDefault();state.range=Math.max(25,Math.min(260,state.range+(e.deltaY>0?15:-15)));setRangeButtons();render();
},{passive:false});
function setRangeButtons(){
  document.querySelectorAll("[data-chart-range]").forEach(b=>{
    b.classList.toggle("active",Number(b.dataset.chartRange)===state.range);
  });
}
document.querySelectorAll("[data-chart-range]").forEach(b=>b.addEventListener("click",()=>{
  state.range=Number(b.dataset.chartRange);state.hover=-1;setRangeButtons();render();
}));
document.addEventListener("byma:selection",e=>setSelected(e.detail?.symbol));
document.addEventListener("byma:data",()=>{if(state.ready)fitData();});
if("ResizeObserver" in window){const ob=new ResizeObserver(()=>render());ob.observe($("chartFrame"));}
else window.addEventListener("resize",render);
setRangeButtons();loadChartFeed();
setInterval(loadChartFeed,300000);
})();
