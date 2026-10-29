// NOX V16 E05: read-only WebView2 projection. E06 owns verification and events.v3.
// No network, timers, event writers, OAuth, D02 DOM, or second data store here.
export const EVENT_SCHEMA = 'NOX-INSTALLER-EVENT-v3';
export const LOCKED_BASELINE = '0b3a7d435be735148d64171deb9027093a89646e';
const weights = [0.20, 0.25, 0.20, 0.25, 0.10];
const sourceIds = new Set(['weather','nox-news','msstx-news','eur-usd','usd-eur','eur-rub','bitcoin','brent','finance-news']);
const singletonMarketIds = new Set(['eur-usd','usd-eur','eur-rub','bitcoin','brent']);
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
const round2 = n => Math.round((n + Number.EPSILON) * 100) / 100;
// E06 must have already authenticated the native owner ledger. This pure
// projection ONLY checks internal consistency; a SHA-shaped string is not a
// signature and this code must never be the authority that accepts a release.
const derivedLaneProgress = b => {
  if (!Number.isInteger(b.total_tasks) || b.total_tasks < 1 || b.total_tasks > 5000 ||
      !Array.isArray(b.task_ledger) || b.task_ledger.length !== b.total_tasks) return null;
  let denominator = 0, accepted = 0;
  let allAccepted = true;
  const seen = new Set();
  for (const task of b.task_ledger) {
    if (!task || !validRunId(task.task_id) || seen.has(task.task_id) ||
        typeof task.weight !== 'number' || !Number.isFinite(task.weight) ||
        task.weight <= 0 || task.weight > 100 ||
        !['SOURCE','HOLD','FAILED','NOT_RUN','COMPONENT_VERIFIED'].includes(task.status)) return null;
    seen.add(task.task_id);
    denominator += task.weight;
    if (task.status === 'COMPONENT_VERIFIED') {
      if (!sha(task.receipt_sha256)) return null;
      accepted += task.weight;
    } else {
      allAccepted = false;
      if (task.receipt_sha256 != null) return null; // reject claiming a receipt for pending work
    }
  }
  if (Math.abs(denominator - 100) > 0.000001) return null;
  // 100 is a TaskID completion claim, not a rounded approximation.
  return allAccepted ? 100 : Math.min(99.99, round2(accepted));
};


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
  const five = Array(5).fill(null);
  // TaskID identifies a single project criterion across P01–P05. Duplicate
  // IDs in different owner ledgers are not independent evidence or weight.
  const globalTaskIds = new Set();
  for (let i=0; i<5; i++) {
    const b = readiness.bars[i];
    const derived=b?derivedLaneProgress(b):null;
    if (!b || b.executor !== i+1 || b.stage !== 'CRITERIA_VERIFIED' ||
        !sha(b.manifest_sha256) || !sha(b.receipt_sha256) ||
        !pct(b.percent) || derived === null ||
        Math.abs(b.percent - derived) > 0.005) {
      continue; // Unknown lane does not erase independently sealed owner lanes.
    }
    if (b.task_ledger.some(t=>globalTaskIds.has(t.task_id)))
      return {bars,overall:null,reason:'CROSS_LANE_TASK_COLLISION'};
    for (const task of b.task_ledger) globalTaskIds.add(task.task_id);
    five[i]=derived;
  }
  for (let i=0; i<5; i++) if (five[i]!==null)
    bars[i] = {executor:i+1,percent:five[i],stage:'COMPONENT_VERIFIED'};
  if (five.some(value=>value===null))
    return {bars,overall:null,reason:'LANE_OWNER_SEAL_MISSING'};
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
  const roundedOverall = round2(five.reduce((v,x,i)=>v+x*weights[i],0));
  // Even a 99.99 lane can round back to 100 after product weighting.
  const overall = five.every(value=>value===100) ? 100 : Math.min(99.99, roundedOverall);
  return {bars, overall: pct(readiness.overall) && Math.abs(readiness.overall-overall)<0.005 ? overall:null,
    reason: pct(readiness.overall) && Math.abs(readiness.overall-overall)<0.005 ? 'E06_OWNER_PROJECTED':'WEIGHTED_MISMATCH'};
}

export function projectHardware(sensors, nowMs, polledUtc=null) {
  const expected = {'cpu.system.percent':['%',100], 'gpu.percent':['%',100],
    'gpu.vram.used_bytes':['bytes',Number.MAX_SAFE_INTEGER],
    'gpu.vram.total_bytes':['bytes',Number.MAX_SAFE_INTEGER],
    'gpu.temperature.c':['°C',150], 'cpu.temperature.c':['°C',150]};
  const result = {};
  const nativeGpuSample = new Map(); // ephemeral: do not add fields to public DTO
  for (const [key,[unit,max]] of Object.entries(expected)) {
    const found = Array.isArray(sensors) ? sensors.filter(s=>s?.key===key) : [];
    const s=found.length===1?found[0]:null;
    const valid=s?.status==='LIVE' && s.unit===unit && typeof s.source==='string' && s.source.trim() &&
      typeof s.value==='number' && Number.isFinite(s.value) && s.value>=0 && s.value<=max &&
      (!key.endsWith('.used_bytes') && !key.endsWith('.total_bytes') ||
        Number.isSafeInteger(s.value)) &&
      ago(s.observed_at_utc,nowMs,30000) &&
      // Optional native sample ID must be bounded and unambiguous if supplied.
      (!key.startsWith('gpu.') || s.sample_id===undefined || validRunId(s.sample_id)) &&
      // A sensor cannot be observed AFTER the enclosing native polling frame.
      (polledUtc===null || (isoUtc(polledUtc) && Date.parse(s.observed_at_utc)<=Date.parse(polledUtc)));
    if (key.startsWith('gpu.')) nativeGpuSample.set(key,valid?(s.sample_id ?? null):null);
    result[key]={value: valid?s.value:null, source:valid?s.source:null, stage:valid?'LIVE':'N_D',
      observedUtc:valid?s.observed_at_utc:null,
      deviceId:valid && typeof s.device_id==='string' && /^[A-Za-z0-9:._\/-]{1,120}$/.test(s.device_id)
        ?s.device_id:null};
  }
  const used=result['gpu.vram.used_bytes'],total=result['gpu.vram.total_bytes'];
  if (used.value!==null && total.value!==null &&
      (total.value===0 || used.value>total.value || used.source!==total.source ||
       // One NVML provider can report several physical GPUs. Never pair a
       // GPU-0 used counter with GPU-1 total or with unidentified hardware.
       !used.deviceId || used.deviceId!==total.deviceId ||
       Math.abs(Date.parse(used.observedUtc)-Date.parse(total.observedUtc))>5000)) {
    used.value=total.value=null; used.stage=total.stage='INCONSISTENT_VRAM';
    used.observedUtc=total.observedUtc=null;used.deviceId=total.deviceId=null;
  }
  // This view has ONE GPU tile, not an array of independently labelled
  // adapters. A source string (NVML, WMI) is NOT a physical device ID.
  // Partial GPU values with no device ID cannot be called LIVE. If a GPU
  // reading belongs to a different adapter, quarantine the entire tile.
  const gpuKeys=['gpu.percent','gpu.temperature.c','gpu.vram.used_bytes','gpu.vram.total_bytes'];
  for (const key of gpuKeys) {
    const r=result[key];
    if (r.value!==null && !r.deviceId) {
      r.value=null; r.stage='N_D'; r.observedUtc=null;
    }
  }
  const liveGpu=gpuKeys.map(k=>result[k]).filter(r=>r.value!==null);
  if (new Set(liveGpu.map(r=>r.deviceId)).size>1) {
    for (const r of liveGpu) {
      r.value=null; r.stage='HOLD_GPU_DEVICE_CONFLICT'; r.observedUtc=null;
    }
  }
  // One GPU tile must not merge unlike providers, distant timestamps, or
  // contradictory native sample IDs just because DeviceId happens to match.
  // An absent sample_id is allowed for legacy native producers, but if ANY
  // metric has one, EVERY shown metric must carry that same identifier.
  const gpuLiveKeys=gpuKeys.filter(k=>result[k].value!==null);
  if (gpuLiveKeys.length>1) {
    const observations=gpuLiveKeys.map(k=>Date.parse(result[k].observedUtc));
    const sampleIds=gpuLiveKeys.map(k=>nativeGpuSample.get(k));
    const someSampleId=sampleIds.some(id=>id!==null);
    const sameSource=new Set(gpuLiveKeys.map(k=>result[k].source)).size===1;
    const coherentWindow=Math.max(...observations)-Math.min(...observations)<=5000;
    const coherentSample=!someSampleId ||
      sampleIds.every(id=>id!==null && id===sampleIds[0]);
    if (!sameSource || !coherentWindow || !coherentSample) {
      for (const key of gpuLiveKeys) {
        const r=result[key];
        r.value=null; r.stage='HOLD_GPU_SAMPLE_CONFLICT';
        r.observedUtc=null; r.deviceId=null;
      }
    }
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
  // Equal-weight mean would invent a project-level formula if the owner has
  // not frozen one. Accept only the E06-approved CoreID weight manifest.
  const agg=core.aggregation;
  const validWeights=agg?.method==='WEIGHTED_V1' && sha(agg.receipt_sha256) &&
    Array.isArray(agg.weights) && agg.weights.length===8 &&
    agg.weights.every(x=>x && typeof x.id==='string' &&
      core.approved_core_ids.includes(x.id) && typeof x.weight==='number' &&
      Number.isFinite(x.weight) && x.weight>0 && x.weight<=100) &&
    new Set(agg.weights.map(x=>x.id)).size===8 &&
    Math.abs(agg.weights.reduce((a,c)=>a+c.weight,0)-100)<0.000001;
  const values=new Map(outCores.map(c=>[c.id,c.percent]));
  // Eight source percentages may each be <100 yet round to 100 in aggregate.
  // Never display completion until every sealed CoreID is exactly complete.
  const helion=complete && validWeights ?
    (outCores.every(c=>c.percent===100) ? 100 : Math.min(99.99,
      round2(agg.weights.reduce((a,c)=>a+values.get(c.id)*c.weight/100,0)))):null;
  return {helion,coreIds:outCores,personas:outPersonas,
    stage:complete && validWeights?'SOURCE_DATED':'N_D'};
}

export function projectFeeds(feeds, nowMs) {
  if (!Array.isArray(feeds) || feeds.length>4096) return [];
  // Single current quotes for financial instruments only. News may contain
  // multiple articles; market duplicates must never show conflicting prices.
  // One shared license gate: invalid/blank provider attribution cannot
  // consume a trusted tile quota or invalidate an approved market quote.
  // The host/E06 verifies the receipt; a SHA-shaped string alone is not proof.
  const licenseReady=f=>f.license_status==='APPROVED' &&
    sha(f.license_receipt_sha256) && typeof f.provider==='string' &&
    f.provider.length<=120 && f.provider.trim().length>0 &&
    !/[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]/u.test(f.provider);
  const recognized=feeds.filter(f=>f && sourceIds.has(f.id));
  const licensed=recognized.filter(licenseReady);
  const disabled=recognized.filter(f=>!licenseReady(f));
  // Scan ALL licensed observations before the cap. Unlicensed submissions
  // cannot turn an otherwise valid quote into HOLD_DUPLICATE_FEED.
  // Identical native feed replays are one observation; distinct prices HOLD.
  // All source fields affect identity: license, timestamp, provider, quote.
  const snapshotIdentity=f=>JSON.stringify(Object.keys(f).sort().map(k=>[k,f[k]]));
  const uniqueLicensed=[];
  const distinctMarkets=new Map();
  for (const f of licensed) {
    if (!singletonMarketIds.has(f.id)) { uniqueLicensed.push(f); continue; }
    let signatures=distinctMarkets.get(f.id);
    if (!signatures) { signatures=new Set(); distinctMarkets.set(f.id,signatures); }
    const signature=snapshotIdentity(f);
    if (signatures.has(signature)) continue;
    signatures.add(signature);
    uniqueLicensed.push(f);
  }
  const marketCounts=new Map([...distinctMarkets].map(([id,signatures])=>[id,signatures.size]));
  const emittedMarkets=new Set();
  const licensedMarketIds=new Set(distinctMarkets.keys());
  const visible=[...uniqueLicensed,...disabled.filter(f=>
    !singletonMarketIds.has(f.id) || !licensedMarketIds.has(f.id))];
  // Show conflicting quotes before a long news list, but count only one
  // HOLD tile per instrument before applying the 16-card display limit.
  const conflicting = f => singletonMarketIds.has(f.id) && (marketCounts.get(f.id)||0)>1;
  const ordered=[...visible.filter(conflicting),
    ...visible.filter(f=>!conflicting(f) && singletonMarketIds.has(f.id)),
    ...visible.filter(f=>!conflicting(f) && !singletonMarketIds.has(f.id))];
  const conflictSeen=new Set();
  const capped=ordered.filter(f=>{
    if (!conflicting(f)) return true;
    if (conflictSeen.has(f.id)) return false;
    conflictSeen.add(f.id);
    return true;
  });
  return capped.slice(0,16).flatMap(f=>{
    if (singletonMarketIds.has(f.id) && (marketCounts.get(f.id)||0)>1) {
      if (emittedMarkets.has(f.id)) return [];
      emittedMarkets.add(f.id);
      return [{id:f.id,stage:'HOLD_DUPLICATE_FEED',sourceUtc:null,value:null,
        observedKind:'N_D'}];
    }
    const fxDate=f.id==='eur-usd'||f.id==='usd-eur';
    const observationSupplied=fxDate && f.observation_date!==undefined;
    const dateOnly=observationSupplied && observationUtc(f.observation_date);
    const sourceTime=observationSupplied ?
      (dateOnly?f.observation_date+'T00:00:00Z':null) : f.source_at_utc;
    const ttl=Number.isInteger(f.ttl_ms)&&f.ttl_ms>0&&f.ttl_ms<=86400000?f.ttl_ms:0;
    const fetched=ttl>0 && ago(f.fetched_at_utc,nowMs,ttl);
    const dated=ago(sourceTime,nowMs,maximumAges[f.id]);
    // No fetched snapshot can truthfully contain a future source observation.
    const temporalOrder=fetched && dated && Date.parse(sourceTime)<=Date.parse(f.fetched_at_utc);
    const strictlyPositive=new Set(['eur-usd','usd-eur','eur-rub','bitcoin','brent']).has(f.id);
    const numericValid=typeof f.value==='number' && Number.isFinite(f.value) &&
      (!strictlyPositive || f.value>0);
    const approved=licenseReady(f);
    const stale=['OFFLINE_CACHE','STALE_CACHE','STALE_SOURCE','OFFLINE'].includes(f.status);
    const invalidMarket = strictlyPositive && (!numericValid || f.parsed_by_owner!==true);
    const stage=!approved?'DISABLED':stale?'STALE_CACHE':
      invalidMarket?'HOLD_INVALID_MARKET_VALUE':
      temporalOrder && ['LIVE','CACHE'].includes(f.status)?'SOURCE_DATED':'N_D';
    return [{id:f.id,stage,sourceUtc:isoUtc(sourceTime)?sourceTime:null,
      value:stage==='SOURCE_DATED' && f.parsed_by_owner===true && numericValid?f.value:null,
      observedKind:dateOnly?'ECB_OBSERVATION_DATE':'SOURCE_TIMESTAMP'}];
  });
}

// The original R11 events.v3 has a strict envelope, not just an event_type.
// This view is deliberately not an event writer, journal or second bus.
const eventPackages = new Set(['P01','P02','P03','P04','P05','E06','E07']);
const eventId = value => validRunId(value) && value.length<=128;
// Canonical required counters are explicit null/null when no metric exists.
// Match native admission: a measured pair is integral, bounded and nonzero-total.
const terminalCounters = e => (e.numerator===null && e.denominator===null) ||
  (Number.isSafeInteger(e.numerator) && Number.isSafeInteger(e.denominator) &&
   e.numerator>=0 && e.denominator>0 && e.numerator<=e.denominator);
const canonicalTerminal = e => e && e.schema===EVENT_SCHEMA &&
  eventId(e.run_id) && eventId(e.event_id) && eventId(e.task_id) &&
  eventId(e.action_id) && eventPackages.has(e.package_id) && terminalCounters(e) &&
  typeof e.source==='string' && e.source.length>0 && e.source.length<=120 &&
  !/[\x00-\x1f\x7f]/.test(e.source) &&
  typeof e.message==='string' && e.message.length<=240 &&
  !/[\x00-\x1f\x7f]/.test(e.message) &&
  typeof e.evidence_verified==='boolean' &&
  ((e.event_type==='model.stopped' && e.package_id==='P04' && e.state==='STOPPED') ||
   (e.event_type==='task.failed' && e.state==='ERROR'));

export function projectCanonicalEvents(events, runId, nowMs) {
  if (!Array.isArray(events) || !validRunId(runId) || !Number.isFinite(nowMs))
    return {state:'N_D',errors:null};
  // Bounded fail-closed projection: never let a raw >64-event tail hide an
  // earlier terminal ERROR or an event_id collision. E06 owns the event log.
  if (events.length>4096) return {state:'HOLD_JOURNAL_OVERFLOW',errors:null};
  const terminal=[];
  const seen=new Map();
  // errors is the deduplicated, verified count for THIS bounded RunID journal,
  // not merely the most recent 30-second LIVE status window. An older native
  // failure must not silently turn into a false “0 errors” after it ages out.
  let runErrorCount=0;
  let observedVerifiedTerminal=false;
  for (const e of events) {
    // A same-run task.failed/model.stopped with a broken envelope is NOT a
    // harmless nonterminal. Quarantine it, or a malformed error can disappear
    // behind a later clean STOP. Foreign runs and nonterminals stay ignored.
    if (e?.run_id===runId &&
        (e.event_type==='model.stopped' || e.event_type==='task.failed' || e.state==='ERROR' ||
         (e.package_id==='P04' && e.state==='STOPPED')) &&
        !canonicalTerminal(e)) return {state:'HOLD_MALFORMED_TERMINAL',errors:null};
    // A terminal failure with a missing, impossible or non-UTC timestamp may
    // otherwise vanish behind a later verified STOP. Missing time is not
    // evidence of successful termination; quarantine rather than skip it.
    if (e?.run_id===runId && (e.event_type==='model.stopped' || e.event_type==='task.failed') &&
        !isoUtc(e.timestamp_utc)) return {state:'HOLD_MALFORMED_TERMINAL_TIMESTAMP',errors:null};
    if (!canonicalTerminal(e) || e.run_id!==runId) continue;
    // A future-dated authenticated failure must not silently disappear.
    if (Date.parse(e.timestamp_utc)>nowMs)
      return {state:'HOLD_FUTURE_TERMINAL',errors:null};
    // A schema-valid terminal with evidence_verified:false is only a report,
    // NOT proof that STOP completed or that the failure was authenticated.
    // It must not overwrite an actually verified error or STOP in this tile.
    if (e.evidence_verified!==true) return {state:'HOLD_UNVERIFIED_TERMINAL',errors:null};
    // Same event_id + DIFFERENT canonical terminal contents is a broken or
    // replayed native receipt, not an instruction to choose arrival order.
    const fingerprint=JSON.stringify([e.run_id,e.event_id,e.event_type,
      e.task_id,e.package_id,e.action_id,e.timestamp_utc,e.state,
      e.source,e.message,e.evidence_verified,e.numerator,e.denominator]);
    const previous=seen.get(e.event_id);
    if (previous!==undefined) {
      if (previous!==fingerprint) return {state:'HOLD_EVENT_ID_COLLISION',errors:null};
      continue; // Identical replay, counted once.
    }
    seen.set(e.event_id,fingerprint);
    observedVerifiedTerminal=true;
    if (e.event_type==='task.failed') runErrorCount++;
    // Only recent terminals determine the current LIVE state; older verified
    // errors remain counted as history without becoming a current error tile.
    if (ago(e.timestamp_utc,nowMs,30000)) terminal.push(e);
  }
  terminal.sort((a,b)=>Date.parse(a.timestamp_utc)-Date.parse(b.timestamp_utc) ||
    (a.state==='ERROR'?1:0)-(b.state==='ERROR'?1:0));
  // Foreign-run-only or empty telemetry cannot establish zero errors here.
  return {state:terminal.length===0?'N_D':terminal.at(-1).state,
    errors:observedVerifiedTerminal?runErrorCount:null};
}

// E06 must project the original native DTO into these same-run envelopes.
// Without a signed E06 readback, this is only a display of owner-reported data.
export function projectSpaceView(host, nowMs=Date.now()) {
  if (!host || !validRunId(host.run_id) || !Number.isFinite(nowMs)) return null;
  const hardwareFrame=host.hardware;
  // UNAVAILABLE is a native poll outcome, not permission to render values.
  // Old projection admitted a nested LIVE sensor even when its enclosing
  // same-run poll explicitly denied hardware availability. Fail closed here.
  const sameRunFrame=hardwareFrame?.run_id===host.run_id &&
    ago(hardwareFrame.polled_utc,nowMs,30000) &&
    (hardwareFrame.state==='LIVE' || hardwareFrame.state==='PARTIAL_OR_LIVE');
  const sameRunCore=host.core?.run_id===host.run_id ? host.core : null;
  // Feeds are host-owned approvals, never auto-fetched or shared across runs.
  const sameRunFeeds=Array.isArray(host.feeds) ?
    host.feeds.filter(f=>f?.run_id===host.run_id) : [];
  return Object.freeze({schema:'NOX-E05-SPACE-READONLY-v1',runId:host.run_id,
    readiness:projectReadiness(host.readiness,host.run_id,nowMs),
    hardware:projectHardware(sameRunFrame?hardwareFrame.sensors:[],nowMs,
      sameRunFrame?hardwareFrame.polled_utc:null),
    core:projectCorePersona(sameRunCore,nowMs),
    feeds:projectFeeds(sameRunFeeds,nowMs),
    events:projectCanonicalEvents(host.events,host.run_id,nowMs),
    // An administrative Drive connector receipt is not app-side OAuth.
    // This remains APP_REPORTED, NEVER externally VERIFIED. E06 must bind
    // signed native app evidence and the actual Drive response for acceptance.
    driveReadback:host.drive?.run_id===host.run_id &&
      validRunId(host.build_id) && host.drive?.build_id===host.build_id &&
      host.drive?.origin==='WEBVIEW2_APP' && host.drive?.status==='READBACK_PASS' &&
      ago(host.drive?.readback_at_utc,nowMs,300000) && sha(host.drive?.receipt_sha256)
        ?'APP_REPORTED_READBACK':'HOLD'}); // No OAuth/network performed here.
}
