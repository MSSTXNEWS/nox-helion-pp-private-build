'use strict';
// R65: exact R64 release only; offline consistency check ONLY. No authentication, source of truth,
// owner authorization, network, model changes, or native acceptance.
// Map independently authenticated native readbacks into this proposed schema;
// never synthesize or copy expected values into observations.
const RELEASE_SHA='c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7';
const SCHEMA='NOX_B3_R65_R64_PHYSICAL_PIN_CONSISTENCY_V1';
const hex=(v,n)=>typeof v==='string'&&v.length===n&&/^[a-f0-9]+$/.test(v)&&!/^(.)\1+$/.test(v);
const hash=v=>hex(v,64);
const id=v=>typeof v==='string'&&v.length>0&&v.length<=160&&v===v.trim()&&!/[\x00-\x1f\x7f]/.test(v);
const obj=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const integer=v=>Number.isSafeInteger(v)&&v>0;
const validProcess=p=>obj(p)&&id(p.boot_id)&&integer(p.pid)&&integer(p.start_ticks);
const sameProcess=(a,b)=>a.boot_id===b.boot_id&&a.pid===b.pid&&a.start_ticks===b.start_ticks;
const pinFields=['model_id','route','weights_manifest_sha256','tokenizer_manifest_sha256'];
function physicalPins(v){
  return obj(v)&&id(v.model_id)&&id(v.route)&&hash(v.weights_manifest_sha256)&&hash(v.tokenizer_manifest_sha256);
}
function check(input){
  const fail=reason=>({schema:SCHEMA,status:'HOLD',reason,consistent:false,native_accepted:false,authentication_verified:false});
  if(!obj(input)||input.schema!==SCHEMA||!obj(input.expected)||!Array.isArray(input.observations))return fail('INPUT_SCHEMA');
  const e=input.expected, obs=input.observations;
  if(!physicalPins(e)||!validProcess(e.process)||e.bridge_sha256!==RELEASE_SHA||!id(e.dialog_id)||!hash(e.original_checkpoint_sha256)||
    !hash(e.owner_admission_receipt_sha256)||!integer(e.window_start_ms)||!integer(e.window_end_ms)||
    e.window_start_ms>=e.window_end_ms||!Array.isArray(e.turn_request_ids)||e.turn_request_ids.length!==2||
    !e.turn_request_ids.every(id)||e.turn_request_ids[0]===e.turn_request_ids[1])return fail('EXPECTED_PIN_SCHEMA');
  if(obs.length!==4)return fail('FOUR_READBACKS_REQUIRED');
  let previous=0;const receiptIds=new Set(),receiptHashes=new Set();
  for(let i=0;i<4;i++){
    const o=obs[i],turn=2+Math.floor(i/2),phase=i%2===0?'before':'after';
    if(!obj(o)||o.turn!==turn||o.phase!==phase||o.dialog_id!==e.dialog_id||
       o.request_id!==e.turn_request_ids[turn-2]||o.original_checkpoint_sha256!==e.original_checkpoint_sha256||
       o.owner_admission_receipt_sha256!==e.owner_admission_receipt_sha256)return fail('READBACK_SCOPE_'+i);
    if(!integer(o.observed_ms)||o.observed_ms<=previous||o.observed_ms<e.window_start_ms||
       o.observed_ms>e.window_end_ms)return fail('READBACK_TIME_'+i);
    previous=o.observed_ms;
    if(!id(o.readback_id)||!hash(o.readback_sha256)||receiptIds.has(o.readback_id)||receiptHashes.has(o.readback_sha256))
      return fail('READBACK_REUSE_'+i);
    receiptIds.add(o.readback_id);receiptHashes.add(o.readback_sha256);
    if(!physicalPins(o))return fail('PHYSICAL_PIN_MISSING_'+i);
    for(const k of pinFields)if(o[k]!==e[k])return fail('PIN_DRIFT_'+k+'_'+i);
    if(o.installed_bridge_sha256!==e.bridge_sha256||o.served_bridge_sha256!==e.bridge_sha256)
      return fail('BRIDGE_DRIFT_'+i);
    const p=o.process;
    if(!validProcess(p))return fail('PROCESS_PIN_MISSING_'+i);
    if(!sameProcess(p,e.process))return fail('PROCESS_DRIFT_'+i);
  }
  return {schema:SCHEMA,status:'CONSISTENT_INPUTS_ONLY',consistent:true,readbacks:4,
    native_accepted:false,authentication_verified:false,requires_external_verifier:true};
}
function selfTest(){
  // synthetic fixtures, never a production pin or an actual receipt
  const h=n=>n.toString(16).padStart(64,'0'), e={
    model_id:'fixture-model',route:'/fixture-only',process:{boot_id:'fixture-boot',pid:42,start_ticks:123},weights_manifest_sha256:h(11),
    tokenizer_manifest_sha256:h(12),bridge_sha256:RELEASE_SHA,dialog_id:'fixture-dialog',
    original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),
    window_start_ms:100,window_end_ms:200,turn_request_ids:['fixture-request-2','fixture-request-3']};
  const fixture={schema:SCHEMA,expected:e,observations:Array.from({length:4},(_,i)=>({
    ...Object.fromEntries(pinFields.map(k=>[k,e[k]])),turn:2+Math.floor(i/2),phase:i%2?'after':'before',
    dialog_id:e.dialog_id,request_id:e.turn_request_ids[Math.floor(i/2)],original_checkpoint_sha256:e.original_checkpoint_sha256,
    owner_admission_receipt_sha256:e.owner_admission_receipt_sha256,observed_ms:110+i*10,
    readback_id:'fixture-'+i,readback_sha256:h(20+i),installed_bridge_sha256:RELEASE_SHA,
    served_bridge_sha256:RELEASE_SHA,process:{boot_id:'fixture-boot',pid:42,start_ticks:123}}))};
  const cases=[
    ['valid consistency only',()=>{},true],
    ['coherently wrong observed process',x=>x.observations.forEach(o=>o.process.pid=99),false],
    ['missing independent process pin',x=>delete x.expected.process,false],
    ['wrong expected boot',x=>x.expected.process.boot_id='different',false],
    ['prior R61 bridge pin',x=>{x.expected.bridge_sha256='9cd1cd1ab96a01b295418b59d53669b742d804520af15e3da648716b02427ef3';x.observations.forEach(o=>{o.installed_bridge_sha256=o.served_bridge_sha256=x.expected.bridge_sha256;});},false],
    ['missing physical tokenizer',x=>delete x.observations[1].tokenizer_manifest_sha256,false],
    ['same label changed weights',x=>x.observations[2].weights_manifest_sha256=h(99),false],
    ['tokenizer drift',x=>x.observations[3].tokenizer_manifest_sha256=h(99),false],
    ['route drift',x=>x.observations[1].route='/different',false],
    ['model drift',x=>x.observations[2].model_id='other',false],
    ['installed bridge mismatch',x=>x.observations[0].installed_bridge_sha256=h(99),false],
    ['served bridge mismatch',x=>x.observations[3].served_bridge_sha256=h(99),false],
    ['PID reuse changed start',x=>x.observations[3].process.start_ticks++,false],
    ['boot changed',x=>x.observations[3].process.boot_id='other',false],
    ['receipt ID reuse',x=>x.observations[3].readback_id=x.observations[0].readback_id,false],
    ['receipt digest reuse',x=>x.observations[3].readback_sha256=x.observations[0].readback_sha256,false],
    ['first turn replay',x=>x.observations[0].turn=1,false],
    ['wrong dialog',x=>x.observations[2].dialog_id='other',false],
    ['wrong request',x=>x.observations[3].request_id=x.expected.turn_request_ids[0],false],
    ['original checkpoint changed',x=>x.observations[2].original_checkpoint_sha256=h(99),false],
    ['wrong owner receipt',x=>x.observations[1].owner_admission_receipt_sha256=h(99),false],
    ['missing readback',x=>x.observations.pop(),false],
    ['reordered time',x=>x.observations[1].observed_ms=100,false],
    ['outside window',x=>x.observations[3].observed_ms=201,false],
    ['wrong release pin',x=>x.expected.bridge_sha256=h(99),false],
    ['missing expected owner receipt',x=>delete x.expected.owner_admission_receipt_sha256,false],
    ['invalid dummy hash',x=>x.expected.weights_manifest_sha256='0'.repeat(64),false]
  ];
  return cases.map(([name,mutate,want])=>{
    const x=JSON.parse(JSON.stringify(fixture));mutate(x);const result=check(x);
    if(result.consistent!==want||result.native_accepted!==false||result.authentication_verified!==false)
      throw Error(name+': '+JSON.stringify(result));
    return {name,status:result.status,reason:result.reason||null};
  });
}
module.exports={check,selfTest,SCHEMA,RELEASE_SHA};
if(typeof require==='function'&&require.main===module){
  if(process.argv.includes('--self-test'))console.log(JSON.stringify({cases:selfTest(),native_accepted:false},null,2));
  else {const result=check(JSON.parse(require('node:fs').readFileSync(0,'utf8')));
    console.log(JSON.stringify(result,null,2));if(!result.consistent)process.exitCode=2;}
}
