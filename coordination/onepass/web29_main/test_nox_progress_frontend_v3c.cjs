const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const content=fs.readFileSync(__dirname+'/site/pc/progress/nox-progress.js','utf8');
const ctx={URL,Date,Number,Intl,Set,console};ctx.globalThis=ctx;
vm.runInNewContext(content,ctx,{filename:'nox-progress.js'});
const {normalize,filterEvents,safeURL,color,eligibleHourCards,nativeFresh,nativeGroupValue,expireNative}=ctx.NoxEvolution;
const A='a'.repeat(64);
const hours=[{id:'hour-20261116T01',start:'2026-11-16T01:00:00Z',end:'2026-11-16T02:00:00Z',closed:true,
   readback_verified:false,readback_sha256:A,readback_state:'HOLD_PERSISTED_HOUR_MISSING',groups:{}}];
const data={schema:'NOX_EVOLUTION_V1',mode:'native',events:[],hours,generated_at:'2026-11-16T02:30:00Z',
    hourly_readback:{expected_closed:1,persisted_verified:0,complete:false},groups:{},metrics:{}};
const a=normalize(data);assert.equal(a.hours[0].closed,false);assert.equal(a.hourlyReadback,'0/1');
assert.equal(eligibleHourCards(a).length,1); // expired HOLD displayed rather than hidden
assert.equal(eligibleHourCards(a)[0].closed,false);
assert.equal(eligibleHourCards(normalize({...data,generated_at:'2026-11-16T01:30:00Z'})).length,0);
hours[0].readback_verified=true;hours[0].readback_state='S03_PERSISTED_HOUR_READBACK';
const b=normalize(data);assert.equal(b.hours[0].closed,true);
hours[0].readback_sha256='wrong';assert.equal(normalize(data).hours[0].closed,false);
const source={...data,mode:'source_snapshot',hours:[{...hours[0],readback_verified:false,closed:true}]};
const c=normalize(source);assert.equal(c.hours[0].closed,true);assert.equal(c.hourlyReadback,'HOLD');
const event={id:'e1',kind:'weights',state:'verified',evidence:'source',at:'2026-11-16T01:23:00Z',title:'Source only',tags:['GPU'],proof:{receipt_sha256:A}};
const d=normalize({...data,events:[event]});assert.equal(d.events[0].state,'source');
assert.equal(filterEvents(d.events,{status:'yellow'}).length,1);
assert.equal(color('failed'),'red');assert.equal(safeURL('javascript:alert(1)'),null);
const liveStamp=new Date().toISOString(),fresh=normalize({...data,generated_at:liveStamp,metrics:{ttft_ms:300,gpu0_percent:40}});
assert.equal(fresh.liveFresh,true);assert.equal(fresh.metrics.ttft_ms,300);
const stale=normalize({...data,generated_at:'2020-01-01T00:00:00Z',metrics:{ttft_ms:300}});
assert.equal(stale.liveFresh,false);assert.equal(stale.metrics.ttft_ms,null);
assert.equal(nativeFresh({...data,generated_at:liveStamp},Date.parse(liveStamp)+121000),false);

const weightProof={receipt_sha256:A,step_before:3,step_after:6,successful_optimizer_updates:2,tensor_before:'b'.repeat(64),tensor_after:'c'.repeat(64),checkpoint_sha256:'d'.repeat(64)};
const verifiedWeights=normalize({...data,generated_at:liveStamp,metrics:{ttft_ms:300,gpu0_percent:40},
 events:[{id:'native-weight',kind:'weights',state:'verified',evidence:'native',at:liveStamp,title:'Checkpoint',proof:weightProof}],
 groups:{weights:{value:2,complete:false}}});
assert.equal(nativeGroupValue(verifiedWeights,'weights'),2);
const skippedOnly=normalize({...data,generated_at:liveStamp,events:[{...verifiedWeights.events[0],proof:{...weightProof,successful_optimizer_updates:0}}],groups:{weights:{value:3,complete:false}}});
assert.equal(skippedOnly.events[0].state,'unknown');
assert.equal(nativeGroupValue(skippedOnly,'weights'),null); // fresh evidenced value
assert.equal(nativeGroupValue(normalize({...data,generated_at:'2020-01-01T00:00:00Z',events:verifiedWeights.events,groups:verifiedWeights.groups}),'weights'),null); // stale is unknown
assert.equal(nativeGroupValue({...verifiedWeights,events:[]},'weights'),null); // unauthenticated aggregate alone
assert.equal(nativeGroupValue({...verifiedWeights,groups:{weights:{value:0,complete:true}},events:[]},'weights'),0); // legitimate zero
const impossibleSkip=normalize({...data,generated_at:liveStamp,
 events:[{...verifiedWeights.events[0],proof:{...weightProof,skipped_optimizer_updates:2}}],
 groups:{weights:{value:2,complete:false}}});
assert.equal(impossibleSkip.events[0].state,'unknown');
assert.equal(nativeGroupValue(impossibleSkip,'weights'),null);
const validSkip=normalize({...data,generated_at:liveStamp,
 events:[{...verifiedWeights.events[0],proof:{...weightProof,skipped_optimizer_updates:1}}],
 groups:{weights:{value:2,complete:false}}});
assert.equal(nativeGroupValue(validSkip,'weights'),2);
const disconnected=expireNative(verifiedWeights);
assert.equal(disconnected.liveFresh,false);
assert.equal(disconnected.metrics.ttft_ms,null);
assert.equal(disconnected.metrics.gpu0_percent,null);
assert.equal(nativeGroupValue(disconnected,'weights'),null);
assert.equal(verifiedWeights.metrics.ttft_ms,300); // historical object never modified
assert.match(content,/if\(e\.status===401\|\|e\.status===403\).*detailBody.*replaceChildren/); // revoke owner details

const forgedAggregate=normalize({...data,generated_at:liveStamp,events:verifiedWeights.events,
 groups:{weights:{value:25,complete:false}}});
assert.equal(nativeGroupValue(forgedAggregate,'weights'),null); // one receipt proves 2, never 25
const forgedComplete=normalize({...data,generated_at:liveStamp,events:verifiedWeights.events,
 groups:{weights:{value:25,complete:true}}});
assert.equal(nativeGroupValue(forgedComplete,'weights'),null); // "complete" cannot override proof
const forgedFraction=normalize({...data,generated_at:liveStamp,events:verifiedWeights.events,
 groups:{weights:{value:2.5,complete:true}}});
assert.equal(nativeGroupValue(forgedFraction,'weights'),null); // count must be integer
const unprovenComplete=normalize({...data,generated_at:liveStamp,events:[],
 groups:{weights:{value:8,complete:true}}});
assert.equal(nativeGroupValue(unprovenComplete,'weights'),null); // no native updates at all
const zeroComplete=normalize({...data,generated_at:liveStamp,events:[],
 groups:{weights:{value:0,complete:true}}});
assert.equal(nativeGroupValue(zeroComplete,'weights'),0); // legitimate complete zero
const zeroIncomplete=normalize({...data,generated_at:liveStamp,events:[],
 groups:{weights:{value:0,complete:false}}});
assert.equal(nativeGroupValue(zeroIncomplete,'weights'),null);
const truncatedAggregate=normalize({...data,generated_at:liveStamp,events:verifiedWeights.events,truncated:true,
 groups:{weights:{value:2,complete:true}}});
assert.equal(nativeGroupValue(truncatedAggregate,'weights'),null); // incomplete source view
const verifiedKnowledge={...verifiedWeights.events[0],id:'native-knowledge',kind:'knowledge',
 proof:{receipt_sha256:A,records_added:3,s03_readback_sha256:'d'.repeat(64)}};
const knowledgeMismatch=normalize({...data,generated_at:liveStamp,events:[verifiedKnowledge],
 groups:{knowledge:{value:4,complete:false}}});
assert.equal(nativeGroupValue(knowledgeMismatch,'knowledge'),null);
const knowledgeMatched=normalize({...data,generated_at:liveStamp,events:[verifiedKnowledge],
 groups:{knowledge:{value:3,complete:false}}});
assert.equal(nativeGroupValue(knowledgeMatched,'knowledge'),3);

const clipped=normalize({...data,generated_at:liveStamp,events:verifiedWeights.events,truncated:true,
 groups:{weights:{value:2,complete:true}}});
assert.equal(clipped.truncated,true);
assert.equal(nativeGroupValue(clipped,'weights'),null); // even a matching partial aggregate is UNKNOWN
assert.match(content,/выборка неполная/); // explicit user-facing notice
assert.match(content,/Событий больше 5000/);

console.log('PASS source regressions: bounded 5000-event window, S03 HOLD, aggregate truthfulness and owner isolation');


// NOX_V14_DELAYED_CHAT_DOCK: original chat can mount after DOMContentLoaded.
const dockCode=fs.readFileSync(__dirname+'/site/nox-evolution-dock.js','utf8');
function dockFixture(late=false,foreignOrigin=false){
 const elements=[],observers=[],listeners={},scheduled=[];
 let composer=null;
 function element(tag){
   const node={tag,id:null,hidden:false,dataset:{},style:{},children:[],attributes:{},
     classList:{add(){}},append(...items){this.children.push(...items);},
     setAttribute(k,v){this.attributes[k]=v;},addEventListener(){},querySelector(){return null;},
     focus(){},remove(){},getBoundingClientRect(){return {top:50,bottom:100}}};
   elements.push(node);return node;
 }
 const region=element('main');
 function attachComposer(){
   composer=element('form');composer.id='chatForm';composer.parentElement=region;
   composer.insertAdjacentElement=()=>{};
 }
 if(!late)attachComposer();
 const doc={
   currentScript:{src:'https://nox.test/nox-web-v29/nox-evolution-dock.js'},
   head:{append(){}},body:{dataset:{page:'chat'}},readyState:'complete',
   activeElement:{focus(){}},createElement:element,
   getElementById(id){return elements.find(node=>node.id===id)||null;},
   querySelector(selector){return selector.startsWith('.v24-main')?region:null;}
 };
 class ScopedObserver{
   constructor(callback){this.callback=callback;this.disconnected=false;observers.push(this);}
   observe(){}disconnect(){this.disconnected=true;}
 }
 const win={addEventListener(type,callback){
   (listeners[type]??=[]).push(callback);
 }};
 vm.runInNewContext(dockCode,{
   window:win,document:doc,URL,MutationObserver:ScopedObserver,
   location:{origin:foreignOrigin?'https://foreign.test':'https://nox.test'},
   setTimeout(callback,ms){scheduled.push({callback,ms});}
 },{filename:'nox-evolution-dock.js'});
 function count(){return elements.filter(node=>node.id==='nox-evolution-dock').length;}
 function mutation(){for(const observer of observers)if(!observer.disconnected)observer.callback();}
 return {win,doc,observers,listeners,scheduled,count,mutation,attachComposer};
}
const earlyDock=dockFixture();
assert.equal(earlyDock.count(),1,'synchronous original composer must remain supported');
assert.equal(earlyDock.observers.length,0,'no background observer after early attach');
const lateDock=dockFixture(true);
assert.equal(lateDock.count(),0,'must not create a second chat UI while composer absent');
assert.equal(lateDock.observers.length,1,'exactly one bounded observer while pending');
lateDock.attachComposer();lateDock.mutation();
assert.equal(lateDock.count(),1,'original progress dock attaches to late composer');
assert.equal(lateDock.observers[0].disconnected,true,'observer must stop after attach');
lateDock.mutation();
assert.equal(lateDock.count(),1,'no duplicated dock on later DOM mutations');
assert.equal(lateDock.win.NoxEvolutionDock.diagnostics().modelCalls,0,'no model call');
assert.equal(lateDock.scheduled.length,1);
assert.equal(lateDock.scheduled[0].ms,12000,'bounded 12-second observation');
const timeoutDock=dockFixture(true);
timeoutDock.scheduled[0].callback();
assert.equal(timeoutDock.observers[0].disconnected,true,'no endless observer');
timeoutDock.attachComposer();timeoutDock.mutation();
assert.equal(timeoutDock.count(),0,'timeout does not silently create a new UI');
const leaveDock=dockFixture(true);
for(const callback of leaveDock.listeners.pagehide||[])callback();
assert.equal(leaveDock.observers[0].disconnected,true,'navigation releases observer');
const wrongOriginDock=dockFixture(true,true);
assert.equal(wrongOriginDock.observers.length,0,'cross-origin asset is never bound');
assert.equal(wrongOriginDock.count(),0);
console.log('PASS NOX_V14_DELAYED_CHAT_DOCK: late/early composer, idempotence, bounded lifecycle, origin');
