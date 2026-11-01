"use strict";
const assert=require("node:assert/strict");
const pos=require("../docs/position_math.js");
global.window={PULSOPositionMath:pos};
const e=require("../docs/research_engine.js");
const now=new Date("2026-11-01T12:00:00Z");
const end=new Date("2026-10-30T12:00:00Z");
function mkBars({slope=.45,period=260}={}){
 const bars=[];
 for(let i=0;i<period;i++){
  const d=new Date(end.getTime()-(period-i-1)*86400000).toISOString().slice(0,10);
  const c=100+i*slope+Math.sin(i/5)*2;
  bars.push([d,c-1,c+3,c-4,c,80000+i*100]);
 }
 return bars;
}
const bars=mkBars();
const asset={symbol:"TEST",kind:"accion",status:"SOLO_SEGUIMIENTO",recommendation:{code:"OBSERVAR",
 real_trade_allowed:false,price_quality:"SOLO_FUENTE_PRINCIPAL"},quote_price:bars.at(-1)[4],
 daily_bar_date:"2026-10-30",fundamental:null,events:[]};
const history={bars,last_candle:"2026-10-30",source:"test fixture – synthetic only in tests"};
let x=e.analyze(asset,history,{capital:100000,now});
assert.equal(x.date,"2026-10-30");
assert(x.metrics.rsi14>=0&&x.metrics.rsi14<=100);
assert(x.metrics.ema20>x.metrics.ema50&&x.metrics.ema50>x.metrics.ema200);
assert(x.metrics.atr14>0);
assert(x.metrics.support20<x.metrics.resistance20);
assert(x.potential.length>=1);
assert.equal(x.plan.unitsToOpen,0,"Without signal no units can be recommended to open");
assert.equal(x.plan.type,"ESTUDIO_SIN_SENAL");
assert(x.plan.stop<x.plan.entry&&x.plan.tp1>x.plan.entry);
assert(x.plan.tp2>x.plan.tp1);
assert(x.plan.cost<=20000.001&&x.plan.lossAtStop<=500.001);
assert(x.risks.some(a=>a.includes("Spread")||a.includes("spread")),"Must flag broker spread not observed");
const stable=JSON.stringify(x);
assert.equal(JSON.stringify(e.analyze(asset,history,{capital:100000,now})),stable,"Deterministic output");
const reference=pos.amount(100000,x.plan.entry,x.plan.stop,x.plan.tp1);
assert(Math.abs(reference.loss-x.plan.lossAtStop)<.01);
const missing=e.analyze(asset,null,{now});
assert.equal(missing.plan,null);
const short=e.analyze(asset,{bars:bars.slice(-50)},{now});
assert.equal(short.plan,null);
const bond=e.analyze({...asset,kind:"bono"},history,{now});
assert.equal(bond.plan,null);assert.equal(bond.state,"RENTA_FIJA_SIN_VALUACION");
assert(bond.next.includes("TIR"));
const on=e.analyze({...asset,kind:"on"},null,{now});
assert.equal(on.plan,null);
const stale=e.analyze(asset,history,{now:new Date("2026-12-12T12:00:00Z")});
assert.equal(stale.plan,null);
const discrep=e.analyze(asset,history,{now,cross:{prices:{TEST:{status:"DIVERGENCE",market_date:"2026-10-30"}}}});
assert.equal(discrep.plan,null);
const same=e.analyze({...asset,quote_retrieved_at:"2026-10-30T18:00:00-03:00",quote_price:asset.quote_price*1.1},history,{now});
assert.equal(same.plan,null);
const altered=structuredClone(history);altered.bars[150][2]=0;
assert.equal(e.analyze(asset,altered,{now}).plan,null,"Invalid OHLC should be rejected");
const actual={
 ...asset, status:"ENTRADA_TEORICA_PAPEL",entry_ref:bars.at(-1)[4],
 stop_ref:bars.at(-1)[4]-18,target_ref:bars.at(-1)[4]+65,rr_net_est:2.6,
 recommendation:{code:"SIMULAR_ENTRADA",technical_date:"2026-10-30",real_trade_allowed:false}
};
const good=e.analyze(actual,history,{capital:100000,now});
assert.equal(good.plan.type,"PAPEL_RSI35");
assert.equal(good.plan.tp2,null);
assert(good.plan.unitsToOpen>=0);
assert.equal(good.plan.unitsToOpen,good.plan.units);
console.log("PASS research_engine 18 checks: trends, RSI/ATR, potential reasons, conditional stops/TP, date/source validation, bonds no made-up yield, paper-only gating");
