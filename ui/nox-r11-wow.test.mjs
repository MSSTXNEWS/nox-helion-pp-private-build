import test from 'node:test';
import assert from 'node:assert/strict';
import {R11_WORLD_IDS,R11_READ_ACTIONS,projectNativeReply,isTrustedInstallerEvent,mountR11WowMenu} from '../ui/nox-r11-wow.mjs';
class FakeElement {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.parentElement=null;this.dataset={};this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.listeners=new Map();this.attrs={};this.style={};this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x)};}
  append(...nodes){for(const n of nodes){if(n.parentElement)n.remove();n.parentElement=this;this.children.push(n)}}
  prepend(...nodes){for(const n of [...nodes].reverse()){if(n.parentElement)n.remove();n.parentElement=this;this.children.unshift(n)}}
  remove(){if(this.parentElement){const i=this.parentElement.children.indexOf(this);if(i>=0)this.parentElement.children.splice(i,1);this.parentElement=null}}
  replaceChildren(...nodes){for(const c of this.children)c.parentElement=null;this.children=[];this.append(...nodes)}
  setAttribute(k,v){this.attrs[k]=v}getAttribute(k){return this.attrs[k]||null}
  addEventListener(k,f){const a=this.listeners.get(k)||[];a.push(f);this.listeners.set(k,a)}
  removeEventListener(k,f){this.listeners.set(k,(this.listeners.get(k)||[]).filter(x=>x!==f))}
  dispatch(k,extra={}){const e={type:k,key:'',preventDefault(){this.prevented=true},...extra};for(const fn of this.listeners.get(k)||[])fn(e);return e;}
  click(){if(!this.disabled)this.dispatch('click')}
  focus(){this.focused=true}
  closest(selector){if(selector==='[data-nox-page="home"]')return null;if(selector==='[hidden]')return this.parentElement?.hidden?this.parentElement:null;return null}
  querySelectorAll(selector){const out=[];const prop=selector==='[data-nox-world]'?'noxWorld':null;const recurse=n=>{for(const c of n.children){if(prop&&Object.hasOwn(c.dataset,prop))out.push(c);recurse(c)}};recurse(this);return out}
  querySelector(selector){if(selector==='[data-nox-r11="mounted"]')return this.children.find(c=>c.dataset.noxR11==='mounted')||null;if(selector==='[data-nox-r11-ticker]')return this.children.find(c=>c.dataset.noxR11Ticker==='true')||null;return null}
}
function fixture(){
  const root=new FakeElement(),status=new FakeElement();
  const worlds=R11_WORLD_IDS.map(id=>{const e=new FakeElement('button');e.dataset.noxWorld=id;e.textContent=id;root.append(e);return e});
  let requests=[],queue=[],timerFns=new Map(),next=1;const eventSource=new FakeElement('webview');
  const doc=new FakeElement('document');doc.createElement=x=>new FakeElement(x);doc.getElementById=x=>x==='status'?status:null;
  let currentScope={core_id:'core.atlas',persona_id:'persona.kairen_voss'};
  const windowRef={matchMedia:()=>({matches:false})};
  const make=()=>mountR11WowMenu({root,documentRef:doc,windowRef,scope:()=>currentScope,
    nativeEventSource:eventSource,request:async(route,payload)=>{requests.push({route,payload});return queue.shift()||{state:'HOLD',errorCode:'OFFLINE'}},
    now:()=>10000,schedule:fn=>{const id=next++;timerFns.set(id,fn);return id;},cancel:id=>timerFns.delete(id)});
  return {root,status,worlds,doc,eventSource,make,requests,queue,timerFns,setScope:v=>{currentScope=v}};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('exact 10 approved logical worlds, 8 physical parents remain external',()=>{
  assert.equal(R11_WORLD_IDS.length,10);assert.equal(new Set(R11_WORLD_IDS).size,10);
  assert.equal(R11_READ_ACTIONS.length,10);
  assert.ok(R11_READ_ACTIONS.every(x=>['models.catalog','models.queue','models.preflight','gpu.preflight','chat.model','chat.commands'].includes(x.route)));
});
test('typed native result never invents successful AI / GPU / percent',()=>{
  assert.deepEqual(projectNativeReply({state:'UNVERIFIED'}),{state:'HOLD',label:'Нет подтверждённого ответа ядра',value:'Н/Д'});
  assert.equal(projectNativeReply({state:'COMPLETED',result:{status:'READY'}}).value,'Н/Д');
  assert.equal(projectNativeReply({state:'COMPLETED',result:{models:[]}}).value,'0');
  assert.equal(projectNativeReply({state:'STOP_REQUESTED'}).state,'STOP_REQUESTED');
  assert.equal(projectNativeReply({state:'HOLD',errorCode:'NATIVE_DENIED'}).state,'HOLD');
});
test('unsigned stale forged telemetry never trusted',()=>{
  const good={schema:'NOX-INSTALLER-EVENT-v3',evidence_verified:true,event_id:'x1',run_id:'run',task_id:'task',action_id:'training.eval',event_sequence:2,receipt_sha256:'a'.repeat(64),timestamp_utc:new Date(10000).toISOString()};
  assert.equal(isTrustedInstallerEvent(good,10000),true);
  assert.equal(isTrustedInstallerEvent({...good,evidence_verified:false},10000),false);
  assert.equal(isTrustedInstallerEvent({...good,timestamp_utc:new Date(10000-32000).toISOString()},10000),false);
  assert.equal(isTrustedInstallerEvent({...good,receipt_sha256:'broken'},10000),false);
});
test('actual original buttons survive mount, real click drives existing native request',async()=>{
  const f=fixture(),r=f.make();
  assert.equal(r.snapshot().worldCount,10);assert.equal(f.root.querySelectorAll('[data-nox-world]').length,10);
  const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const b=panel.children.find(x=>x.className==='nox-r11-actions').children[0];
  assert.ok(b);f.queue.push({state:'COMPLETED',result:{models:['first','second']}});b.click();await flush();
  assert.deepEqual(f.requests,[{route:'models.catalog',payload:{}}]);
  assert.equal(f.status.querySelector('[data-nox-r11-ticker]').dataset.state,'verified');
  assert.equal(r.snapshot().hasNativeProof,true);
  assert.equal(f.root.querySelectorAll('[data-nox-world]').length,10);
  for(const fn of f.timerFns.values())fn();
  assert.equal(r.snapshot().hasNativeProof,false);
  r.destroy();assert.equal(f.status.children.length,0);assert.equal(f.root.querySelectorAll('[data-nox-world]').length,10);
});
test('AI source action scope required, no silent execution without CoreID/Persona',async()=>{
  const f=fixture(),r=f.make();const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const actions=panel.children.find(x=>x.className==='nox-r11-actions').children;
  f.setScope({core_id:'',persona_id:''});actions[5].click();await flush();assert.equal(f.requests.length,0);
  f.setScope({core_id:'core.atlas',persona_id:'persona.kairen_voss'});
  f.queue.push({state:'HOLD',errorCode:'NO_NATIVE_HANDLER'});actions[5].click();await flush();
  assert.equal(f.requests.length,1);assert.equal(f.requests[0].route,'chat.commands');
  assert.equal(f.requests[0].payload.action,'selfbuilder.sources.inspect');
  assert.equal(f.status.querySelector('[data-nox-r11-ticker]').dataset.state,'hold');r.destroy();
});
test('STOP uses existing native route, does not invent termination',async()=>{
  const f=fixture(),r=f.make();const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const actions=panel.children.find(x=>x.className==='nox-r11-actions').children;
  f.queue.push({state:'STOP_REQUESTED'});actions.at(-1).click();await flush();
  assert.equal(f.requests.at(-1).route,'chat.stop');
  assert.ok(f.status.querySelector('[data-nox-r11-ticker]').children[1].textContent.includes('ожидается'));
  r.destroy();
});
test('Ctrl+K search opens existing original button only and Escape closes',()=>{
  const f=fixture(),r=f.make();const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const p=panel.children.find(x=>x.dataset.noxR11Palette==='true');
  assert.equal(p.hidden,true);f.doc.dispatch('keydown',{ctrlKey:true,key:'k'});assert.equal(p.hidden,false);
  let n=0;f.worlds[0].addEventListener('click',()=>n++);
  const input=p.children[0];input.value='work';input.dispatch('input');
  const buttons=p.children[1].children;assert.equal(buttons.length,1);buttons[0].click();assert.equal(n,1);
  assert.equal(p.hidden,true);f.doc.dispatch('keydown',{ctrlKey:true,key:'k'});f.doc.dispatch('keydown',{key:'Escape'});assert.equal(p.hidden,true);
  r.destroy();
});
test('duplicate mount rejected, cleanup restores all visual classes',()=>{
  const f=fixture(),r=f.make();assert.throws(()=>f.make(),/ONEHOST_ORIGINAL_MENU_REQUIRED/);
  assert.ok(f.worlds[0].classList.contains('nox-r11-world'));
  r.destroy();assert.equal(f.worlds[0].classList.contains('nox-r11-world'),false);
});
test('incomplete approved MENU DOM fails closed before any DOM changes',()=>{
  const f=fixture();f.worlds.at(-1).remove();assert.throws(()=>f.make(),/TEN_ORIGINAL_SUBWORLDS_REQUIRED/);
  assert.equal(f.status.children.length,0);
});

test('native v3 event only after coherent verified evidence, monotonic run sequence and 30-second expiry',()=>{
  const f=fixture(),r=f.make();const ticker=f.status.querySelector('[data-nox-r11-ticker]');
  const good={schema:'NOX-INSTALLER-EVENT-v3',evidence_verified:true,event_id:'id1',run_id:'run1',task_id:'task1',action_id:'model.pull',event_type:'task.progress',state:'RUNNING',package_id:'P03',event_sequence:1,receipt_sha256:'f'.repeat(64),timestamp_utc:new Date(10000).toISOString(),numerator:2,denominator:4};
  f.eventSource.dispatch('message',{data:{installerEvent:{...good,state:'FAILED'}}});assert.equal(ticker.dataset.state,'unknown');
  f.eventSource.dispatch('message',{data:{installerEvent:good}});assert.equal(ticker.dataset.state,'verified');assert.ok(ticker.children[1].textContent.includes('50%'));
  f.eventSource.dispatch('message',{data:{installerEvent:{...good,event_sequence:1,numerator:4}}});assert.ok(ticker.children[1].textContent.includes('50%'));
  f.eventSource.dispatch('message',{data:{installerEvent:{...good,event_sequence:2,numerator:4,receipt_sha256:'bad'}}});assert.ok(ticker.children[1].textContent.includes('50%'));
  for(const fn of f.timerFns.values())fn();assert.equal(ticker.dataset.state,'stale');
  r.destroy();assert.equal((f.eventSource.listeners.get('message')||[]).length,0);
});

test('STOP fence excludes a late native completion even after ACK',async()=>{
  const f=fixture(),r=f.make();const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const actions=panel.children.find(x=>x.className==='nox-r11-actions').children;
  let finish;f.queue.push(new Promise(resolve=>{finish=resolve}));actions[0].click();await flush();
  f.queue.push({state:'STOP_REQUESTED'});actions.at(-1).click();await flush();
  const ticker=f.status.querySelector('[data-nox-r11-ticker]');
  assert.equal(ticker.dataset.state,'pending');
  assert.match(ticker.children[1].textContent,/STOP/);
  finish({state:'COMPLETED',result:{models:['old'],status:'READY'}});await flush();
  assert.match(ticker.children[1].textContent,/STOP/);
  assert.notEqual(ticker.dataset.state,'verified');r.destroy();
});
test('bad counter does not reserve native event sequence and block corrected input',()=>{
  const f=fixture(),r=f.make();const ticker=f.status.querySelector('[data-nox-r11-ticker]');
  const ev={schema:'NOX-INSTALLER-EVENT-v3',evidence_verified:true,event_id:'valid-1',run_id:'r11',task_id:'t11',
    action_id:'model.pull',event_type:'task.progress',state:'RUNNING',package_id:'P03',event_sequence:4,
    receipt_sha256:'e'.repeat(64),timestamp_utc:new Date(10000).toISOString(),numerator:10,denominator:0};
  f.eventSource.dispatch('message',{data:{installerEvent:ev}});
  assert.equal(ticker.dataset.state,'unknown');
  f.eventSource.dispatch('message',{data:{installerEvent:{...ev,denominator:20}}});
  assert.equal(ticker.dataset.state,'verified');assert.match(ticker.children[1].textContent,/50%/);r.destroy();
});
test('ticker button opens corresponding existing read-only native action on user click',async()=>{
  const f=fixture(),r=f.make();const ticker=f.status.querySelector('[data-nox-r11-ticker]');
  const ev={schema:'NOX-INSTALLER-EVENT-v3',evidence_verified:true,event_id:'native-1',run_id:'r11',task_id:'t11',
    action_id:'model.pull',event_type:'task.progress',state:'RUNNING',package_id:'P03',event_sequence:1,
    receipt_sha256:'e'.repeat(64),timestamp_utc:new Date(10000).toISOString(),numerator:5,denominator:20};
  f.eventSource.dispatch('message',{data:{installerEvent:ev}});
  const button=ticker.children[2];assert.equal(button.hidden,false);
  f.queue.push({state:'COMPLETED',result:{jobs:[]}});button.click();await flush();
  assert.equal(f.requests.at(-1).route,'models.queue');r.destroy();
});

test('browser.open native HOLD is surfaced immediately without fake navigation success',async()=>{
  const f=fixture(),r=f.make();const panel=f.root.querySelector('[data-nox-r11="mounted"]');
  const input=panel.children.find(x=>x.type==='url');
  const button=panel.children.find(x=>x.textContent==='Открыть HTTPS');
  const feedback=panel.children.find(x=>x.className==='nox-r11-feedback');
  input.value='https://docs.example.org';
  f.queue.push({state:'HOLD',errorCode:'BROWSER_NATIVE_POLICY_HOLD'});
  button.click();await flush();
  assert.equal(f.requests.at(-1).route,'browser.open');
  assert.equal(feedback.dataset.state,'HOLD');
  assert.match(feedback.textContent,/BROWSER_NATIVE_POLICY_HOLD/);
  f.queue.push({state:'COMPLETED',result:{status:'NAVIGATION_REQUESTED'}});
  button.click();await flush();
  assert.equal(feedback.dataset.state,'pending');
  assert.match(feedback.textContent,/не подтверждён/);
  input.value='http://unsafe.example.org';button.click();await flush();
  assert.equal(f.requests.length,2);
  assert.equal(feedback.dataset.state,'HOLD');
  r.destroy();
});
