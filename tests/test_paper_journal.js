"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const j=require("../docs/paper_journal_math.js");
const basic={symbol:"IRSA",kind:"accion",capital:100000,entry:2070,stop:1990,target:2500,qty:1,
  date:"2026-11-05",source:"SIMULACION_MANUAL",quoteAt:"",confirm:true};
const today="2026-11-05";
const ok=j.validate(basic,today);
assert.equal(ok.valid,true,JSON.stringify(ok));
assert.equal(ok.status,"ABIERTA_FICTICIA_MANUAL_NO_VERIFICADA");
assert.equal(ok.manual,true);
assert.ok(ok.rr>=2 && ok.loss<=500 && ok.spend<=20000);
assert.ok(ok.unitCost>basic.entry);
assert.ok(ok.gain>0 && ok.loss>0);
const fails=[
  [{...basic,confirm:false},"Confirmá"],
  [{...basic,kind:"bono"},"acciones"],
  [{...basic,symbol:"AAPL.US"},"símbolo"],
  [{...basic,stop:2080},"stop"],
  [{...basic,target:2110},"inferior"],
  [{...basic,qty:100},"Supera"],
  [{...basic,capital:50000,qty:50},"Supera"],
  [{...basic,date:"2026-12-01"},"futura"],
  [{...basic,source:"NO_EXISTE"},"Fuente"],
  [{...basic,qty:0},"Cantidad"],
];
for(const [input,reason] of fails){const r=j.validate(input,today);assert.equal(r.valid,false,JSON.stringify(r));assert.ok(r.reason.toLowerCase().includes(reason.toLowerCase()),r.reason);}
const missing=fs.readFileSync("docs/index.html","utf8");
const js=fs.readFileSync("docs/app.js","utf8");
for(const id of ["newPaper","paperSymbolInput","paperKind","paperSource","paperConfirm","paperQuoteAt"]){
  assert.ok(missing.includes('id="'+id+'"'),"Falta campo "+id);
  assert.ok(js.includes('"'+id+'"'),"Falta conexión "+id);
}
assert.ok(missing.indexOf("./paper_journal_math.js")<missing.indexOf("./app.js"),"Módulo de cálculos debe cargarse primero");
assert.ok(!js.includes('$("paperEntry").value=item.entry_ref??item.quote_price'),"Está reutilizando una cotización no validada como fill");
assert.ok(js.includes('openPaper(item=null)'),"Debe permitir simulación sin radar");
console.log("OK: 11 casos de validación, controles de UI, sin relleno de precios ni fills automáticos.");
