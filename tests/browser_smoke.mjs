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
