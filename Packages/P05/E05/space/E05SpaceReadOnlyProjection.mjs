// NOX V16 E05: read-only WebView2 projection. E06 owns verification and events.v3.
// No network, timers, event writers, OAuth, D02 DOM, or second data store here.
export const EVENT_SCHEMA = 'NOX-INSTALLER-EVENT-v3';
export const LOCKED_BASELINE = '0b3a7d435be735148d64171deb9027093a89646e';
const weights = [0.20, 0.25, 0.20, 0.25, 0.10];
const sourceIds = new Set(['weather','nox-news','msstx-news','eur-usd','usd-eur','eur-rub','bitcoin','brent','finance-news']);
const maximumAges = Object.freeze({weather:2700000,'nox-news':172800000,'msstx-news':172800000,'eur-usd':864000000,'usd-eur':864000000,'eur-rub':864000000,bitcoin:300000,brent:86400000,'finance-news':172800000});
const sha = v => typeof v === 'string' && /^[a-f0-9]{64}$/i.test(v);
const pct = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100;
// Date.parse silently normalizes impossible dates (e.g. February 30). Verify
// calendar fields before a source timestamp may be displayed as authoritative.
const isoUtc = v => {
  if (typeof v !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(v)) return false;
  const ms=Date.parse(v);
  if (!Number.isFinite(ms)) return false;
  const d=new Date(ms);
  return d.getUTCFullYear()===Number(v.slice(0,4)) &&
    d.getUTCMonth()+1===Number(v.slice(5,7)) &&
    d.getUTCDate()===Number(v.slice(8,10)) &&
    d.getUTCHours()===Number(v.slice(11,13)) &&
    d.getUTCMinutes()===Number(v.slice(14,16)) &&
    d.getUTCSeconds()===Number(v.slice(17,19));
};
const observationUtc = v => typeof v === 'string' && /^\d{4}-\d\d-\d\d$/.test(v) && isoUtc(v+'T00:00:00Z');
const ago = (iso, now, max) => isoUtc(iso) && now - Date.parse(iso) >= 0 && now - Date.parse(iso) <= max;
const validRunId = v => typeof v === 'string' && /^[A-Za-z0-9_.-]{1,160}$/.test(v);
const status = v => typeof v === 'string' && /^[A-Z_]{1,40}$/.test(v) ? v : 'N_D';
const unique = (items, n) => Array.isArray(items) && items.length === n && items.every(v => typeof v === 'string' && v.length > 0) && new Set(items).size === n;

// Only an E06 *native* sealed DTO is admissible; a JavaScript flag is not a
// cryptographic owner receipt. Consumers must never promote this view to QA.
export function projectReadiness(readiness, runId, nowMs) {
  const bars = Array.from({length: 7}, (_, i) => ({executor:i+1, percent:null, stage:i<5?'N_D':i===5?'HOLD':'NOT_RUN'}));
  if (!validRunId(runId) || !readiness || readiness.run_id !== runId ||
      readiness.source_commit !== LOCKED_BASELINE || !ago(readiness.at_utc, nowMs, 30000) ||
      readiness.native_attestation !== 'E06_OWNER_VERIFIED' ||
      !Array.isArray(readiness.bars) || readiness.bars.length !== 7) {
    return {bars, overall:null, reason:'FROZEN_OWNER_EVIDENCE_REQUIRED'};
  }
  const five = [];
  for (let i=0; i<5; i++) {
    const b = readiness.bars[i];
    if (!b || b.executor !== i+1 || b.stage !== 'CRITERIA_VERIFIED' ||
        !sha(b.manifest_sha256) || !sha(b.receipt_sha256) ||
        !pct(b.percent) || !Number.isInteger(b.total_tasks) || b.total_tasks < 1) {
      return {bars, overall:null, reason:'LANE_OWNER_SEAL_MISSING'};
    }
    five.push(b.percent);
  }
  for (let i=0; i<5; i++) bars[i] = {executor:i+1,percent:five[i],stage:'COMPONENT_VERIFIED'};
  const stage6 = readiness.bars[5], stage7 = readiness.bars[6];
  const integrated=stage6?.executor===6 && stage6?.percent==null &&
    stage6?.stage==='INTEGRATED' && sha(stage6.receipt_sha256) &&
    stage6.source_tree_sha1==='f108d604c444f718b32aaecfd07b90b8f91b9a6f';
  bars[5].stage=integrated?'INTEGRATED':'HOLD';
  const windowsAccepted=integrated && stage7?.executor===7 &&
    stage7?.percent==null && stage7?.stage==='WINDOWS_ACCEPTED' &&
    sha(stage7.receipt_sha256) && sha(stage7.exe_sha256) &&
    validRunId(stage7.build_id) && stage7.build_id===readiness.build_id &&
    stage7.exe_sha256===readiness.exe_sha256;
  bars[6].stage=windowsAccepted?'WINDOWS_ACCEPTED':'NOT_RUN';
  const overall = Math.round(five.reduce((v,x,i)=>v+x*weights[i],0)*100)/100;
  return {bars, overall: pct(readiness.overall) && Math.abs(readiness.overall-overall)<0.005 ? overall:null,
    reason: pct(readiness.overall) && Math.abs(readiness.overall-overall)<0.005 ? 'E06_OWNER_PROJECTED':'WEIGHTED_MISMATCH'};
}

export function projectHardware(sensors, nowMs) {
  const expected = {'cpu.system.percent':['%',100], 'gpu.percent':['%',100],
    'gpu.vram.used_bytes':['bytes',Number.MAX_SAFE_INTEGER],
    'gpu.vram.total_bytes':['bytes',Number.MAX_SAFE_INTEGER],
    'gpu.temperature.c':['°C',150]};
  const result = {};
  for (const [key,[unit,max]] of Object.entries(expected)) {
    const found = Array.isArray(sensors) ? sensors.filter(s=>s?.key===key) : [];
    const s=found.length===1?found[0]:null;
    const valid=s?.status==='LIVE' && s.unit===unit && typeof s.source==='string' && s.source.trim() &&
      typeof s.value==='number' && Number.isFinite(s.value) && s.value>=0 && s.value<=max &&
      ago(s.observed_at_utc,nowMs,30000);
    result[key]={value: valid?s.value:null, source:valid?s.source:null, stage:valid?'LIVE':'N_D'};
  }
  const used=result['gpu.vram.used_bytes'],total=result['gpu.vram.total_bytes'];
  if (used.value!==null && total.value!==null &&
      (total.value===0 || used.value>total.value || used.source!==total.source)) {
    used.value=total.value=null; used.stage=total.stage='INCONSISTENT_VRAM';
  }
  return result;
}

export function projectCorePersona(core, nowMs) {
  const denied={helion:null,coreIds:[],personas:[],stage:'N_D'};
  if (!core || !sha(core.owner_manifest_sha256) || !unique(core.approved_core_ids,8) ||
      !unique(core.approved_persona_ids,5) || !Array.isArray(core.core_ids) ||
      !Array.isArray(core.personas) || core.core_ids.length!==8 || core.personas.length!==5) return denied;
  const seenCore=new Set(),seenPersona=new Set();
  const outCores=[];
  for (const c of core.core_ids) {
    if (!c || !core.approved_core_ids.includes(c.id) || seenCore.has(c.id)) return denied;
    seenCore.add(c.id);
    const good=c.status==='VERIFIED' && sha(c.receipt_sha256) && pct(c.percent) &&
      ago(c.measured_at_utc,nowMs,300000);
    outCores.push({id:c.id,percent:good?c.percent:null,stage:good?'VERIFIED':'N_D'});
  }
  const outPersonas=[];
  for (const p of core.personas) {
    if (!p || !core.approved_persona_ids.includes(p.id) || seenPersona.has(p.id)) return denied;
    seenPersona.add(p.id);
    const valid=ago(p.observed_at_utc,nowMs,300000) && ['AVAILABLE','OFFLINE'].includes(p.status);
    outPersonas.push({id:p.id,stage:valid?p.status:'OFFLINE'});
  }
  const complete=outCores.every(c=>c.percent!==null);
  return {helion:complete?Math.round(outCores.reduce((a,c)=>a+c.percent,0)/8*100)/100:null,
    coreIds:outCores,personas:outPersonas,stage:complete?'SOURCE_DATED':'N_D'};
}

export function projectFeeds(feeds, nowMs) {
  if (!Array.isArray(feeds)) return [];
  return feeds.slice(0,16).filter(f=>f && sourceIds.has(f.id)).map(f=>{
    const fxDate=f.id==='eur-usd'||f.id==='usd-eur';
    const observationSupplied=fxDate && f.observation_date!==undefined;
    const dateOnly=observationSupplied && observationUtc(f.observation_date);
    const sourceTime=observationSupplied ?
      (dateOnly?f.observation_date+'T00:00:00Z':null) : f.source_at_utc;
    const ttl=Number.isInteger(f.ttl_ms)&&f.ttl_ms>0&&f.ttl_ms<=86400000?f.ttl_ms:0;
    const fetched=ttl>0 && ago(f.fetched_at_utc,nowMs,ttl);
    const dated=ago(sourceTime,nowMs,maximumAges[f.id]);
    const approved=f.license_status==='APPROVED' && sha(f.license_receipt_sha256) &&
      typeof f.provider==='string' && f.provider.length>0;
    const stale=['OFFLINE_CACHE','STALE_CACHE','STALE_SOURCE','OFFLINE'].includes(f.status);
    const stage=!approved?'DISABLED':stale?'STALE_CACHE':
      dated && fetched && ['LIVE','CACHE'].includes(f.status)?'SOURCE_DATED':'N_D';
    return {id:f.id,stage,sourceUtc:isoUtc(sourceTime)?sourceTime:null,
      value:stage==='SOURCE_DATED' && f.parsed_by_owner===true &&
        typeof f.value==='number' && Number.isFinite(f.value)?f.value:null,
      observedKind:dateOnly?'ECB_OBSERVATION_DATE':'SOURCE_TIMESTAMP'};
  });
}

// The original R11 events.v3 has a strict envelope, not just an event_type.
// This view is deliberately not an event writer, journal or second bus.
const eventPackages = new Set(['P01','P02','P03','P04','P05','E06','E07']);
const canonicalTerminal = e => e && e.schema===EVENT_SCHEMA &&
  validRunId(e.run_id) && validRunId(e.event_id) && validRunId(e.task_id) &&
  validRunId(e.action_id) && eventPackages.has(e.package_id) &&
  typeof e.source==='string' && e.source.length>0 && e.source.length<=120 &&
  !/[\x00-\x1f\x7f]/.test(e.source) &&
  typeof e.message==='string' && e.message.length<=240 &&
  !/[\x00-\x1f\x7f]/.test(e.message) &&
  typeof e.evidence_verified==='boolean' &&
  ((e.event_type==='model.stopped' && e.state==='STOPPED') ||
   (e.event_type==='task.failed' && e.state==='ERROR'));

export function projectCanonicalEvents(events, runId, nowMs) {
  if (!Array.isArray(events) || !validRunId(runId) || !Number.isFinite(nowMs))
    return {state:'N_D',errors:0};
  // Canonical event journal order is not guaranteed by asynchronous UI delivery.
  // Sorting by trusted event timestamp makes the last terminal state deterministic.
  const terminal=[];
  const seen=new Set();
  for (const e of events.slice(-64)) {
    if (!canonicalTerminal(e) || e.run_id!==runId ||
        !ago(e.timestamp_utc,nowMs,30000) || seen.has(e.event_id)) continue;
    seen.add(e.event_id);
    terminal.push(e);
  }
  terminal.sort((a,b)=>Date.parse(a.timestamp_utc)-Date.parse(b.timestamp_utc) ||
    (a.state==='ERROR'?1:0)-(b.state==='ERROR'?1:0));
  return {state:terminal.length===0?'N_D':terminal.at(-1).state,
    errors:terminal.filter(e=>e.event_type==='task.failed').length};
}

// E06 must project the original native DTO into these same-run envelopes.
// Without a signed E06 readback, this is only a display of owner-reported data.
export function projectSpaceView(host, nowMs=Date.now()) {
  if (!host || !validRunId(host.run_id) || !Number.isFinite(nowMs)) return null;
  const hardwareFrame=host.hardware;
  const sameRunFrame=hardwareFrame?.run_id===host.run_id &&
    ago(hardwareFrame.polled_utc,nowMs,30000) &&
    ['LIVE','PARTIAL_OR_LIVE','UNAVAILABLE'].includes(hardwareFrame.state);
  const sameRunCore=host.core?.run_id===host.run_id ? host.core : null;
  // Feeds are host-owned approvals, never auto-fetched or shared across runs.
  const sameRunFeeds=Array.isArray(host.feeds) ?
    host.feeds.filter(f=>f?.run_id===host.run_id) : [];
  return Object.freeze({schema:'NOX-E05-SPACE-READONLY-v1',runId:host.run_id,
    readiness:projectReadiness(host.readiness,host.run_id,nowMs),
    hardware:projectHardware(sameRunFrame?hardwareFrame.sensors:[],nowMs),
    core:projectCorePersona(sameRunCore,nowMs),
    feeds:projectFeeds(sameRunFeeds,nowMs),
    events:projectCanonicalEvents(host.events,host.run_id,nowMs),
    driveReadback:host.drive?.run_id===host.run_id &&
      host.drive?.status==='READBACK_PASS' && sha(host.drive?.receipt_sha256)
        ?'APP_REPORTED_READBACK':'HOLD'}); // E06 must independently attest actual Drive response.
}
