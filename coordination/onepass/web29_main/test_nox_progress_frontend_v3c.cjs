const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const content=fs.readFileSync(__dirname+'/site/pc/progress/nox-progress.js','utf8');
const ctx={URL,Date,Number,Intl,Set,console};ctx.globalThis=ctx;
vm.runInNewContext(content,ctx,{filename:'nox-progress.js'});
const {normalize,filterEvents,safeURL,color,eligibleHourCards,nativeFresh}=ctx.NoxEvolution;
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
console.log('PASS source regression: HOLD hour visible, open hour excluded, stale live telemetry suppressed');
