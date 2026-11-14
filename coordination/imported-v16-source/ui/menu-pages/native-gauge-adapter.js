/* NOX · original naikus/svg-gauge (MIT) adapter for native receipts only.
 * No simulations, no timers, no privileged actions. */
(function(){
 'use strict';
 const percentageKey=/^(?:cpu|gpu|vram|ram|memory|progress|training|utilization|usage|load)[\w-]*(?:percent|percentage|pct|_utilization|_usage)$/i;
 function percentage(key,value){
   if(!percentageKey.test(String(key)))return null;
   if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>100)return null;
   return value;
 }
 function mount(parent,key,value){
   const n=percentage(key,value);
   if(n===null||!parent||typeof window.Gauge!=='function')return false;
   const wrapper=parent.ownerDocument.createElement('div');
   wrapper.className='nox-native-svg-gauge';wrapper.dataset.nativeMetric=String(key);
   wrapper.setAttribute('role','img');wrapper.setAttribute('aria-label',String(key)+': '+n+'% (подтверждено OneHost)');
   const name=parent.ownerDocument.createElement('span');
   name.className='nox-native-gauge-label';name.textContent=String(key).slice(0,80);
   const graph=parent.ownerDocument.createElement('div');graph.className='nox-native-gauge-canvas';
   wrapper.append(name,graph);parent.append(wrapper);
   try{
     const gauge=window.Gauge(graph,{min:0,max:100,value:n,showValue:true,label:v=>Math.round(v)+'%'});
     if(!gauge){wrapper.remove();return false;}
     return true;
   }catch{wrapper.remove();return false;}
 }
 window.NOXNativeGauge=Object.freeze({mount,percentage});
})();
