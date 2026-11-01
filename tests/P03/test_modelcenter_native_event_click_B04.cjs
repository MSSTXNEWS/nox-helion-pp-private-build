'use strict';
// EV-B04: real native lifecycle event -> visible queue status -> direct user click -> exact ACK.
// SOURCE-ONLY Node regression. No WebView2, Ollama, runtime weights, telemetry, or installed EXE.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const src = fs.readFileSync(path.resolve(__dirname,'../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js'),'utf8');
function el(tag='div'){
  return {tagName:tag.toUpperCase(),children:[],handlers:{},textContent:'',value:'',
    checked:false,disabled:false,hidden:false,dataset:{},style:{setProperty(){}},
    classList:{add(){},remove(){},toggle(){}},append(...v){this.children.push(...v)},
    replaceChildren(...v){this.children=v},setAttribute(){},removeAttribute(){},
    addEventListener(type,fn){this.handlers[type]=fn},focus(){}};
}
const elements=new Map(), sent=[];let listener;
const doc={getElementById(id){if(!elements.has(id))elements.set(id,el());return elements.get(id)},
  createElement:el,querySelector:s=>s==='.topbar'?doc.getElementById('_topbar'):null,
  querySelectorAll:()=>[],addEventListener(){},activeElement:{tagName:'BODY'}};
const win={chrome:{webview:{postMessage:m=>sent.push(m),
  addEventListener(type,fn){if(type==='message')listener=fn}}}};
const app=new Function('document','window','URL','setTimeout','clearTimeout','setInterval',
  src+'\nreturn {state,processMessage,sendAction};')(doc,win,URL,()=>1,()=>{},()=>0);
const field=id=>doc.getElementById(id),post=data=>listener({data});
const id='11111111-1111-4111-8111-111111111111',tag='qwen3:0.6b';
const queued={jobId:id,modelId:'qwen3',modelTag:tag,state:'Queued',completedBytes:0,totalBytes:100};
const models=JSON.parse(JSON.stringify(app.state.models));
const snapshot=job=>({type:'p03.snapshot.v1',models,activeJob:job,
  capabilities:{stop:true,retry:true,pull:false,importGguf:false,diagnose:false}});
const event=(phase,atUtc=new Date().toISOString())=>({type:'p03.event.v1',event:{
  jobId:id,modelTag:tag,phase,atUtc,status:'Starting'}});
assert.equal(sent.shift()?.type,'p03.ready.v1','listener must precede ready notification');
post(snapshot(queued));
assert.equal(field('jobState').textContent,'Queued');
assert.equal(field('eventSignal').textContent,'● —','snapshot alone cannot make LIVE');
post(event('started'));
assert.equal(app.state.activeJob.state,'Running','native started evidence must transition Queued');
assert.equal(field('jobState').textContent,'Running','hero must display actual lifecycle state');
assert.equal(field('eventSignal').textContent,'● LIVE','timestamped native event drives LIVE');
assert.equal(field('stopBtn').disabled,false,'native Running remains stoppable');
field('stopBtn').handlers.click();
const command=sent.pop();
assert.equal(command?.action,'stop');assert.equal(command.jobId,id);
assert.equal(command.type,'p03.command.v1');
assert.equal(field('stopBtn').disabled,true,'click pending prevents duplicate native STOP');
post({type:'p03.command.ack.v1',action:'stop',commandId:'wrong',accepted:true});
assert.equal(app.state.pending.has('stop'),true,'wrong ACK cannot unlock STOP');
post({type:'p03.command.ack.v1',action:'stop',commandId:command.commandId,
  accepted:true,jobId:id,modelTag:tag});
assert.match(field('toast').textContent,/требует receipt/,'ACK is not installation');
post(event('cancelled'));
assert.equal(field('jobState').textContent,'Cancelled','only native event confirms cancellation');
assert.equal(field('stopBtn').disabled,true);
assert.equal(field('retryBtn').disabled,false,'native terminal state enables authorized retry');
post(event('progress'));
assert.equal(field('jobState').textContent,'Cancelled','late event cannot revive STOPped job');
const other='22222222-2222-4222-8222-222222222222';
post(snapshot({...queued,jobId:other}));
post({type:'p03.event.v1',event:{jobId:other,modelTag:tag,phase:'progress',
  atUtc:new Date().toISOString(),status:'Pulling layer',completedBytes:10,totalBytes:100}});
assert.equal(field('jobState').textContent,'Running','real native progress advances Queued');
assert.notEqual(field('jobState').textContent,'Completed','no synthetic installation claim');
console.log('EV-B04_P03_NATIVE_EVENT_CLICK_REGRESSION: 19 assertions PASS (source only)');
