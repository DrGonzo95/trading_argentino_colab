import { chromium } from "playwright";
import assert from "node:assert/strict";
import fs from "node:fs";
const URL="http://127.0.0.1:8765/";
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
let allOk=true;
for(const [name,viewport] of [["desktop",{width:1440,height:900}],["mobile",{width:390,height:844}]]){
 const page=await browser.newPage({viewport,deviceScaleFactor:1});
 const errors=[];
 page.on("pageerror",e=>errors.push(e.message));
 page.on("response",r=>{if(r.status()>=400&&/\/data\//.test(r.url()))errors.push("HTTP "+r.status()+" "+r.url());});
 try{
  await page.goto(URL,{waitUntil:"domcontentloaded",timeout:30000});
  await page.waitForSelector("#chartDrawing",{timeout:25000});
  await page.waitForFunction(()=>document.querySelector("#chartSymbolPicker")?.options.length>=4,{timeout:25000});
  await page.selectOption("#chartSymbolPicker","CEPU");
  await page.waitForFunction(()=>document.querySelector("#chartSymbol")?.textContent==="CEPU");
  const info=await page.evaluate(()=>{
   const svg=document.querySelector("#chartDrawing");
   const chart=document.querySelector("#chartFrame").getBoundingClientRect();
   return {
    symbols:document.querySelector("#chartSymbolPicker").options.length,
    candles:svg.querySelectorAll("g:nth-child(4) rect").length,
    rects:svg.querySelectorAll("rect").length,
    chartWidth:chart.width,chartHeight:chart.height,
    text:document.querySelector("#chartHover").textContent,
    visible:!!(svg.getBoundingClientRect().width&&svg.getBoundingClientRect().height),
    overlay:document.querySelector("#chartEmpty").hidden,
    banner:document.querySelector("#proTerminal")?.textContent.slice(0,80)
   };
  });
  assert(info.symbols>=4,"Symbol selector missing options");
  assert(info.rects>40,"Not enough rendered SVG candle/volume bars");
  assert(info.visible&&info.chartWidth>200&&info.chartHeight>280,"No visible chart viewport");
  assert(info.overlay,"Unexpected error overlay on CEPU");
  assert(/Cierre/.test(info.text),"OHLC hover/last close missing");
  // Every researched instrument must carry an explained no-real-order action.
  await page.selectOption("#assetType","todos");
  await page.selectOption("#statusFilter","todos");
  await page.fill("#search","CEPU");
  await page.waitForFunction(()=>document.querySelectorAll("#assetsBody .rec-pill").length>0);
  await page.locator("#assetsBody tr").first().click();
  const advice=await page.evaluate(()=>{
    const r=window.s?.items?.find?.(x=>x.symbol==="CEPU")||null;
    return {label:document.querySelector("#detailPanel .rec-pill")?.textContent||"",
      next:document.querySelector("#detailPanel")?.textContent||"",
      row:document.querySelector("#assetsBody .rec-pill")?.textContent||"",
      monitor:document.querySelector("#proSignal .pro-action-tag")?.textContent||"",
      market:document.querySelector("#statTotal")?.textContent||""};
  });
  assert(advice.label && advice.row,"Recommendations missing from table or instrument detail");
  assert(advice.next.includes("Próximo paso")&&advice.next.includes("Qué hacer con esta especie"),
    "Explanation and trigger absent from recommendation");
  assert(advice.monitor,"Professional monitor does not show researched action");
  // All instruments get an independent paper simulation outcome. A missing signal must show zero open units.
  await page.waitForFunction(()=>document.querySelector("#simCount")?.textContent.includes("especies"),{timeout:20000});
  await page.locator("#positionFilter").selectOption("chart");
  await page.locator("#positionSearch").fill("CEPU");
  await page.waitForFunction(()=>document.querySelectorAll("#simPositionsBody tr").length===1);
  const simulation=await page.evaluate(()=>{
    const row=document.querySelector("#simPositionsBody tr");
    return {text:row?.textContent||"",cells:row?.querySelectorAll("td").length||0,
      count:document.querySelector("#simCount")?.textContent||"",
      method:typeof window.PULSOPositionMath?.assess,
      capital:document.querySelector("#simCapitalLabel")?.textContent||""};
  });
  assert.equal(simulation.cells,12,"Simulation table must present all 12 columns");
  assert.equal(simulation.method,"function","Position math module is absent");
  assert(simulation.text.includes("NO ABRIR") || simulation.text.includes("PAPEL"),"No honest position state");
  await page.locator("#positionCapital").fill("250000");
  await page.waitForFunction(()=>document.querySelector("#simCapitalLabel")?.textContent.includes("250.000"));
  await page.locator("#simPositionsBody tr button").first().click();
  await page.waitForFunction(()=>document.querySelector("#detailPanel .sim-detail"));
  assert((await page.locator("#detailPanel .sim-detail").innerText()).includes("unidades"),"Position sizing absent from selected asset");

  // Confirm exact source-driven analysis for stock and safe refusal for bond.
  await page.waitForFunction(()=>document.querySelector("#detailPanel .research-panel"));
  const research=await page.evaluate(()=>{
    const p=document.querySelector("#detailPanel .research-panel");
    return {text:p?.textContent||"",metrics:p?.querySelectorAll(".research-metrics .sim-stat").length||0,
      plan:p?.querySelector(".research-levels")?.textContent||"",status:p?.querySelector(".research-status")?.textContent||""};
  });
  assert(research.metrics>=8,"EMA, RSI, ATR, volume, support/resistance not rendered");
  assert(/potencial/i.test(research.text),"Missing evidence-based potential rationale");
  assert(/Stop condicional/.test(research.plan)&&/Take profit 1/.test(research.plan)&&/Take profit 2/.test(research.plan),
    "Conditional stop/TP1/TP2 levels not shown");
  assert(/Unidades para abrir por señal/.test(research.plan),
    "No-signal simulated entry status should be explicit");
  console.log("RESEARCH_ANALYSIS",name,JSON.stringify({metrics:research.metrics,status:research.status,plan:research.plan.slice(0,170)}));
  await page.screenshot({path:"artifacts/"+name+"-research-analysis.png",fullPage:true});
  await page.evaluate(()=>{
    const bond=typeof s!=="undefined"?s.items.find(x=>x.kind==="bono"):null;
    if(bond){s.selected=bond.symbol;renderDetail();}
  });
  const bondStudy=await page.locator("#detailPanel .research-panel").innerText();
  assert(bondStudy.includes("TIR")&&bondStudy.includes("SIN niveles de operación"),
    "Bond must not pretend to have verified coupon, yield or stop/TP levels");
  // Restore stock for remainder of visual smoke test.
  await page.evaluate(()=>{if(typeof s!=="undefined"){s.selected="CEPU";renderDetail();}});

  console.log("POSITION_SIM",name,JSON.stringify(simulation));
    await page.screenshot({path:`artifacts/${name}-recommendations.png`,fullPage:true});
  console.log("recommendations_on_all_assets",name,JSON.stringify({label:advice.label,table:advice.row}));
  await page.screenshot({path:`artifacts/${name}-cepu.png`,fullPage:true});
  // Verify unmatched symbol never impersonates a valid chart.
  await page.evaluate(()=>document.dispatchEvent(new CustomEvent("byma:selection",{detail:{symbol:"__MISSING__"}})));
  await page.waitForFunction(()=>document.querySelector("#chartEmpty").hidden===false);
  const warning=await page.locator("#chartEmpty").innerText();
  assert(warning.includes("NO como gráfico"),"Missing chart must be explained accurately");
  await page.selectOption("#chartSymbolPicker","BBAR");
  await page.waitForFunction(()=>document.querySelector("#chartEmpty").hidden===true);
  assert.equal(errors.length,0,"Browser errors: "+errors.join("; "));
  console.log("PASS",name,JSON.stringify(info));
 }catch(e){allOk=false;console.error("FAIL",name,e.message,"browser errors:",errors);}
 finally{await page.close();}
}
await browser.close();
if(!allOk)process.exit(1);
