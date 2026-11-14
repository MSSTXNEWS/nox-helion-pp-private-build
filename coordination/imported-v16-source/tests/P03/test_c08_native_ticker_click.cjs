'use strict';
// Source-only regression for the existing P03 WebView2 UI. No invented native ACK.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.resolve(__dirname,
  '../../Packages/P03/Source/P03.ModelCenter.Wow/ui.js'), 'utf8');

function mount() {
  let now = Date.parse('2026-11-01T20:00:00.000Z');
  const sent = [];
  let focused = 0;
  const RealDate = Date;
  class ClockDate extends RealDate {
    constructor(...v) { super(...(v.length ? v : [now])); }
    static now() { return now; }
    static parse(v) { return RealDate.parse(v); }
  }
  function node(tag='div') {
    return {tagName:tag.toUpperCase(), children:[], handlers:{}, attrs:{}, dataset:{},
      textContent:'', value:'', checked:false, disabled:false, hidden:false,
      style:{setProperty(){}}, classList:{add(){},remove(){},toggle(){}},
      append(...v){this.children.push(...v);}, replaceChildren(...v){this.children=v;},
      setAttribute(k,v){this.attrs[k]=v;}, removeAttribute(k){delete this.attrs[k];},
      focus(){focused++;}, addEventListener(t,cb){this.handlers[t]=cb;}};
  }
  const elements = new Map();
  const document = {getElementById(id){if(!elements.has(id)) elements.set(id,node());return elements.get(id);},
    createElement:node, querySelector(sel){return sel==='.topbar'?this.getElementById('_topbar'):null;},
    querySelectorAll(){return [];}, addEventListener(){},activeElement:{tagName:'BODY'}};
  const webview = {postMessage(message){sent.push(message);},addEventListener(){}};
  const app = new Function('document','window','URL','Date','setInterval','setTimeout',
    'clearTimeout', source+'\nreturn {processMessage,refreshNativeEventSignal,state};')(
    document,{chrome:{webview}},URL,ClockDate,()=>1,()=>1,()=>{});
  const jobId = '11111111-1111-4111-8111-111111111111';
  const signal = () => document.getElementById('eventSignal').textContent;
  const post = (id,atUtc,phase='started') => app.processMessage({type:'p03.event.v1',
    event:{jobId:id,modelTag:'llama3',phase,atUtc,status:'Starting'}});
  return {app,document,jobId,sent,signal,post,focused:()=>focused,
    clock:()=>now, advance(ms){now+=ms;}, utc:()=>new RealDate(now).toISOString(),
    future(ms){return new RealDate(now+ms).toISOString()}};
}

test('future native atUtc never turns LIVE as the wall clock advances', () => {
  const v=mount();
  v.post(v.jobId,v.future(10000));
  assert.equal(v.signal(),'● —');
  v.advance(6000);v.app.refreshNativeEventSignal();
  assert.equal(v.signal(),'● —','no native event means no LIVE transition');
});

test('click status is bound to current native job, never a command or external route', () => {
  const v=mount();
  v.app.state.activeJob={jobId:v.jobId,modelTag:'llama3',modelId:'llama3',state:'Queued'};
  v.post(v.jobId,v.utc(),'progress');
  assert.equal(v.signal(),'● LIVE');
  const row=v.document.getElementById('eventFeed').children[0];
  const button=row.children.find(x=>x.tagName==='BUTTON');
  assert.ok(button,'native row for current durable queue job must be clickable');
  assert.equal(button.type,'button');
  const sentBefore=v.sent.length;button.handlers.click();
  assert.equal(v.focused(),1);
  assert.equal(v.document.getElementById('jobState').attrs.tabindex,'-1');
  assert.equal(v.sent.length,sentBefore,'navigation must not forge native ACK/command');
  v.app.state.activeJob={jobId:'22222222-2222-4222-8222-222222222222',
    modelTag:'llama3',state:'Queued'};
  button.handlers.click();
  assert.equal(v.focused(),1,'stale event cannot navigate after job changes');
  v.post(v.jobId,v.utc(),'progress');
  assert.ok(v.document.getElementById('eventFeed').children[0].children
    .every(x=>x.tagName!=='BUTTON'),'unrelated history is text, not a misleading link');
  v.advance(31000);v.app.refreshNativeEventSignal();
  assert.equal(v.signal(),'● STALE');
});

// C08 chronological native gate: historic/UNKNOWN frame remains advisory.
test('stale/missing timestamps never advance durable P03 queue; latest native wins', () => {
  const stale=mount();stale.app.state.activeJob={jobId:stale.jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'};
  stale.post(stale.jobId,new Date(stale.clock()-3600000).toISOString(),'completed');
  assert.equal(stale.app.state.activeJob.state,'Queued');
  const unknown=mount();unknown.app.state.activeJob={jobId:unknown.jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'};
  unknown.post(unknown.jobId,undefined,'progress');
  assert.equal(unknown.app.state.activeJob.state,'Queued');
  const ordered=mount();ordered.app.state.activeJob={jobId:ordered.jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'};
  ordered.post(ordered.jobId,new Date(ordered.clock()-1000).toISOString(),'progress');
  assert.equal(ordered.app.state.activeJob.state,'Running');
  ordered.post(ordered.jobId,new Date(ordered.clock()-2000).toISOString(),'completed');
  assert.equal(ordered.app.state.activeJob.state,'Running');
  ordered.post(ordered.jobId,new Date(ordered.clock()-500).toISOString(),'completed');
  assert.equal(ordered.app.state.activeJob.state,'Completed');
});

test('stale, missing and reordered terminal notices cannot advertise Installed', () => {
  const present=v=>v.document.getElementById('eventFeed').children[0].children
    .map(x=>x.textContent).join(' ');
  for(const atUtc of [new Date(Date.parse('2026-11-01T19:00:00.000Z')).toISOString(),undefined]) {
    const v=mount();
    v.app.state.activeJob={jobId:v.jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'};
    v.app.processMessage({type:'p03.event.v1',event:{jobId:v.jobId,modelTag:'llama3',
      phase:'completed',status:'Installed',atUtc}});
    assert.equal(v.app.state.activeJob.state,'Queued','durable queue must remain Queued');
    assert.doesNotMatch(present(v),/Installed|completed/,'untrusted terminal notice must not claim install');
    assert.match(present(v),atUtc ? /STALE/ : /UNKNOWN/);
  }
  const v=mount();v.app.state.activeJob={jobId:v.jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'};
  v.post(v.jobId,new Date(v.clock()-1000).toISOString(),'progress');
  assert.equal(v.app.state.activeJob.state,'Running');
  v.app.processMessage({type:'p03.event.v1',event:{jobId:v.jobId,modelTag:'llama3',
    phase:'completed',status:'Installed',atUtc:new Date(v.clock()-2000).toISOString()}});
  assert.equal(v.app.state.activeJob.state,'Running');
  assert.doesNotMatch(present(v),/Installed|completed/,'reordered event must not spoof completion in feed');
  assert.match(present(v),/STALE/);
});

test('unmatched native terminal notices never imply Installed or LIVE', () => {
  const primary='11111111-1111-4111-8111-111111111111';
  const foreign='22222222-2222-4222-8222-222222222222';
  for (const variant of [
    {label:'foreign current',jobId:foreign,tag:'llama3',at:'current',status:/STALE/},
    {label:'foreign missing',jobId:foreign,tag:'llama3',at:'missing',status:/UNKNOWN/},
    {label:'foreign future',jobId:foreign,tag:'llama3',at:'future',status:/UNKNOWN/},
    {label:'foreign old',jobId:foreign,tag:'llama3',at:'old',status:/STALE/},
    {label:'same job wrong tag',jobId:primary,tag:'mistral',at:'current',status:/STALE/}
  ]) {
    const v=mount();
    v.app.state.activeJob={jobId:primary,modelId:'llama3',modelTag:'llama3',state:'Queued'};
    const atUtc=variant.at==='current' ? v.utc() :
      variant.at==='future' ? v.future(60000) :
      variant.at==='old' ? new Date(v.clock()-3600000).toISOString() : undefined;
    v.app.processMessage({type:'p03.event.v1',event:{
      jobId:variant.jobId,modelTag:variant.tag,phase:'completed',status:'Installed',atUtc}});
    const row=v.document.getElementById('eventFeed').children[0];
    const visible=row.children.map(x=>x.textContent).join(' ');
    assert.doesNotMatch(visible,/Installed|completed/,variant.label+' cannot claim terminal result');
    assert.match(visible,variant.status,variant.label+' must be advisory');
    assert.equal(v.app.state.activeJob.state,'Queued');
    assert.equal(v.signal(),'● —',variant.label+' cannot mark native queue LIVE');
  }
});

test('a new durable job or empty queue revokes LIVE until its own fresh native event', () => {
  const v=mount(), other='22222222-2222-4222-8222-222222222222';
  const snapshot=jobId=>v.app.processMessage({type:'p03.snapshot.v1',
    models:[{id:'llama3',name:'Llama 3'}],
    activeJob:jobId?{jobId,modelId:'llama3',modelTag:'llama3',state:'Queued'}:null});
  snapshot(v.jobId);
  v.post(v.jobId,v.utc(),'progress');
  assert.equal(v.signal(),'● LIVE');
  snapshot(v.jobId);
  assert.equal(v.signal(),'● LIVE','same durable job keeps its real fresh event');
  snapshot(other);
  assert.equal(v.signal(),'● —','old job telemetry is not live for another job');
  v.post(v.jobId,v.utc(),'completed');
  assert.equal(v.signal(),'● —','foreign event cannot revive stale LIVE');
  v.post(other,v.utc(),'progress');
  assert.equal(v.signal(),'● LIVE','new native frame enables LIVE for its matching job');
  snapshot(null);
  assert.equal(v.signal(),'● —','empty durable queue cannot show prior job LIVE');
});

test('nonterminal native status and progress never claim Installed without completed event', () => {
  const v=mount(), jobId=v.jobId;
  v.app.processMessage({type:'p03.snapshot.v1',models:[{id:'llama3',name:'Llama 3'}],
    activeJob:{jobId,modelId:'llama3',modelTag:'llama3',state:'Queued',status:'Installed'}});
  assert.equal(v.app.state.activeJob.status,'Обновление');
  assert.doesNotMatch(v.document.getElementById('jobPhase').textContent,/Installed/);
  v.app.processMessage({type:'p03.event.v1',event:{jobId,modelTag:'llama3',
    phase:'progress',status:'Installed',atUtc:v.utc()}});
  assert.equal(v.app.state.activeJob.state,'Running');
  assert.equal(v.app.state.activeJob.status,'Обновление');
  const text=v.document.getElementById('eventFeed').children[0].children
    .map(x=>x.textContent).join(' ');
  assert.doesNotMatch(text,/Installed/);
  assert.doesNotMatch(v.document.getElementById('jobPhase').textContent,/Installed/);
  v.advance(1000);
  v.app.processMessage({type:'p03.event.v1',event:{jobId,modelTag:'llama3',
    phase:'completed',status:'Installed',atUtc:v.utc()}});
  assert.equal(v.app.state.activeJob.state,'Completed');
  assert.equal(v.app.state.activeJob.status,'Installed','only matching native completion can show Installed');
});
