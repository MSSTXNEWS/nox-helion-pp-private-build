import test from 'node:test';
import assert from 'node:assert/strict';
import {createNativeMenuClient,mountOneHostMenu,canonicalChatContext,nativeAutostartPersistenceAck,createAutostartOwnerFlow,AUTOSTART_UIA_IDS,settingsAutostartOwnerAdmission} from '../../ui/onehost-menu-bindings.mjs';
import {SELFBUILDER_MENU,MENU_V2_SECTIONS} from '../../ui/selfbuilder-menu-v2.mjs';
function fixture(){let listener;const sent=[];let next=1;const webview={postMessage:x=>sent.push(x),addEventListener:(n,f)=>listener=f,removeEventListener:()=>{listener=null;}};const client=createNativeMenuClient({webview,cryptoRef:{getRandomValues:b=>{b.fill(next++);return b;}},timeoutMs:10});return {client,sent,webview,reply:x=>listener?.({data:x,source:webview,isTrusted:true}),emit:(x,source,trusted=false)=>listener?.({data:x,source,isTrusted:trusted})};}
test('native result must correlate route and nonce; stream only that request',async()=>{
 const f=fixture(),events=[];const p=f.client.request('helion.chat',{text:'hi'},e=>events.push(e));const req=f.sent[0];
 f.reply({kind:'p02NativeEvent',requestId:req.requestId,routeId:'chat.model',state:'STREAMING',data:{route:'chat.model',delta:'bad'}});
 f.reply({kind:'p02NativeEvent',requestId:req.requestId,routeId:req.routeId,state:'STREAMING',data:{route:req.routeId,delta:'ok'}});
 f.reply({kind:'p02NativeResult',requestId:req.requestId,routeId:req.routeId,state:'COMPLETED',result:{answer:'ok',done:true}});
 assert.equal((await p).result.answer,'ok');assert.deepEqual(events,[{route:'helion.chat',delta:'ok'}]);f.client.destroy();
});
test('page authority and unknown actions fail before native dispatch',async()=>{
 const f=fixture();await assert.rejects(f.client.request('chat.model',{principal:'owner'}),/DENIED/);
 await assert.rejects(f.client.request('chat.commands',{action:'exec'}),/DENIED/);assert.equal(f.sent.length,0);f.client.destroy();
});
test('timeout is not STOP or completion',async()=>{const f=fixture();await assert.rejects(f.client.request('chat.history'),/^Error: TIMEOUT$/);f.client.destroy();});
test('document teardown rejects pending and cannot submit again',async()=>{const f=fixture();const p=f.client.request('chat.history');f.client.destroy();await assert.rejects(p,/DOCUMENT_CLOSED/);await assert.rejects(f.client.request('chat.stop'),/DISPOSED/);});
test('approved local origin only, preserving eight menu sections',()=>{
 assert.equal(mountOneHostMenu({documentRef:{},windowRef:{location:{origin:'https://example.org'}}}),null);
 assert.equal(MENU_V2_SECTIONS.length,8);assert.equal(new Set(MENU_V2_SECTIONS).size,8);
 assert.ok(SELFBUILDER_MENU.every(x=>MENU_V2_SECTIONS.includes(x.section)));
});

test('selectors map exact original IDs without fallback persona or core',()=>{
 assert.deepEqual(canonicalChatContext('CORE','cassien'),{core_id:'core.core',persona_id:'persona.kassien_veir'});
 assert.deepEqual(canonicalChatContext('unknown','unknown'),{core_id:'',persona_id:''});
});

class Node {
 constructor(tag,doc){this.tag=tag;this.ownerDocument=doc;this.dataset={};this.children=[];this.listeners={};this.textContent='';this.value='';}
 replaceChildren(){this.children=[];}
 append(...nodes){this.children.push(...nodes);for(const n of nodes)n.parent=this;}
 setAttribute(name,value){this[name]=value;}
 addEventListener(name,callback){this.listeners[name]=callback;}
 remove(){}
 closest(){return null;}
 querySelector(){return null;}
 focus(){}
}
const walk=node=>[node,...node.children.flatMap(walk)];
test('MENU read response is received; propose waits for real queue ACK and uses bounded task',async()=>{
 const {mountSelfBuilderMenuV2}=await import('../../ui/selfbuilder-menu-v2.mjs');
 const doc={createElement:tag=>new Node(tag,doc)},root=new Node('div',doc);let section='РАЗВИТИЕ',last;
 const menu=mountSelfBuilderMenuV2({root,documentRef:doc,getCurrentSection:()=>section,
  ownerApprovedRoute:()=>true,getTrustedState:()=>({available:true,status:'AVAILABLE',ownerConsent:true}),
  invokeNative:async request=>{last=request;return request.actionId==='selfbuilder.propose'?{ack:true,run_id:'S03-7'}:{ack:true,status:'S03_READ'};}});
 const nodes=walk(root),feedback=nodes.find(x=>x.className==='nox-sb-feedback');
 const read=nodes.find(x=>x.dataset.actionId==='selfbuilder.study.queue');
 await read.listeners.click();assert.match(feedback.textContent,/ПОЛУЧЕНО/);assert.equal(read.dataset.state,'AVAILABLE');
 section='РАБОТА';menu.refresh();const task=nodes.find(x=>x.tag==='textarea');task.value='Create the requested existing-source feature';
 const propose=nodes.find(x=>x.dataset.actionId==='selfbuilder.propose');await propose.listeners.click();
 assert.equal(last.task,task.value);assert.match(feedback.textContent,/QUEUED.*S03-7/);
 assert.equal(nodes.filter(x=>x.dataset.section==='РАЗВИТИЕ').every(x=>x.hidden),true);menu.destroy();
});

test('model import and adapter operations carry approved identifiers, never page paths',async()=>{
 const f=fixture();
 await assert.rejects(f.client.request('models.gguf.import',{modelTag:'reviewed',path:'C:/private.gguf'}),/SELECTION_REQUIRED/);
 await assert.rejects(f.client.request('chat.commands',{action:'training.activate',job_id:'approved',path:'C:/weights'}),/TRAINING_JOB_REQUIRED/);
 assert.equal(f.sent.length,0);f.client.destroy();
});
test('FORGE controls require native-listed job and pass only its identifier',async()=>{
 const {mountSelfBuilderMenuV2}=await import('../../ui/selfbuilder-menu-v2.mjs');
 const doc={createElement:tag=>new Node(tag,doc)},root=new Node('div',doc);let last;
 const menu=mountSelfBuilderMenuV2({root,documentRef:doc,getCurrentSection:()=> 'РАЗВИТИЕ',
  ownerApprovedRoute:()=>true,getTrustedState:()=>({available:true,status:'AVAILABLE',requiresNativeConsent:true}),
  getTrainingJobs:()=>[{id:'native-job-7',status:'EVALUATED'}],
  invokeNative:async request=>{last=request;return {ack:true,status:'ACTIVATED'};}});
 const nodes=walk(root),select=nodes.find(x=>x.tag==='select'),button=nodes.find(x=>x.dataset.actionId==='training.activate');
 await button.listeners.click();assert.equal(last,undefined);
 select.value='native-job-7';await button.listeners.click();
 assert.equal(last.job_id,'native-job-7');assert.equal('path' in last,false);menu.destroy();
});

test('B06: forged JS MessageEvent cannot impersonate the WebView2 native host',async()=>{
 const f=fixture();
 let completed=false;
 const pending=f.client.request('chat.history',{}).then(v=>{completed=true;return v;});
 const req=f.sent[0];
 const ack={kind:'p02NativeResult',requestId:req.requestId,routeId:req.routeId,
   state:'COMPLETED',result:{verified:true}};
 // Attack A: dispatchEvent creates isTrusted=false even if source is copied.
 f.emit(ack,f.webview,false);
 f.emit(ack,null,true); // Attack B: foreign source, even with trusted flag.
 await Promise.resolve();await Promise.resolve();
 assert.equal(completed,false,'renderer ACK must remain pending');
 f.reply(ack); // Genuine WebView2 host source + trusted event.
 assert.equal((await pending).result.verified,true);
 f.client.destroy();
});

test('P01: timed-out native chats cannot starve two bounded STOP/cancel IPC slots',async()=>{
  let listener,seq=0,timerSeq=0;
  const timers=new Map(),sent=[];
  const webview={
    postMessage:message=>sent.push(message),
    addEventListener:(_type,fn)=>{listener=fn;},
    removeEventListener:()=>{listener=null;}
  };
  const client=createNativeMenuClient({
    webview,cryptoRef:{getRandomValues:bytes=>{bytes.fill(++seq);return bytes;}},
    setTimer:fn=>{const id=++timerSeq;timers.set(id,fn);return id;},
    clearTimer:id=>timers.delete(id),timeoutMs:10
  });
  let lateTerminal=0;
  for(let i=0;i<32;i++){
    const response=client.request('helion.chat',{text:'unresolved'},null,
      i===0?()=>{lateTerminal++;}:null);
    timers.get(timerSeq)(); // native timeout without terminal ACK
    await assert.rejects(response,/TIMEOUT/);
  }
  await assert.rejects(client.request('chat.history',{}),/REQUEST_LIMIT/);
  const stop=client.request('chat.stop',{});
  const cancel=client.request('models.cancel',{jobId:'existing-job-01'});
  assert.equal(sent.length,34,'no unbounded page flood beyond two controls');
  assert.deepEqual(sent.slice(-2).map(x=>x.routeId),['chat.stop','models.cancel']);
  await assert.rejects(client.request('chat.stop',{}),/REQUEST_LIMIT/);
  const nativeReply=(request,state)=>listener({
    source:webview,isTrusted:true,
    data:{kind:'p02NativeResult',requestId:request.requestId,
      routeId:request.routeId,state}
  });
  nativeReply(sent[32],'STOP_REQUESTED');
  nativeReply(sent[33],'STOP_REQUESTED');
  assert.equal((await stop).state,'STOP_REQUESTED');
  assert.equal((await cancel).state,'STOP_REQUESTED');
  nativeReply(sent[0],'COMPLETED'); // late terminal correlation is preserved
  assert.equal(lateTerminal,1);
  client.destroy();
});

// D06: transport COMPLETED and matching enabled are NOT proof of HKCU write.
test('D06 original SETTINGS owner requires explicit native write/read provenance',()=>{
 const envelope=(result,extra={})=>({routeId:'system.autostart',state:'COMPLETED',result,...extra});
 for(const enabled of [true,false]){
  assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly:false}),enabled),true);
  assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly:true}),enabled),false);
  assert.equal(nativeAutostartPersistenceAck(envelope({enabled}),enabled),false);
  for(const invalid of [null,'false',0,1])
   assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly:invalid}),enabled),false);
  assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly:true}),null),true);
  assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly:false}),null),false);
 }
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false}),false),false);
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false},{errorCode:'SID_MISMATCH'}),true),false);
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false,ownerResult:{status:'CONSENT_REQUIRED'}}),true),false);
 assert.equal(nativeAutostartPersistenceAck({...envelope({enabled:true,readOnly:false}),routeId:'chat.history'},true),false);
});

test('D06 SETTINGS WPF owner write requires a fresh native HKCU readback',async()=>{
 const envelope=(enabled,readOnly,extra={})=>({routeId:'system.autostart',state:'COMPLETED',result:{enabled,readOnly,...extra}});
 const calls=[],pending=[];
 const flow=createAutostartOwnerFlow((route,payload)=>{calls.push({route,payload});
   return new Promise((resolve,reject)=>pending.push({resolve,reject}));});
 const on=flow.request({enabled:true});
 await assert.rejects(flow.request({enabled:false}),/NOX_AUTOSTART_OWNER_IN_FLIGHT/);
 pending.shift().resolve(envelope(true,false));await Promise.resolve();
 assert.deepEqual(calls.map(v=>v.payload),[{enabled:true},{}]);
 await assert.rejects(flow.request({}),/NOX_AUTOSTART_OWNER_IN_FLIGHT/);
 pending.shift().resolve(envelope(true,true));
 assert.equal((await on).result.enabled,true);
 const off=flow.request({enabled:false});
 pending.shift().resolve(envelope(false,false));await Promise.resolve();
 pending.shift().resolve(envelope(true,true));
 await assert.rejects(off,/NOX_AUTOSTART_READBACK_HOLD/);
 const read=flow.request({});
 pending.shift().resolve(envelope(false,true));
 assert.equal((await read).result.readOnly,true);
 const denied=flow.request({enabled:true});
 pending.shift().resolve(envelope(true,false,{ownerConsent:false}));
 await assert.rejects(denied,/NOX_AUTOSTART_WRITE_UNVERIFIED/);
 const deniedRead=flow.request({enabled:true});
 pending.shift().resolve(envelope(true,false));await Promise.resolve();
 pending.shift().resolve(envelope(true,true,{permissionGranted:false}));
 await assert.rejects(deniedRead,/NOX_AUTOSTART_READBACK_HOLD/);
 const refusal=flow.request({enabled:false});
 pending.shift().reject(Error('NOX_AUTOSTART_NATIVE_OWNER_CONSENT_REQUIRED'));
 await assert.rejects(refusal,/NOX_AUTOSTART_NATIVE_OWNER_CONSENT_REQUIRED/);
 await assert.rejects(flow.request({enabled:'true'}),/NOX_AUTOSTART_BOOLEAN_REQUIRED/);
 assert.ok(Object.isFrozen(flow));
 assert.throws(()=>createAutostartOwnerFlow(null),/NATIVE_OWNER_REQUIRED/);
});

test('D06 SETTINGS UIA original-node / unique owner-route identity: not native consent PASS',()=>{
  const issued=new WeakSet();let nodes=[];
  const doc={querySelectorAll:sel=>nodes.filter(n=>'[id="'+n.id+'"]'===sel)};
  const mk=(id,key,value)=>({id,tagName:'BUTTON',isConnected:true,ownerDocument:doc,
    dataset:{nativeRoute:'system.autostart',nativeKey:key,nativeValue:value}});
  for(const [id,key,value] of [
    [AUTOSTART_UIA_IDS.read,'',''],[AUTOSTART_UIA_IDS.on,'enabled','true'],
    [AUTOSTART_UIA_IDS.off,'enabled','false']]){
    const original=mk(id,key,value);issued.add(original);nodes=[original];
    assert.equal(settingsAutostartOwnerAdmission(original,issued),true);
    const replacement=mk(id,key,value);
    assert.equal(settingsAutostartOwnerAdmission(replacement,issued),false);
    nodes=[original,replacement];
    assert.equal(settingsAutostartOwnerAdmission(original,issued),false);
    nodes=[original];original.dataset.nativeRoute='chat.commands';
    assert.equal(settingsAutostartOwnerAdmission(original,issued),false);
    original.dataset.nativeRoute='system.autostart';original.dataset.nativeValue='spoof';
    assert.equal(settingsAutostartOwnerAdmission(original,issued),false);
    original.dataset.nativeValue=value;original.isConnected=false;
    assert.equal(settingsAutostartOwnerAdmission(original,issued),false);
  }
  assert.equal(new Set(Object.values(AUTOSTART_UIA_IDS)).size,3);
});

test('D06 SETTINGS denies inner nonterminal or unreviewed owner status despite transport COMPLETED',()=>{
 const envelope=result=>({routeId:'system.autostart',state:'COMPLETED',result});
 for(const field of ['status','state']){
   for(const value of ['PENDING','QUEUED','RUNNING','IN_PROGRESS','COMPLETED','SUCCESS',null]){
     assert.equal(nativeAutostartPersistenceAck(
       envelope({enabled:true,readOnly:false,[field]:value}),true),false);
     assert.equal(nativeAutostartPersistenceAck(
       envelope({enabled:false,readOnly:true,[field]:value}),null),false);
   }
 }
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false}),true),true);
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:false,readOnly:false}),false),true);
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:false,readOnly:true}),null),true);
});

test('D06 SETTINGS refuses explicit native owner consent and permission denial on read/write',()=>{
 const envelope=result=>({routeId:'system.autostart',state:'COMPLETED',result});
 for(const key of ['consented','ownerConsent','nativeConsent','permissionGranted']){
   for(const invalid of [false,null,0,'true']){
     for(const [enabled,readOnly,requested] of [[true,false,true],[false,true,null]]){
       assert.equal(nativeAutostartPersistenceAck(envelope({enabled,readOnly,[key]:invalid}),requested),false,key+':'+String(invalid));
     }
   }
   assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false,[key]:true}),true),true);
   assert.equal(nativeAutostartPersistenceAck(envelope({enabled:false,readOnly:true,[key]:true}),null),true);
   assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false,ownerResult:{[key]:false}}),true),false);
 }
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:true,readOnly:false}),true),true);
 assert.equal(nativeAutostartPersistenceAck(envelope({enabled:false,readOnly:true}),null),true);
});
