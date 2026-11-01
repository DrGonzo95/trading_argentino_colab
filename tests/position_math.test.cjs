"use strict";
const assert=require("node:assert/strict");
const {assess,amount,atr14,barsValid,FEE,SLIP}=require("../docs/position_math.js");
const now=new Date("2026-11-01T14:00:00.000Z");
const base=new Date("2026-09-01T12:00:00Z");
const bars=Array.from({length:60},(_,i)=>{
 const day=new Date(base.getTime()+i*86400000).toISOString().slice(0,10);
 const open=99+i*.5, close=open+1, high=close+1.5,low=open-1.2;
 return [day,open,high,low,close,200000+i*100];
});
const date=bars.at(-1)[0],last=bars.at(-1)[4];
const chart={bars,last_candle:date};
const a={
 symbol:"TEST",kind:"accion",status:"SOLO_SEGUIMIENTO",daily_bar_date:date,
 recommendation:{code:"OBSERVAR",real_trade_allowed:false,price_quality:"SEGUNDA_FUENTE_COINCIDE",
   technical_date:date}
};
assert(barsValid(bars));
assert(atr14(bars)>0);
const no=assess(a,chart,100000,now);
assert.equal(no.mode,"ESTUDIO_SIN_SENAL");
assert.equal(no.openUnits,0,"No RSI35 signal => zero suggested positions");
assert(no.scenario.units>0,"Should compute scenario independent from a valid signal");
assert(no.scenario.cost<=20000+.0001);
assert(no.scenario.loss<=500+.0001);
assert(no.scenario.gain>0);
const paper={
 ...a,status:"ENTRADA_TEORICA_PAPEL",entry_ref:last,
 stop_ref:last-10,target_ref:last+40,rr_net_est:3,
 recommendation:{...a.recommendation,code:"SIMULAR_ENTRADA"}
};
const eligible=assess(paper,chart,100000,now);
assert.equal(eligible.mode,"ENTRADA_SOLO_PAPEL");
assert(eligible.openUnits>0);
assert.equal(eligible.openUnits,eligible.plan.units);
assert(eligible.plan.rr>=2);
assert(eligible.plan.cost<=20000+.0001);
assert(eligible.plan.loss<=500+.0001);
assert.equal(eligible.plan.unitCost,last*(1+SLIP)*(1+FEE));
assert(eligible.plan.gain>0);
const more=assess(paper,chart,250000,now);
assert(more.openUnits>eligible.openUnits,"Capital should scale units within risk limits");
const mismatch=assess({...paper,recommendation:{...paper.recommendation,price_quality:"SEGUNDA_FUENTE_DISCREPA"}},chart,100000,now);
assert.equal(mismatch.openUnits,0);
assert.equal(mismatch.scenario,null,"Source discrepancy also suppresses hypothetical pricing");
const invalid=assess({...paper,daily_bar_date:"2026-10-29"},chart,100000,now);
assert.equal(invalid.openUnits,0,"Candle from wrong day must not turn into signal");
const bond=assess({...paper,kind:"bono"},chart,100000,now);
assert.equal(bond.openUnits,0);assert.equal(bond.scenario,null);
const stale=assess(a,{bars:bars.map(row=>["2020-"+row[0].slice(5),...row.slice(1)])},100000,now);
assert.equal(stale.openUnits,0);
const tooSmall=assess(paper,chart,1000,now);
assert.equal(tooSmall.openUnits,0);
assert(tooSmall.plan===undefined||tooSmall.plan.units===0);
assert.equal(amount(100000,100,110,150),null);
console.log("PASS position_math: 10 checks incl no-signal zero, fees, stop risk, exposure, stale, mismatch, capital scaling");
