"use strict";
const SHELL="pulso-byma-shell-v2", DATA="pulso-byma-data-v1";
const FILES=["./","./index.html","./styles.css","./app.js","./charts.js","./pro.js?v=2","./pro.css?v=2","./pwa.js","./manifest.webmanifest","./icon.svg"];
self.addEventListener("install",event=>{
  event.waitUntil(caches.open(SHELL).then(c=>c.addAll(FILES)));
});
self.addEventListener("activate",event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(x=>x.startsWith("pulso-byma-")&&x!==SHELL&&x!==DATA).map(x=>caches.delete(x)))));
});
self.addEventListener("fetch",event=>{
  const req=event.request;
  if(req.method!=="GET")return;
  const url=new URL(req.url);
  if(url.origin!==self.location.origin)return;
  if(/\/data\/(market|charts)\.json$/.test(url.pathname)){
    event.respondWith(fetch(req,{cache:"no-store"}).then(async response=>{
      if(response.ok)(await caches.open(DATA)).put(url.pathname,response.clone());
      return response;
    }).catch(async()=>await (await caches.open(DATA)).match(url.pathname)||Response.error()));
  }
});