'use strict';
// R66: offline normalized receipt byte binding, NOT native authentication.
// Input index must come from an independent authenticated verifier; this module cannot establish that.
const {createHash}=require('node:crypto');
const r65=require('./b3_r65_r64_physical_pin_check.cjs');
const SCHEMA='NOX_B3_R66_READBACK_BYTES_V1';
const sha=s=>createHash('sha256').update(s,'utf8').digest('hex');
const hash=s=>typeof s==='string'&&/^[0-9a-f]{64}$/.test(s);
function check(input){
  const fail=reason=>({schema:SCHEMA,status:'HOLD',reason,consistent:false,native_accepted:false,authentication_verified:false});
  if(!input||input.schema!==SCHEMA||!Array.isArray(input.receipt_index)||!Array.isArray(input.receipt_payloads)||
     input.receipt_index.length!==4||input.receipt_payloads.length!==4)return fail('FOUR_RECEIPTS_REQUIRED');
  const observations=[], ids=new Set(), digests=new Set();
  for(let i=0;i<4;i++){
    const pin=input.receipt_index[i],raw=input.receipt_payloads[i];
    if(!pin||typeof pin.readback_id!=='string'||!hash(pin.sha256)||typeof raw!=='string'||raw.length>65536||
       ids.has(pin.readback_id)||digests.has(pin.sha256))return fail('INDEX_OR_SIZE_'+i);
    if(sha(raw)!==pin.sha256)return fail('RAW_DIGEST_MISMATCH_'+i);
    let parsed;
    try{parsed=JSON.parse(raw);}catch{return fail('RAW_JSON_'+i);}
    // Proposed compact normalized JSON payload, not arbitrary native wire JSON.
    // Roundtrip rejects duplicate keys, noncanonical encodings and extra trailing text.
    if(!parsed||typeof parsed!=='object'||Array.isArray(parsed)||JSON.stringify(parsed)!==raw||
       Object.prototype.hasOwnProperty.call(parsed,'readback_sha256')||
       parsed.readback_id!==pin.readback_id)return fail('RAW_SCOPE_OR_ENCODING_'+i);
    ids.add(pin.readback_id);digests.add(pin.sha256);
    observations.push({...parsed,readback_sha256:pin.sha256});
  }
  const result=r65.check({schema:r65.SCHEMA,expected:input.expected,observations});
  if(!result.consistent)return fail('R65_'+result.reason);
  return {schema:SCHEMA,status:'CONSISTENT_BYTES_ONLY',consistent:true,readbacks:4,
    native_accepted:false,authentication_verified:false,requires_external_verifier:true};
}
function selfTest(){
  const h=n=>n.toString(16).padStart(64,'0');
  const process={boot_id:'fixture',pid:42,start_ticks:123};
  const e={model_id:'fixture-model',route:'/fixture',process,weights_manifest_sha256:h(11),
    tokenizer_manifest_sha256:h(12),bridge_sha256:r65.RELEASE_SHA,dialog_id:'fixture-dialog',
    original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),
    window_start_ms:100,window_end_ms:200,turn_request_ids:['req2','req3']};
  const payloads=Array.from({length:4},(_,i)=>JSON.stringify({
    model_id:e.model_id,route:e.route,process,weights_manifest_sha256:e.weights_manifest_sha256,
    tokenizer_manifest_sha256:e.tokenizer_manifest_sha256,turn:2+Math.floor(i/2),phase:i%2?'after':'before',
    dialog_id:e.dialog_id,request_id:e.turn_request_ids[Math.floor(i/2)],
    original_checkpoint_sha256:e.original_checkpoint_sha256,owner_admission_receipt_sha256:e.owner_admission_receipt_sha256,
    observed_ms:110+i*10,readback_id:'readback-'+i,installed_bridge_sha256:e.bridge_sha256,served_bridge_sha256:e.bridge_sha256}));
  const fixture={schema:SCHEMA,expected:e,receipt_payloads:payloads,receipt_index:payloads.map((s,i)=>({readback_id:'readback-'+i,sha256:sha(s)}))};
  const repin=(x,i,s)=>{x.receipt_payloads[i]=s;x.receipt_index[i].sha256=sha(s);};
  const change=(x,i,fn)=>{const p=JSON.parse(x.receipt_payloads[i]);fn(p);repin(x,i,JSON.stringify(p));};
  const cases=[
    ['valid',()=>{},true],
    ['changed payload',x=>x.receipt_payloads[0]+=' ',false],
    ['wrong digest',x=>x.receipt_index[1].sha256=h(99),false],
    ['duplicate receipt',x=>{x.receipt_index[3]=x.receipt_index[0];x.receipt_payloads[3]=x.receipt_payloads[0];},false],
    ['wrong index id',x=>x.receipt_index[2].readback_id='wrong',false],
    ['reordered payloads',x=>{[x.receipt_payloads[0],x.receipt_payloads[1]]=[x.receipt_payloads[1],x.receipt_payloads[0]];},false],
    ['duplicate JSON key',x=>repin(x,0,x.receipt_payloads[0].replace('{','{"turn":1,')),false],
    ['embedded self digest',x=>change(x,1,p=>p.readback_sha256=h(99)),false],
    ['malformed JSON',x=>repin(x,1,'{'),false],
    ['repinned wrong tokenizer',x=>change(x,2,p=>p.tokenizer_manifest_sha256=h(99)),false],
    ['repinned wrong turn',x=>change(x,0,p=>p.turn=1),false],
    ['missing receipt',x=>x.receipt_payloads.pop(),false],
    ['oversized payload',x=>repin(x,0,'x'.repeat(65537)),false],
    ['repinned wrong route',x=>change(x,3,p=>p.route='/wrong'),false],
    ['repinned wrong process',x=>change(x,3,p=>p.process.pid++),false]
  ];
  return cases.map(([name,mutate,want])=>{const x=JSON.parse(JSON.stringify(fixture));mutate(x);const r=check(x);
    if(r.consistent!==want||r.native_accepted!==false||r.authentication_verified!==false)throw Error(name+': '+JSON.stringify(r));
    return {name,status:r.status,reason:r.reason||null};});
}
module.exports={check,selfTest,SCHEMA};
if(require.main===module){
  if(process.argv.includes('--self-test'))console.log(JSON.stringify({cases:selfTest(),native_accepted:false},null,2));
  else {const r=check(JSON.parse(require('node:fs').readFileSync(0,'utf8')));console.log(JSON.stringify(r,null,2));if(!r.consistent)process.exitCode=2;}
}
