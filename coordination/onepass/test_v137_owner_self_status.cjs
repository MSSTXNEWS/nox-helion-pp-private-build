const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const SOURCE=fs.readFileSync('coordination/onepass/nox-v137-owner-self-status.js','utf8');
class El {
  constructor(tag,doc){
    this.tagName=tag;this.doc=doc;this.children=[];this.dataset={};this.style={};
    this.listeners={};this.hidden=false;this.textContent='';this.className='';
  }
  append(...elements){this.children.push(...elements);}
  querySelector(selector){
    if(selector==='[data-nox-self-monitor="v137"]')
      return this.children.find(e=>e.dataset.noxSelfMonitor==='v137')||null;
    const key={
      '[data-nox-monitor-source]':'noxMonitorSource',
      '[data-nox-monitor-values]':'noxMonitorValues'
    }[selector];
    if(key)return this.children.find(e=>e.dataset[key]==='true')||null;
    return null;
  }
  addEventListener(type,cb){(this.listeners[type]??=[]).push(cb);}
  click(){for(const cb of this.listeners.click??[])cb({target:this});}
}
function harness({owner=true,path='/nox-web-v29/pc/resonance.html',reply=null,v22=false}={}){
  const doc={readyState:'complete',visibilityState:'visible',listeners:{},system:null,aside:null};
  if(v22)doc.aside=new El('aside',doc);
  else doc.system=new El('aside',doc);
  doc.getElementById=id=>id==='v24System'?doc.system:null;
  doc.querySelector=selector=>selector==='.nox-v22-left'?doc.aside:null;
  doc.createElement=tag=>new El(tag,doc);
  doc.addEventListener=(kind,cb)=>{(doc.listeners[kind]??=[]).push(cb);};
  let requests=0;
  const fetch=async url=>{
    requests++;
    if(reply===null)return new Response('Not Found',{status:404});
    const val=reply(url);
    return new Response(JSON.stringify(val),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const context={window:{NOX_NATIVE_OWNER:owner,fetch},document:doc,
    location:{pathname:path},setTimeout:(cb)=>{cb();return 1;},
    clearTimeout:()=>{},setInterval:()=>{},AbortController,Response,
    Date,console};
  vm.runInNewContext(SOURCE,context);
  return {doc,window:context.window,get requests(){return requests;},
    trigger:()=>{for(const f of doc.listeners.click??[])f({
      target:{closest:()=>({dataset:{action:'open-system'}})}
    });},
    update:async()=>{const s=(doc.system||doc.aside).children[0];
      const btn=s.children.find(x=>x.dataset.action==='nox-self-refresh');
      assert(btn);btn.click();await new Promise(ok=>setImmediate(ok));
      return s;}
  };
}
test('owner-only monitor not installed on public/foreign frontend',()=>{
 for(const [owner,path] of [[false,'/nox-web-v29/pc/resonance.html'],
  [true,'/chat.html'],[true,'/pc/resonance.html']]){
  const h=harness({owner,path});
  assert.equal(h.doc.system.children.length,0);
  assert.equal(h.requests,0);
 }
});
test('real native read-only service receipt renders verified state not fake training',async()=>{
 const h=harness({reply:()=>({
  schema:'NOX_V137_OWNER_SELF_OBSERVATION_V1',
  status:'READY',collected_at_utc:'2026-11-15T00:00:00Z',
  service_observation:{state:'OBSERVED',services:[
   {name:'nox-proxy',state:'RUNNING'},{name:'nox-train-volta-t866u',state:'EXITED'}]},
  gpu_observation:{state:'OBSERVED',devices:[{
   index:0,gpu_percent:16,vram_used_mib:27000,vram_total_mib:32768,
   gpu_core_temp_c:40}]},
  s03_observation:{state:'OBSERVED',fact_rows:210},
  training:{positive_optimizer_steps_verified:false},
  stop:{flag_present:false}
 })});
 const p=await h.update();
 const text=p.querySelector('[data-nox-monitor-values]').textContent;
 assert(text.includes('nox-proxy — RUNNING'));
 assert(text.includes('nox-train-volta-t866u — EXITED'));
 assert(text.includes('новые шаги оптимизатора не подтверждены'));
 assert(text.includes('S03: 210'));
 assert(!text.includes('100% обучения'));
});
test('missing live host becomes HOLD rather than staged fake success',async()=>{
 const h=harness();
 const p=await h.update();
 assert.equal(p.dataset.status,'HOLD');
 assert(p.querySelector('[data-nox-monitor-values]').textContent.includes('HOLD'));
 assert(h.requests>=4);
});
test('existing V125 endpoints are bounded and labeled as incomplete fallback',async()=>{
 const h=harness({reply:url=>{
  if(url==='/api/nox/self/observations')throw Error('not installed');
  if(url==='/api/nox/system/processes')return {
   status:'READY',source:'PROCFS',observed_count:42,
   categories:{python:6,llama:2,supervisor:1,node:1}};
  if(url==='/api/status')return {status:'READY',source:'NOX_VAST_PROCFS_NVIDIA_SMI',
   gpus:[{index:0,gpu_percent:18,vram_used_gib:27}]};
  return {status:'HOLD'};
 }});
 const p=await h.update();
 const text=p.querySelector('[data-nox-monitor-values]').textContent;
 assert.equal(p.dataset.status,'OBSERVED');
 assert(text.includes('полный монитор V137 не установлен'));
 assert(text.includes('GPU0: 18%'));
 assert(text.includes('Тренер: HOLD'));
 assert(text.includes('S03: не проверялась'));
});

test('original V22 owner sees source-gated read-only monitor in existing sidebar',async()=>{
 const h=harness({v22:true,path:'/nox-web-v29/pc/v22/resonance.template.html'});
 assert.equal(h.doc.system,null);
 assert.equal(h.doc.aside.children.length,1);
 const box=await h.update();
 assert.equal(box.className,'nox-v22-card panel');
 assert.equal(box.dataset.status,'HOLD');
 assert(box.querySelector('[data-nox-monitor-values]').textContent.includes('HOLD'));
 assert(h.requests>=4);
});
