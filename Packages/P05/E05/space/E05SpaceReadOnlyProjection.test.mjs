import assert from 'node:assert/strict';
import {projectSpaceView,projectReadiness,projectFeeds,projectHardware,projectCorePersona,
  projectCanonicalEvents,LOCKED_BASELINE,EVENT_SCHEMA} from './E05SpaceReadOnlyProjection.mjs';
const NOW=Date.parse('2026-10-28T03:45:00Z');
const H='a'.repeat(64),RUN='NOX-E05-TURBO10-R02';
const bar=i=>({executor:i,stage:'CRITERIA_VERIFIED',percent:i*10,total_tasks:10,manifest_sha256:H,receipt_sha256:H});
const readiness={run_id:RUN,source_commit:LOCKED_BASELINE,at_utc:'2026-10-28T03:44:58Z',
  native_attestation:'E06_OWNER_VERIFIED',bars:[1,2,3,4,5].map(bar).concat([
    {executor:6,stage:'HOLD',percent:null},{executor:7,stage:'NOT_RUN',percent:null}]),overall:28};
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
    personas:Array.from({length:5},(_,i)=>({id:'person-'+i,status:'AVAILABLE',observed_at_utc:'2026-10-28T03:44:00Z'}))};
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
  const e={schema:EVENT_SCHEMA,run_id:RUN,event_type:'model.stopped',timestamp_utc:'2026-10-28T03:44:58Z'};
  assert.deepEqual(projectCanonicalEvents([e],RUN,NOW),{state:'STOPPED',errors:0});
});
test('foreign STOP cannot stop another RunID',()=>{
  const e={schema:EVENT_SCHEMA,run_id:'OTHER',event_type:'model.stopped',timestamp_utc:'2026-10-28T03:44:58Z'};
  assert.equal(projectCanonicalEvents([e],RUN,NOW).state,'N_D');
});
test('Drive readback never claimed without same-run proof',()=>{
  const v=projectSpaceView({run_id:RUN,drive:{run_id:'OTHER',status:'READBACK_PASS',receipt_sha256:H}},NOW);
  assert.equal(v.driveReadback,'HOLD');assert.equal(v.readiness.overall,null);
});
console.log('PASSED '+n+'/18 source-level Node assertions; Windows native/EXE NOT_RUN');
