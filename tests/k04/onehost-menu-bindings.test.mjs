import test from 'node:test';
import assert from 'node:assert/strict';
import {createNativeMenuClient,mountOneHostMenu,canonicalChatContext} from '../../ui/onehost-menu-bindings.mjs';
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
