// ui/ev-b02-native-queue.test.mjs — add file exactly alongside production edit
// node --test ui/ev-b02-native-queue.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {createNativeMenuClient} from './onehost-menu-bindings.mjs';
import {mountSelfBuilderMenuV2,P01_MENU_WORLD_NAV} from './selfbuilder-menu-v2.mjs';

function nativeFixture(){
  const sent=[];let receiver;let nonce=0;
  const bridge={postMessage(message){sent.push(message)},
    addEventListener(kind,cb){assert.equal(kind,'message');receiver=cb},
    removeEventListener(){}};
  const client=createNativeMenuClient({webview:bridge,cryptoRef:{getRandomValues(bytes){
    for(let i=0;i<bytes.length;i++)bytes[i]=(nonce+i)%256;nonce++;return bytes;
  }}});
  const reply=(req,data)=>receiver({data:{kind:'p02NativeResult',requestId:req.requestId,
    routeId:req.routeId,...data}});
  return {sent,client,reply};
}

test('P03 queue uses the one bounded native transport; no forged ACK or fake completion',async()=>{
  const f=nativeFixture();
  const pending=f.client.request('models.queue',{});
  const req=f.sent.at(-1);
  assert.equal(req.kind,'p02.native');assert.equal(req.routeId,'models.queue');
  assert.deepEqual(req.payload,{});assert.match(req.requestId,/^[a-f0-9]{32}$/);
  let settled=false;pending.then(()=>{settled=true});
  f.reply(req,{routeId:'models.cancel',state:'COMPLETED',result:{jobs:[]}});
  await Promise.resolve();assert.equal(settled,false,'wrong-route ACK must not resolve');
  f.reply(req,{state:'COMPLETED',result:{jobs:[{id:'native-job',state:'Running'}]}});
  assert.deepEqual((await pending).result.jobs,[{id:'native-job',state:'Running'}]);
  const cancel=f.client.request('models.cancel',{jobId:'native-job'});
  const stopReq=f.sent.at(-1);assert.equal(stopReq.routeId,'models.cancel');
  f.reply(stopReq,{state:'STOP_REQUESTED',result:{cancelled:true}});
  assert.equal((await cancel).state,'STOP_REQUESTED','STOP requested is not download completed');
  await assert.rejects(f.client.request('system.pc_control',{}),/NOX_NATIVE_REQUEST_DENIED/);
  f.client.destroy();
});

class Node {
  constructor(doc,tag){this.ownerDocument=doc;this.tagName=tag;this.children=[];this.dataset={};
    this.handlers=new Map();this.textContent='';this.value='';this.disabled=false;this.hidden=false;}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n)}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes)}
  addEventListener(name,handler){this.handlers.set(name,handler)}
  setAttribute(name,value){this[name]=value}
  querySelector(){return null}
  closest(){return null}
  focus(){}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this)}
  dispatch(name){return this.handlers.get(name)?.({target:this,preventDefault(){}})}
}
function dom(){const doc={createElement:(tag)=>new Node(doc,tag)};return {doc,root:doc.createElement('div')}}
function find(root,fn){if(fn(root))return root;for(const child of root.children){const hit=find(child,fn);if(hit)return hit}return null}
function mounted(invokeP03Queue,invokeP03Cancel=null){
  const {doc,root}=dom();
  const menu=mountSelfBuilderMenuV2({root,documentRef:doc,invokeNative:async()=>({ack:false}),
    invokeP03Queue,invokeP03Cancel,getTrustedState:()=>({available:false}),ownerApprovedRoute:()=>true,
    getCurrentSection:()=> 'РАЗВИТИЕ'});
  const button=find(root,x=>x.dataset.noxP03Queue==='native-only');
  const feedback=find(root,x=>x.textContent==='P03 · ожидание native ACK');
  assert.ok(button);assert.ok(feedback);
  return {root,button,feedback,menu};
}

test('P03 only renders a native-ACKed queue count in the original development subview',async()=>{
  assert.equal(P01_MENU_WORLD_NAV.length,10,'10 logical worlds; no extra top-level tile');
  const ui=mounted(async()=>({ack:true,jobs:[{id:'one',state:'Queued'}]}));
  await ui.button.dispatch('click');
  assert.match(ui.feedback.textContent,/P03 · 1 заданий/);
  assert.match(ui.feedback.textContent,/STOP .* native cancel/);
  assert.equal(ui.button.disabled,false);ui.menu.destroy();
});

test('denied/unsupported native queue leaves an honest HOLD and no pretend progress',async()=>{
  const ui=mounted(async()=>({ack:false,errorCode:'NATIVE_PERMISSION_DENIED'}));
  await ui.button.dispatch('click');
  assert.match(ui.feedback.textContent,/HOLD · P03 · NATIVE_PERMISSION_DENIED/);
  assert.doesNotMatch(ui.feedback.textContent,/COMPLETED|100%|LIVE/);
  ui.menu.destroy();
});

test('only one P03 request per pending click; STOP or owner consent are not synthesized',async()=>{
  let finish,requests=0;
  const ui=mounted(()=>{requests++;return new Promise(resolve=>{finish=resolve})});
  const inFlight=ui.button.dispatch('click');ui.button.dispatch('click');
  assert.equal(requests,1);assert.equal(ui.button.disabled,true);
  assert.equal(ui.button.dataset.state,'PENDING');
  finish({ack:false,errorCode:'P03_QUEUE_UNAVAILABLE'});await inFlight;
  assert.match(ui.feedback.textContent,/HOLD/);assert.equal(ui.button.disabled,false);
  ui.menu.destroy();
});

test('Native P03 STOP is bounded to verified active job IDs and never claims download complete',async()=>{
  const cancelled=[];
  const ui=mounted(async()=>({ack:true,jobs:[{id:'job-1',state:'Running'},
    {id:'job-1',state:'Queued'},{id:'bad/id',state:'Downloading'},
    {id:'finished',state:'Completed'}]}),async id=>{cancelled.push(id);return {ack:true,state:'STOP_REQUESTED'}});
  await ui.button.dispatch('click');
  const stop=find(ui.root,x=>x.dataset.noxP03Stop==='job-1');
  assert.ok(stop);assert.equal(find(ui.root,x=>x.dataset.noxP03Stop==='bad/id'),null);
  await stop.dispatch('click');assert.deepEqual(cancelled,['job-1']);
  assert.match(ui.feedback.textContent,/STOP REQUESTED/);
  assert.doesNotMatch(ui.feedback.textContent,/COMPLETED|100%|LIVE/);
  assert.equal(stop.disabled,true);ui.menu.destroy();
});
test('Denied native P03 STOP shows HOLD and keeps explicit retry possible',async()=>{
  const ui=mounted(async()=>({ack:true,jobs:[{id:'j2',state:'Queued'}]}),
    async()=>({ack:false,errorCode:'NATIVE_CONSENT_DENIED'}));
  await ui.button.dispatch('click');
  const stop=find(ui.root,x=>x.dataset.noxP03Stop==='j2');assert.ok(stop);
  await stop.dispatch('click');
  assert.match(ui.feedback.textContent,/HOLD · P03 STOP · NATIVE_CONSENT_DENIED/);
  assert.equal(stop.disabled,false);ui.menu.destroy();
});

test('missing P03 port is disabled, without creating a second model queue',()=>{
  const ui=mounted(null);
  assert.equal(ui.button.disabled,true);assert.equal(ui.button.dataset.state,'HOLD');
  ui.menu.destroy();
});
