import assert from 'node:assert/strict';
import {projectSpaceView,projectReadiness,projectFeeds,projectHardware,projectCorePersona,
  projectCanonicalEvents,LOCKED_BASELINE,EVENT_SCHEMA} from './E05SpaceReadOnlyProjection.mjs';
const NOW=Date.parse('2026-10-28T03:45:00Z');
const H='a'.repeat(64),RUN='NOX-E05-TURBO10-R03';
const bar=i=>({executor:i,stage:'CRITERIA_VERIFIED',percent:i*10,total_tasks:10,
  task_ledger:Array.from({length:10},(_,j)=>({task_id:`E0${i}-TASK-${j+1}`,weight:10,
    status:j<i?'COMPONENT_VERIFIED':'HOLD',...(j<i?{receipt_sha256:H}:{})})),
  manifest_sha256:H,receipt_sha256:H});
const readiness={run_id:RUN,source_commit:LOCKED_BASELINE,at_utc:'2026-10-28T03:44:58Z',
  native_attestation:'E06_OWNER_VERIFIED',bars:[1,2,3,4,5].map(bar).concat([
    {executor:6,stage:'HOLD',percent:null},{executor:7,stage:'NOT_RUN',percent:null}]),overall:28};
const terminalEvent=(type,state)=>({schema:EVENT_SCHEMA,run_id:RUN,event_id:'evt-001',
  event_type:type,task_id:'G1-05-09',package_id:'P05',action_id:'stop',
  timestamp_utc:'2026-10-28T03:44:58Z',state,source:'P05.Host',message:'Recorded terminal',evidence_verified:true});
const feed={id:'weather',provider:'approved',license_status:'APPROVED',license_receipt_sha256:H,
  status:'LIVE',source_at_utc:'2026-10-28T03:44:00Z',fetched_at_utc:'2026-10-28T03:44:50Z',
  ttl_ms:60000,parsed_by_owner:true,value:14};
let n=0;const test=(description,fn)=>{fn();n++;console.log('PASS',n,description)};
test('five sealed lanes use 20/25/20/25/10, not simple mean',()=>{
  const r=projectReadiness(readiness,RUN,NOW); assert.equal(r.overall,28);assert.equal(r.bars.length,7);
});
test('E06 and E07 remain independent non-numeric gates',()=>{
  const r=projectReadiness(readiness,RUN,NOW);assert.equal(r.bars[5].percent,null);assert.equal(r.bars[6].percent,null);
});
test('unverified raw percent fails closed',()=>assert.equal(projectReadiness({overall:100},RUN,NOW).overall,null));
test('foreign run is rejected',()=>assert.equal(projectReadiness(readiness,'DIFFERENT',NOW).overall,null));
test('old source lock cannot promote progress',()=>assert.equal(projectReadiness({...readiness,source_commit:'f'.repeat(40)},RUN,NOW).overall,null));
test('tampered weighted total yields N/D',()=>assert.equal(projectReadiness({...readiness,overall:100},RUN,NOW).overall,null));
test('stale attestation yields N/D',()=>assert.equal(projectReadiness({...readiness,at_utc:'2026-10-28T03:40:00Z'},RUN,NOW).overall,null));
test('GPU missing provider returns N/D, never zero',()=>assert.equal(projectHardware([],NOW)['gpu.percent'].value,null));
test('VRAM contradictory pairs are invalid',()=>{
  const at='2026-10-28T03:44:58Z';const s=(key,value,source='nvml')=>({key,value,source,unit:'bytes',status:'LIVE',observed_at_utc:at});
  const h=projectHardware([s('gpu.vram.used_bytes',2048),s('gpu.vram.total_bytes',1024)],NOW);
  assert.equal(h['gpu.vram.total_bytes'].value,null);assert.equal(h['gpu.vram.used_bytes'].stage,'INCONSISTENT_VRAM');
});
test('eight approved CoreIDs and five Persona IDs only',()=>{
  const c={owner_manifest_sha256:H,approved_core_ids:Array.from({length:8},(_,i)=>'core-'+i),
    approved_persona_ids:Array.from({length:5},(_,i)=>'person-'+i),
    core_ids:Array.from({length:8},(_,i)=>({id:'core-'+i,percent:20,status:'VERIFIED',receipt_sha256:H,measured_at_utc:'2026-10-28T03:44:00Z'})),
    personas:Array.from({length:5},(_,i)=>({id:'person-'+i,status:'AVAILABLE',observed_at_utc:'2026-10-28T03:44:00Z'})),
    aggregation:{method:'WEIGHTED_V1',receipt_sha256:H,
      weights:Array.from({length:8},(_,i)=>({id:'core-'+i,weight:12.5}))}};
  assert.equal(projectCorePersona(c,NOW).helion,20);assert.equal(projectCorePersona({...c,core_ids:[...c.core_ids.slice(0,7),c.core_ids[0]]},NOW).helion,null);
});
test('approved dated weather values may display',()=>assert.equal(projectFeeds([feed],NOW)[0].value,14));
test('offline cache is never marked LIVE',()=>{
  const f=projectFeeds([{...feed,status:'OFFLINE_CACHE'}],NOW)[0];assert.equal(f.stage,'STALE_CACHE');assert.equal(f.value,null);
});
test('unlicensed financial feeds cannot display',()=>{
  const f=projectFeeds([{...feed,id:'bitcoin',license_status:'UNKNOWN'}],NOW)[0];assert.equal(f.stage,'DISABLED');assert.equal(f.value,null);
});
test('future source time is N/D',()=>assert.equal(projectFeeds([{...feed,source_at_utc:'2026-10-29T03:44:00Z'}],NOW)[0].stage,'N_D'));
test('ECB date is labeled historical observation, not market tick',()=>{
  const f=projectFeeds([{...feed,id:'eur-usd',observation_date:'2026-10-27'}],NOW)[0];assert.equal(f.observedKind,'ECB_OBSERVATION_DATE');
});
test('same-run STOP event is recognized without progress',()=>{
  const e=terminalEvent('model.stopped','STOPPED');
  assert.deepEqual(projectCanonicalEvents([e],RUN,NOW),{state:'STOPPED',errors:0});
});
test('foreign STOP cannot stop another RunID',()=>{
  const e={...terminalEvent('model.stopped','STOPPED'),run_id:'OTHER'};
  assert.equal(projectCanonicalEvents([e],RUN,NOW).state,'N_D');
});
test('Drive readback never claimed without same-run proof',()=>{
  const v=projectSpaceView({run_id:RUN,drive:{run_id:'OTHER',status:'READBACK_PASS',receipt_sha256:H}},NOW);
  assert.equal(v.driveReadback,'HOLD');assert.equal(v.readiness.overall,null);
});
test('STOP requires full canonical event schema (not a UI hint)',()=>{
  const bad={schema:EVENT_SCHEMA,run_id:RUN,event_type:'model.stopped',timestamp_utc:'2026-10-28T03:44:58Z'};
  assert.equal(projectCanonicalEvents([bad],RUN,NOW).state,'HOLD_MALFORMED_TERMINAL');
});
test('STOP with wrong canonical state is rejected',()=>{
  assert.equal(projectCanonicalEvents([{...terminalEvent('model.stopped','STOPPED'),state:'RUNNING'}],RUN,NOW).state,'HOLD_MALFORMED_TERMINAL');
});
test('failed task with wrong state is rejected',()=>{
  assert.equal(projectCanonicalEvents([terminalEvent('task.failed','COMPLETED')],RUN,NOW).errors,null);
});
test('duplicate event_id does not double-count failures',()=>{
  const e=terminalEvent('task.failed','ERROR');
  assert.deepEqual(projectCanonicalEvents([e,e],RUN,NOW),{state:'ERROR',errors:1});
});
test('out of order event arrival cannot overwrite newer ERROR with older STOP',()=>{
  const old=terminalEvent('model.stopped','STOPPED');
  const newer={...terminalEvent('task.failed','ERROR'),event_id:'new-error',timestamp_utc:'2026-10-28T03:44:59Z'};
  assert.deepEqual(projectCanonicalEvents([newer,old],RUN,NOW),{state:'ERROR',errors:1});
});
test('later legitimate STOP preserves count of earlier errors',()=>{
  const old=terminalEvent('task.failed','ERROR');
  const newer={...terminalEvent('model.stopped','STOPPED'),event_id:'new-stop',timestamp_utc:'2026-10-28T03:44:59Z'};
  assert.deepEqual(projectCanonicalEvents([newer,old],RUN,NOW),{state:'STOPPED',errors:1});
});
test('future dated terminal event cannot control current state',()=>{
  assert.equal(projectCanonicalEvents([{...terminalEvent('task.failed','ERROR'),timestamp_utc:'2026-10-28T03:45:01Z'}],RUN,NOW).state,'N_D');
});
test('impossible observation date fails source-time admission',()=>{
  const f=projectFeeds([{...feed,id:'eur-usd',observation_date:'2026-02-30'}],NOW)[0];
  assert.equal(f.observedKind,'SOURCE_TIMESTAMP');assert.equal(f.stage,'N_D');
});
test('impossible source timestamp invalidates the feed',()=>{
  const f=projectFeeds([{...feed,source_at_utc:'2026-02-30T03:44:00Z'}],NOW)[0];
  assert.equal(f.stage,'N_D');
});
const trustedSensor={key:'cpu.system.percent',value:39,source:'windows-perfcounter',unit:'%',status:'LIVE',
  observed_at_utc:'2026-10-28T03:44:58Z'};
const trustedFrame={run_id:RUN,polled_utc:'2026-10-28T03:44:59Z',state:'PARTIAL_OR_LIVE',sensors:[trustedSensor]};
test('foreign host frame never borrows current-run sensor values',()=>{
  assert.equal(projectSpaceView({run_id:RUN,hardware:{...trustedFrame,run_id:'OTHER'}},NOW).hardware['cpu.system.percent'].value,null);
});
test('fresh same-run native sensor frame may display value',()=>{
  assert.equal(projectSpaceView({run_id:RUN,hardware:trustedFrame},NOW).hardware['cpu.system.percent'].value,39);
});
test('stale host polled timestamp invalidates even fresh individual sensor',()=>{
  const old={...trustedFrame,polled_utc:'2026-10-28T03:40:00Z'};
  assert.equal(projectSpaceView({run_id:RUN,hardware:old},NOW).hardware['cpu.system.percent'].value,null);
});
test('foreign run market/feed snapshot is never displayed',()=>{
  const f=projectSpaceView({run_id:RUN,feeds:[{...feed,run_id:'OTHER'}]},NOW);
  assert.equal(f.feeds.length,0);
});
test('same-run approved market/feed snapshot is displayed only as source-dated',()=>{
  const f=projectSpaceView({run_id:RUN,feeds:[{...feed,run_id:RUN}]},NOW);
  assert.equal(f.feeds[0].stage,'SOURCE_DATED');
});
test('foreign run CoreID snapshot fails closed',()=>{
  const c={run_id:'OTHER',owner_manifest_sha256:H,approved_core_ids:Array.from({length:8},(_,i)=>'c'+i),
    approved_persona_ids:Array.from({length:5},(_,i)=>'p'+i),core_ids:[],personas:[]};
  assert.equal(projectSpaceView({run_id:RUN,core:c},NOW).core.stage,'N_D');
});
test('E06 integration bar requires a real receipt and exact immutable source tree',()=>{
  const forged={...readiness,bars:readiness.bars.map(x=>x.executor===6?{...x,stage:'INTEGRATED'}:x)};
  assert.equal(projectReadiness(forged,RUN,NOW).bars[5].stage,'HOLD');
});
test('E06 native integration seal is separate from numeric weighting',()=>{
  const r={...readiness,bars:readiness.bars.map(x=>x.executor===6?{...x,
    stage:'INTEGRATED',receipt_sha256:H,source_tree_sha1:'f108d604c444f718b32aaecfd07b90b8f91b9a6f'}:x)};
  const o=projectReadiness(r,RUN,NOW);
  assert.equal(o.bars[5].stage,'INTEGRATED'); assert.equal(o.overall,28);
});
test('E07 Windows ACCEPTED is impossible without a same-EXE SHA and build_id',()=>{
  const a={...readiness,bars:readiness.bars.map(x=>x.executor===6?{...x,
    stage:'INTEGRATED',receipt_sha256:H,source_tree_sha1:'f108d604c444f718b32aaecfd07b90b8f91b9a6f'}:
    x.executor===7?{...x,stage:'WINDOWS_ACCEPTED'}:x)};
  assert.equal(projectReadiness(a,RUN,NOW).bars[6].stage,'NOT_RUN');
});
test('E07 Windows accepted metadata must match E06 frozen one binary',()=>{
  const a={...readiness,build_id:'EXE-1',exe_sha256:H,bars:readiness.bars.map(x=>x.executor===6?{...x,
    stage:'INTEGRATED',receipt_sha256:H,source_tree_sha1:'f108d604c444f718b32aaecfd07b90b8f91b9a6f'}:
    x.executor===7?{...x,stage:'WINDOWS_ACCEPTED',receipt_sha256:H,build_id:'EXE-1',exe_sha256:H}:x)};
  assert.equal(projectReadiness(a,RUN,NOW).bars[6].stage,'WINDOWS_ACCEPTED');
  assert.equal(projectReadiness({...a,exe_sha256:'b'.repeat(64)},RUN,NOW).bars[6].stage,'NOT_RUN');
});
test('untrusted TTL strings never unlock numeric feed values',()=>{
  assert.equal(projectFeeds([{...feed,ttl_ms:'60000'}],NOW)[0].stage,'N_D');
});
test('approved USD/EUR inverse source is recognized but not invented',()=>{
  const f=projectFeeds([{...feed,id:'usd-eur',observation_date:'2026-10-27',value:0.87}],NOW)[0];
  assert.equal(f.observedKind,'ECB_OBSERVATION_DATE');assert.equal(f.value,0.87);
});
test('same-second ERROR wins over STOP so errors cannot be hidden by arrival order',()=>{
  const stop=terminalEvent('model.stopped','STOPPED');
  const fail={...terminalEvent('task.failed','ERROR'),event_id:'same-time-error'};
  assert.equal(projectCanonicalEvents([fail,stop],RUN,NOW).state,'ERROR');
});
console.log('PASSED '+n+' source-level Node assertions; Windows native/EXE NOT_RUN');

// R04: new owner-only negative regressions; NONE constitutes native telemetry.
test('one event_id with conflicting STOP vs ERROR is quarantined',()=>{
  const a=terminalEvent('model.stopped','STOPPED');
  const b=terminalEvent('task.failed','ERROR');
  assert.deepEqual(projectCanonicalEvents([a,b],RUN,NOW),{state:'HOLD_EVENT_ID_COLLISION',errors:null});
});
test('one event_id with conflicting timestamp is quarantined',()=>{
  const a=terminalEvent('model.stopped','STOPPED');
  assert.equal(projectCanonicalEvents([a,{...a,timestamp_utc:'2026-10-28T03:44:59Z'}],RUN,NOW).state,'HOLD_EVENT_ID_COLLISION');
});
test('same event_id with conflicting task_id is quarantined',()=>{
  const a=terminalEvent('task.failed','ERROR');
  assert.equal(projectCanonicalEvents([a,{...a,task_id:'G1-05-OTHER'}],RUN,NOW).errors,null);
});
test('two identical canonical events with different property order count once',()=>{
  const a=terminalEvent('task.failed','ERROR');
  const b=Object.fromEntries(Object.entries(a).reverse());
  assert.deepEqual(projectCanonicalEvents([a,b],RUN,NOW),{state:'ERROR',errors:1});
});
test('a same-run ERROR is not hidden by 65 distinct later non-terminal events',()=>{
  const a=terminalEvent('task.failed','ERROR');
  const nonterminal=Array.from({length:65},(_,i)=>({...a,
    event_id:'evt-noise-'+i,event_type:'task.progress',state:'RUNNING'}));
  assert.deepEqual(projectCanonicalEvents([a,...nonterminal],RUN,NOW),{state:'ERROR',errors:1});
});
test('large unbounded event log is HOLD not misleading STOP',()=>{
  const a=terminalEvent('model.stopped','STOPPED');
  assert.deepEqual(projectCanonicalEvents(Array(4097).fill(a),RUN,NOW),
    {state:'HOLD_JOURNAL_OVERFLOW',errors:null});
});
test('normal bounded 4096 window still accepts unique error',()=>{
  const a=terminalEvent('task.failed','ERROR');
  assert.equal(projectCanonicalEvents([a,...Array(4095).fill(null)],RUN,NOW).state,'ERROR');
});
test('hardware sensor later than native polled time is never LIVE',()=>{
  const f={...trustedFrame,polled_utc:'2026-10-28T03:44:57Z'};
  assert.equal(projectSpaceView({run_id:RUN,hardware:f},NOW).hardware['cpu.system.percent'].stage,'N_D');
});
test('hardware sensor at native polled time may remain LIVE',()=>{
  const f={...trustedFrame,polled_utc:'2026-10-28T03:44:58Z'};
  assert.equal(projectSpaceView({run_id:RUN,hardware:f},NOW).hardware['cpu.system.percent'].value,39);
});
test('VRAM pair from same source but incoherent sample times is HOLD',()=>{
  const s=(key,value,at)=>({key,value,unit:'bytes',source:'NVML',status:'LIVE',observed_at_utc:at});
  const x=projectHardware([s('gpu.vram.used_bytes',1024,'2026-10-28T03:44:50Z'),
    s('gpu.vram.total_bytes',2048,'2026-10-28T03:44:58Z')],NOW);
  assert.equal(x['gpu.vram.used_bytes'].stage,'INCONSISTENT_VRAM');
});
test('feed source observation newer than actual fetch is N/D',()=>{
  const f={...feed,source_at_utc:'2026-10-28T03:44:59Z',fetched_at_utc:'2026-10-28T03:44:50Z'};
  assert.equal(projectFeeds([f],NOW)[0].stage,'N_D');
});
test('negative Brent price cannot be surfaced as actual price',()=>{
  const f={...feed,id:'brent',value:-5};
  assert.equal(projectFeeds([f],NOW)[0].value,null);
});
test('negative weather temperature is not discarded as impossible rate',()=>{
  const f={...feed,value:-5};
  assert.equal(projectFeeds([f],NOW)[0].value,-5);
});
console.log('R04 tests are synthetic JavaScript component gates only, not installed EXE or live devices.');

// R05: false-positive percent defense. Read-only checks do NOT attest native bytes.
test('readiness refuses summary percent without underlying TaskID ledger',()=>{
  const r={...readiness,bars:readiness.bars.map((b,i)=>i===0?{...b,task_ledger:undefined}:b)};
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses repeated TaskIDs even if the sum is 100',()=>{
  const r=structuredClone(readiness);r.bars[0].task_ledger[1].task_id=r.bars[0].task_ledger[0].task_id;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses 100 percent when accepted receipts cover 10 percent',()=>{
  const r=structuredClone(readiness);r.bars[0].percent=100;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses missing owner receipt for a COMPONENT_VERIFIED task',()=>{
  const r=structuredClone(readiness);delete r.bars[0].task_ledger[0].receipt_sha256;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses over/underweight manifest totals',()=>{
  const r=structuredClone(readiness);r.bars[0].task_ledger[0].weight=9;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses NaN weight even when summary is plausible',()=>{
  const r=structuredClone(readiness);r.bars[0].task_ledger[0].weight=NaN;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness refuses false receipt for an unaccepted task',()=>{
  const r=structuredClone(readiness);r.bars[0].task_ledger[1].receipt_sha256=H;
  assert.equal(projectReadiness(r,RUN,NOW).overall,null);
});
test('readiness recomputes the full weighted total from admitted ledgers',()=>{
  const r=projectReadiness(readiness,RUN,NOW);
  assert.deepEqual(r.bars.slice(0,5).map(b=>b.percent),[10,20,30,40,50]);
  assert.equal(r.overall,28);
});
test('native CPU temperature remains N/D absent an observation',()=>{
  assert.equal(projectHardware([],NOW)['cpu.temperature.c'].value,null);
});
test('native CPU temperature may be displayed only with fresh provider/time',()=>{
  const s={key:'cpu.temperature.c',value:57,unit:'°C',source:'WMI-hwmon',status:'LIVE',
    observed_at_utc:'2026-10-28T03:44:58Z'};
  assert.equal(projectHardware([s],NOW)['cpu.temperature.c'].value,57);
  assert.equal(projectHardware([{...s,source:''}],NOW)['cpu.temperature.c'].value,null);
});
test('HELION aggregate is N/D without an explicit owner CoreID weight manifest',()=>{
  const c={owner_manifest_sha256:H,approved_core_ids:Array.from({length:8},(_,i)=>'c'+i),
    approved_persona_ids:Array.from({length:5},(_,i)=>'p'+i),
    core_ids:Array.from({length:8},(_,i)=>({id:'c'+i,percent:i*10,status:'VERIFIED',
      receipt_sha256:H,measured_at_utc:'2026-10-28T03:44:00Z'})),
    personas:Array.from({length:5},(_,i)=>({id:'p'+i,status:'AVAILABLE',observed_at_utc:'2026-10-28T03:44:00Z'}))};
  assert.equal(projectCorePersona(c,NOW).helion,null);
});
test('HELION aggregate honors an explicit uneven approved weighting',()=>{
  const c={owner_manifest_sha256:H,approved_core_ids:Array.from({length:8},(_,i)=>'c'+i),
    approved_persona_ids:Array.from({length:5},(_,i)=>'p'+i),
    core_ids:Array.from({length:8},(_,i)=>({id:'c'+i,percent:i*10,status:'VERIFIED',
      receipt_sha256:H,measured_at_utc:'2026-10-28T03:44:00Z'})),
    personas:Array.from({length:5},(_,i)=>({id:'p'+i,status:'AVAILABLE',observed_at_utc:'2026-10-28T03:44:00Z'})),
    aggregation:{method:'WEIGHTED_V1',receipt_sha256:H,weights:Array.from({length:8},(_,i)=>({id:'c'+i,weight:i===0?30:10}))}};
  assert.equal(projectCorePersona(c,NOW).helion,28);
  c.aggregation.weights[0].weight=20;
  assert.equal(projectCorePersona(c,NOW).helion,null);
});
console.log('R05 added 12 ledger, weighted CoreID and native CPU-temperature regression gates; Windows NOT_RUN.');

// R06: one ambiguity-quarantine method for terminal origin, GPU identity,
// duplicated priced feeds and app-side readback provenance. All synthetic.
test('malformed same-run failure cannot be hidden behind a clean STOP',()=>{
  const broken={...terminalEvent('task.failed','ERROR'),event_id:'broken',message:42};
  assert.deepEqual(projectCanonicalEvents([terminalEvent('model.stopped','STOPPED'),broken],RUN,NOW),
    {state:'HOLD_MALFORMED_TERMINAL',errors:null});
});
test('same-run terminal without a bounded source is quarantined',()=>{
  const broken={...terminalEvent('model.stopped','STOPPED'),source:'\n'};
  assert.equal(projectCanonicalEvents([broken],RUN,NOW).state,'HOLD_MALFORMED_TERMINAL');
});
test('malformed terminal of another RunID cannot stop current run',()=>{
  const foreign={...terminalEvent('task.failed','ERROR'),run_id:'OTHER',message:42};
  assert.equal(projectCanonicalEvents([foreign],RUN,NOW).state,'N_D');
});
const vram=(key,value,deviceId)=>({key,value,unit:'bytes',source:'NVML',status:'LIVE',
  observed_at_utc:'2026-10-28T03:44:58Z',...(deviceId===null?{}:{device_id:deviceId})});
test('two VRAM counters without hardware identity cannot be combined',()=>{
  const x=projectHardware([vram('gpu.vram.used_bytes',2048,null),vram('gpu.vram.total_bytes',8192,null)],NOW);
  assert.equal(x['gpu.vram.used_bytes'].stage,'INCONSISTENT_VRAM');
  assert.equal(x['gpu.vram.total_bytes'].value,null);
});
test('different GPU identifiers cannot be mixed into one VRAM pair',()=>{
  const x=projectHardware([vram('gpu.vram.used_bytes',2048,'GPU-0'),vram('gpu.vram.total_bytes',8192,'GPU-1')],NOW);
  assert.equal(x['gpu.vram.used_bytes'].value,null);
});
test('matching GPU device identifier and native observation permits truthful VRAM',()=>{
  const x=projectHardware([vram('gpu.vram.used_bytes',2048,'GPU-0'),vram('gpu.vram.total_bytes',8192,'GPU-0')],NOW);
  assert.equal(x['gpu.vram.used_bytes'].value,2048);
  assert.equal(x['gpu.vram.total_bytes'].deviceId,'GPU-0');
});
test('two bitcoin prices are quarantined even when each is licensed',()=>{
  const x=projectFeeds([{...feed,id:'bitcoin',value:70000},{...feed,id:'bitcoin',value:80000}],NOW);
  assert.deepEqual(x,[{id:'bitcoin',stage:'HOLD_DUPLICATE_FEED',sourceUtc:null,value:null,observedKind:'N_D'}]);
});
test('hidden seventeenth market quote still blocks first price',()=>{
  const x=projectFeeds([{...feed,id:'brent',value:78},...Array(15).fill(null),{...feed,id:'brent',value:108}],NOW);
  assert.equal(x[0].stage,'HOLD_DUPLICATE_FEED');assert.equal(x[0].value,null);
});
test('two news articles are not treated as conflicting market ticks',()=>{
  const x=projectFeeds([{...feed,id:'nox-news',value:null},{...feed,id:'nox-news',value:null}],NOW);
  assert.equal(x.length,2);assert.equal(x[0].stage,'SOURCE_DATED');
});
test('Drive controller flag without WebView2 proof cannot claim app readback',()=>{
  const x=projectSpaceView({run_id:RUN,build_id:'BUILD-1',drive:{run_id:RUN,build_id:'BUILD-1',
    status:'READBACK_PASS',receipt_sha256:H}},NOW);
  assert.equal(x.driveReadback,'HOLD');
});
test('fresh app-side Drive receipt stays reported, not independently verified',()=>{
  const d={run_id:RUN,build_id:'BUILD-1',origin:'WEBVIEW2_APP',status:'READBACK_PASS',
    readback_at_utc:'2026-10-28T03:44:58Z',receipt_sha256:H};
  const x=projectSpaceView({run_id:RUN,build_id:'BUILD-1',drive:d},NOW);
  assert.equal(x.driveReadback,'APP_REPORTED_READBACK');
  assert.equal(projectSpaceView({run_id:RUN,build_id:'BUILD-1',drive:{...d,
    readback_at_utc:'2026-10-28T03:00:00Z'}},NOW).driveReadback,'HOLD');
});
test('Drive receipt tied to a different installed BuildID is HOLD',()=>{
  const d={run_id:RUN,build_id:'WRONG-EXE',origin:'WEBVIEW2_APP',status:'READBACK_PASS',
    readback_at_utc:'2026-10-28T03:44:58Z',receipt_sha256:H};
  assert.equal(projectSpaceView({run_id:RUN,build_id:'BUILD-1',drive:d},NOW).driveReadback,'HOLD');
});
console.log('R06 ambiguity-quarantine guards PASS (synthetic only); native WebView2/Windows/feeds/Drive readback NOT_RUN.');


// R07: terminal evidence truth, and one physical GPU identity across metrics.
// 12 red/green fixture checks. No claim of Windows/host/provider acceptance.
test('R07 unverified STOP cannot become an accepted terminal state',()=>{
  const e={...terminalEvent('model.stopped','STOPPED'),evidence_verified:false};
  assert.deepEqual(projectCanonicalEvents([e],RUN,NOW),{state:'HOLD_UNVERIFIED_TERMINAL',errors:null});
});
test('R07 unverified ERROR cannot be counted as verified evidence',()=>{
  const e={...terminalEvent('task.failed','ERROR'),evidence_verified:false};
  assert.deepEqual(projectCanonicalEvents([e],RUN,NOW),{state:'HOLD_UNVERIFIED_TERMINAL',errors:null});
});
test('R07 conflicting verified STOP and unverified ERROR require HOLD',()=>{
  const e={...terminalEvent('task.failed','ERROR'),event_id:'later',evidence_verified:false};
  assert.equal(projectCanonicalEvents([terminalEvent('model.stopped','STOPPED'),e],RUN,NOW).state,'HOLD_UNVERIFIED_TERMINAL');
});
test('R07 verified STOP still accepted without introducing progress',()=>{
  assert.deepEqual(projectCanonicalEvents([terminalEvent('model.stopped','STOPPED')],RUN,NOW),
    {state:'STOPPED',errors:0});
});
test('R07 verified ERROR remains visible and counted exactly once',()=>{
  const e=terminalEvent('task.failed','ERROR');
  assert.deepEqual(projectCanonicalEvents([e,e],RUN,NOW),{state:'ERROR',errors:1});
});
test('R07 string evidence_verified never masquerades as native boolean',()=>{
  const e={...terminalEvent('model.stopped','STOPPED'),evidence_verified:'true'};
  assert.equal(projectCanonicalEvents([e],RUN,NOW).state,'HOLD_MALFORMED_TERMINAL');
});
test('R07 foreign-run unverified STOP never holds current run',()=>{
  const e={...terminalEvent('model.stopped','STOPPED'),run_id:'OTHER',evidence_verified:false};
  assert.deepEqual(projectCanonicalEvents([e],RUN,NOW),{state:'N_D',errors:0});
});
const gpu=(key,value,deviceId,unit)=>({key,value,device_id:deviceId,unit,
  source:'NVML',status:'LIVE',observed_at_utc:'2026-10-28T03:44:58Z'});
test('R07 GPU percent without physical device ID stays N/D',()=>{
  const h=projectHardware([gpu('gpu.percent',41,undefined,'%')],NOW);
  assert.equal(h['gpu.percent'].value,null);assert.equal(h['gpu.percent'].stage,'N_D');
});
test('R07 GPU temperature without physical device ID stays N/D',()=>{
  const h=projectHardware([gpu('gpu.temperature.c',64,undefined,'°C')],NOW);
  assert.equal(h['gpu.temperature.c'].value,null);assert.equal(h['gpu.temperature.c'].stage,'N_D');
});
test('R07 GPU percent and VRAM from different devices cannot become one GPU',()=>{
  const h=projectHardware([gpu('gpu.percent',41,'GPU-1','%'),
    gpu('gpu.vram.used_bytes',1024,'GPU-0','bytes'),
    gpu('gpu.vram.total_bytes',2048,'GPU-0','bytes')],NOW);
  assert.equal(h['gpu.percent'].value,null);assert.equal(h['gpu.vram.used_bytes'].value,null);
  assert.equal(h['gpu.percent'].stage,'HOLD_GPU_DEVICE_CONFLICT');
});
test('R07 GPU temperature and GPU utilization cannot mix device identities',()=>{
  const h=projectHardware([gpu('gpu.percent',22,'GPU-0','%'),
    gpu('gpu.temperature.c',58,'GPU-1','°C')],NOW);
  assert.equal(h['gpu.percent'].value,null);assert.equal(h['gpu.temperature.c'].value,null);
});
test('R07 same-device percent temperature VRAM remain LIVE and correctly sourced',()=>{
  const h=projectHardware([gpu('gpu.percent',22,'GPU-0','%'),
    gpu('gpu.temperature.c',58,'GPU-0','°C'),
    gpu('gpu.vram.used_bytes',1024,'GPU-0','bytes'),
    gpu('gpu.vram.total_bytes',2048,'GPU-0','bytes')],NOW);
  assert.equal(h['gpu.percent'].value,22);assert.equal(h['gpu.temperature.c'].value,58);
  assert.equal(h['gpu.vram.used_bytes'].value,1024);assert.equal(h['gpu.vram.total_bytes'].value,2048);
});
console.log('R07 SOURCE-ONLY truth envelope tests; physical Windows GPU/WebView2/Drive still NOT_RUN.');
// R08: host-level evidence-status consistency. A native polling frame that
// explicitly reports UNAVAILABLE is not allowed to display embedded LIVE data.
const r08Sensor=(key,value,unit,device_id)=>({key,value,unit,
  ...(device_id?{device_id}:{}),status:'LIVE',source:'WindowsNative',
  observed_at_utc:'2026-10-28T03:44:58Z'});
const r08Frame=(state,sensors)=>({run_id:RUN,polled_utc:'2026-10-28T03:44:59Z',state,sensors});
const r08Hardware=(state,sensors)=>projectSpaceView({run_id:RUN,hardware:r08Frame(state,sensors)},NOW).hardware;
test('R08 unavailable polling frame must not display an embedded LIVE CPU percentage',()=>{
  assert.equal(r08Hardware('UNAVAILABLE',[r08Sensor('cpu.system.percent',73,'%')])['cpu.system.percent'].value,null);
});
test('R08 unavailable polling frame must not display an embedded LIVE CPU temperature',()=>{
  assert.equal(r08Hardware('UNAVAILABLE',[r08Sensor('cpu.temperature.c',75,'°C')])['cpu.temperature.c'].value,null);
});
test('R08 unavailable polling frame must not display an embedded LIVE GPU percentage',()=>{
  assert.equal(r08Hardware('UNAVAILABLE',[r08Sensor('gpu.percent',54,'%','GPU-0')])['gpu.percent'].value,null);
});
test('R08 unavailable polling frame must not display embedded LIVE VRAM',()=>{
  const h=r08Hardware('UNAVAILABLE',[r08Sensor('gpu.vram.used_bytes',1024,'bytes','GPU-0'),r08Sensor('gpu.vram.total_bytes',2048,'bytes','GPU-0')]);
  assert.equal(h['gpu.vram.used_bytes'].value,null);assert.equal(h['gpu.vram.total_bytes'].value,null);
});
test('R08 unavailable frame with a mixture of CPU and GPU readings remains all N/D',()=>{
  const h=r08Hardware('UNAVAILABLE',[r08Sensor('cpu.system.percent',12,'%'),r08Sensor('gpu.percent',78,'%','GPU-0')]);
  assert.equal(h['cpu.system.percent'].stage,'N_D');assert.equal(h['gpu.percent'].stage,'N_D');
});
test('R08 LIVE polling frame still accepts a consistent native CPU reading',()=>{
  assert.equal(r08Hardware('LIVE',[r08Sensor('cpu.system.percent',73,'%')])['cpu.system.percent'].value,73);
});
test('R08 PARTIAL_OR_LIVE polling frame still accepts present native CPU reading',()=>{
  assert.equal(r08Hardware('PARTIAL_OR_LIVE',[r08Sensor('cpu.system.percent',73,'%')])['cpu.system.percent'].value,73);
});
test('R08 error frame must not expose a LIVE GPU reading',()=>{
  assert.equal(r08Hardware('ERROR',[r08Sensor('gpu.percent',54,'%','GPU-0')])['gpu.percent'].value,null);
});
test('R08 missing frame state must not expose a LIVE CPU reading',()=>{
  assert.equal(r08Hardware(undefined,[r08Sensor('cpu.system.percent',73,'%')])['cpu.system.percent'].value,null);
});
test('R08 missing hardware data still produces six explicit N/D tiles',()=>{
  const h=projectSpaceView({run_id:RUN},NOW).hardware;
  assert.equal(Object.keys(h).length,6);assert.ok(Object.values(h).every(x=>x.value===null&&x.stage==='N_D'));
});
test('R08 UNAVAILABLE hardware frame never promotes app-side Drive readback',()=>{
  const v=projectSpaceView({run_id:RUN,hardware:r08Frame('UNAVAILABLE',[r08Sensor('cpu.system.percent',73,'%')])},NOW);
  assert.equal(v.driveReadback,'HOLD');assert.equal(v.hardware['cpu.system.percent'].value,null);
});
test('R08 direct hardware projection stays independent of native frame-status admission',()=>{
  assert.equal(projectHardware([r08Sensor('cpu.system.percent',73,'%')],NOW)['cpu.system.percent'].value,73);
});
console.log('R08: native UNAVAILABLE frame cannot report hardware LIVE; E07/Windows NOT_RUN.');

// R09: one-GPU-tile provenance: do not conflate different providers or samples.
const r09Gpu=(key,value,{source='NVML',sample_id,at='2026-10-28T03:44:58Z',device_id='GPU-0'}={})=>({
  key,value,source,device_id,...(sample_id===undefined?{}:{sample_id}),
  status:'LIVE',unit:key.includes('vram')?'bytes':key.includes('temperature')?'°C':'%',
  observed_at_utc:at});
const r09Tile=(rows)=>projectHardware(rows,NOW);
const r09NoLive=(h,...keys)=>keys.forEach(k=>{
  assert.equal(h[k].value,null,`${k} must not remain LIVE`);
  assert.equal(h[k].stage,'HOLD_GPU_SAMPLE_CONFLICT');
});
test('R09 conflicting NVML and WMI GPU percentage and temperature are quarantined',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',40),r09Gpu('gpu.temperature.c',60,{source:'WMI'})]);
  r09NoLive(h,'gpu.percent','gpu.temperature.c');
});
test('R09 mixed GPU percent provider and VRAM provider are quarantined',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{source:'NVML'}),
    r09Gpu('gpu.vram.used_bytes',1024,{source:'DXGI'}),
    r09Gpu('gpu.vram.total_bytes',2048,{source:'DXGI'})]);
  r09NoLive(h,'gpu.percent','gpu.vram.used_bytes','gpu.vram.total_bytes');
});
test('R09 one provider but timestamps 10 seconds apart are not one GPU sample',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{at:'2026-10-28T03:44:48Z'}),
    r09Gpu('gpu.temperature.c',60,{at:'2026-10-28T03:44:58Z'})]);
  r09NoLive(h,'gpu.percent','gpu.temperature.c');
});
test('R09 same GPU provider and identical timestamp remains LIVE',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45),r09Gpu('gpu.temperature.c',60)]);
  assert.equal(h['gpu.percent'].value,45);assert.equal(h['gpu.temperature.c'].value,60);
});
test('R09 same GPU provider and five-second timestamp span stays LIVE',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{at:'2026-10-28T03:44:53Z'}),r09Gpu('gpu.temperature.c',60)]);
  assert.equal(h['gpu.percent'].value,45);assert.equal(h['gpu.temperature.c'].value,60);
});
test('R09 different native sample IDs on one GPU are quarantined',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{sample_id:'poll-12'}),
    r09Gpu('gpu.temperature.c',60,{sample_id:'poll-13'})]);
  r09NoLive(h,'gpu.percent','gpu.temperature.c');
});
test('R09 partial native sample IDs on one GPU are quarantined',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{sample_id:'poll-12'}),
    r09Gpu('gpu.temperature.c',60)]);
  r09NoLive(h,'gpu.percent','gpu.temperature.c');
});
test('R09 matching native sample IDs on one GPU remain LIVE',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{sample_id:'poll-12'}),
    r09Gpu('gpu.temperature.c',60,{sample_id:'poll-12'})]);
  assert.equal(h['gpu.percent'].value,45);assert.equal(h['gpu.temperature.c'].value,60);
});
test('R09 source mismatch within same device and identical sample ID is still blocked',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45,{sample_id:'poll-12'}),
    r09Gpu('gpu.temperature.c',60,{sample_id:'poll-12',source:'WMI'})]);
  r09NoLive(h,'gpu.percent','gpu.temperature.c');
});
test('R09 mixed provider CPU temperature does not contaminate sole GPU reading',()=>{
  const h=r09Tile([r09Gpu('gpu.percent',45),{key:'cpu.temperature.c',value:64,
    source:'WMI',unit:'°C',status:'LIVE',observed_at_utc:'2026-10-28T03:44:58Z'}]);
  assert.equal(h['gpu.percent'].value,45);assert.equal(h['cpu.temperature.c'].value,64);
});
test('R09 two VRAM counters within five seconds same source still LIVE',()=>{
  const h=r09Tile([r09Gpu('gpu.vram.used_bytes',1024,{at:'2026-10-28T03:44:54Z'}),
    r09Gpu('gpu.vram.total_bytes',2048,{at:'2026-10-28T03:44:58Z'})]);
  assert.equal(h['gpu.vram.used_bytes'].value,1024);assert.equal(h['gpu.vram.total_bytes'].value,2048);
});
test('R09 missing any real GPU samples stays N/D without inferred zeros',()=>{
  const h=r09Tile([]);assert.equal(h['gpu.percent'].value,null);
  assert.equal(h['gpu.temperature.c'].value,null);
});
console.log('R09 GPU tile strict provider/time/sample guards; native Windows NOT_RUN.');


// R10: reject identity collisions across sealed P01–P05 task ledgers and
// missing/impossible native terminal timestamps before presenting STOP.
const oneTaskBar=(i,taskId)=>({executor:i,stage:'CRITERIA_VERIFIED',percent:100,total_tasks:1,
  task_ledger:[{task_id:taskId,weight:100,status:'COMPONENT_VERIFIED',receipt_sha256:H}],
  manifest_sha256:H,receipt_sha256:H});
const oneTaskReadiness=ids=>({...readiness,overall:100,
  bars:ids.map((id,i)=>oneTaskBar(i+1,id)).concat(readiness.bars.slice(5))});
const datedError=(time)=>({...terminalEvent('task.failed','ERROR'),event_id:'R10-bad-time',timestamp_utc:time});
const laterStop={...terminalEvent('model.stopped','STOPPED'),event_id:'R10-later-stop',
  timestamp_utc:'2026-10-28T03:44:59Z'};
test('R10 missing same-run ERROR timestamp cannot hide under a later STOP',()=>{
  assert.equal(projectCanonicalEvents([datedError(undefined),laterStop],RUN,NOW).state,
    'HOLD_MALFORMED_TERMINAL_TIMESTAMP');
});
test('R10 malformed same-run ERROR timestamp cannot hide under a later STOP',()=>{
  assert.equal(projectCanonicalEvents([datedError('INVALID'),laterStop],RUN,NOW).state,
    'HOLD_MALFORMED_TERMINAL_TIMESTAMP');
});
test('R10 impossible calendar timestamp is quarantined',()=>{
  assert.equal(projectCanonicalEvents([datedError('2026-02-30T03:44:58Z')],RUN,NOW).state,
    'HOLD_MALFORMED_TERMINAL_TIMESTAMP');
});
test('R10 numeric-offset timestamp not in canonical UTC schema is quarantined',()=>{
  assert.equal(projectCanonicalEvents([datedError('2026-10-28T03:44:58+00:00')],RUN,NOW).state,
    'HOLD_MALFORMED_TERMINAL_TIMESTAMP');
});
test('R10 missing model.stopped timestamp is quarantined',()=>{
  assert.equal(projectCanonicalEvents([{...laterStop,timestamp_utc:null}],RUN,NOW).state,
    'HOLD_MALFORMED_TERMINAL_TIMESTAMP');
});
test('R10 invalid timestamp on a nonterminal does not forge ERROR',()=>{
  const noise={...datedError('INVALID'),event_type:'task.progress',state:'RUNNING'};
  assert.equal(projectCanonicalEvents([noise,laterStop],RUN,NOW).state,'STOPPED');
});
test('R10 foreign-run invalid timestamp cannot poison current run',()=>{
  assert.equal(projectCanonicalEvents([{...datedError('INVALID'),run_id:'OTHER'},laterStop],RUN,NOW).state,
    'STOPPED');
});
test('R10 old but correctly dated terminal remains outside 30-second window',()=>{
  assert.equal(projectCanonicalEvents([datedError('2026-10-28T03:40:00Z')],RUN,NOW).state,'N_D');
});
test('R10 valid terminal time still displays verified ERROR',()=>{
  assert.equal(projectCanonicalEvents([datedError('2026-10-28T03:44:58Z')],RUN,NOW).state,'ERROR');
});
test('R10 same TaskID in two valid owner lanes cannot be double counted',()=>{
  const r=projectReadiness(oneTaskReadiness(['P01-A','P02-B','P03-C','P04-D','P01-A']),RUN,NOW);
  assert.equal(r.overall,null);assert.equal(r.reason,'CROSS_LANE_TASK_COLLISION');
});
test('R10 identical TaskID repeated in all five lanes is quarantined',()=>{
  assert.equal(projectReadiness(oneTaskReadiness(Array(5).fill('ONE-TASK')),RUN,NOW).reason,
    'CROSS_LANE_TASK_COLLISION');
});
test('R10 distinct global TaskIDs retain the 20/25/20/25/10 formula',()=>{
  const r=projectReadiness(oneTaskReadiness(['P01-A','P02-B','P03-C','P04-D','P05-E']),RUN,NOW);
  assert.equal(r.overall,100);assert.equal(r.reason,'E06_OWNER_PROJECTED');
});
console.log('R10 TOTAL PASSED '+n+' assertions; Native Windows EXE = NOT_RUN');
