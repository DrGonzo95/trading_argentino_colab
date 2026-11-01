"use strict";
(()=>{
  let deferred=null;
  const button=document.getElementById("installApp");
  const tip=document.getElementById("installHelp");
  if("serviceWorker" in navigator && (location.protocol==="https:" || location.hostname==="localhost")){
    window.addEventListener("load",()=>navigator.serviceWorker.register("./sw.js",{scope:"./"}).catch(e=>console.warn("PWA",e)));
  }
  window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();deferred=e;});
  window.addEventListener("appinstalled",()=>{deferred=null;if(button)button.textContent="✓ Instalada";});
  button?.addEventListener("click",async()=>{
    if(deferred){
      const event=deferred;deferred=null;await event.prompt();
    }else if(tip){
      tip.hidden=false;
      tip.textContent="Para instalar Pulso BYMA: abrí el menú del navegador → Instalar aplicación / Agregar a pantalla de inicio. En iPhone: Compartir → Agregar a inicio.";
      setTimeout(()=>tip.hidden=true,9000);
    }
  });
})();