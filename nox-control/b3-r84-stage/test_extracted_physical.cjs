'use strict';
const a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const {stagePhysical}=require('./stage_physical.cjs');
const root=fs.realpathSync(process.argv[2]),sha=b=>createHash('sha256').update(b).digest('hex'),raw=x=>Buffer.from(JSON.stringify(x)),h=n=>n.toString(16).padStart(64,'0');
const snapshot=()=>Object.fromEntries(fs.readdirSync(root,{recursive:true,withFileTypes:true}).filter(x=>x.isFile()).map(x=>{const p=path.join(x.parentPath||x.path,x.name);return [path.relative(root,p),sha(fs.readFileSync(p))];}));
const before=snapshot();
for(const name of ['bridge/b3_r64_eof_candidate.js','inputs/b3.json']){
 const f=path.join(root,'nox-control/d3-r111',name),b=fs.readFileSync(f);
 try{fs.writeFileSync(f,Buffer.concat([b,Buffer.from('x')]));a.throws(()=>stagePhysical(root),/HOLD_B3_STAGE_PIN/);}
 finally{fs.writeFileSync(f,b);}
 a.deepEqual(snapshot(),before);
}
const staged=stagePhysical(root),after=snapshot();
a.equal(Object.keys(after).length,Object.keys(before).length+1);
for(const [p,v] of Object.entries(before))a.equal(after[p],v,p);
a.throws(()=>stagePhysical(root),/HOLD_B3_STAGE_OVERWRITE/);
a.deepEqual(snapshot(),after);
a.equal(require.resolve(staged.consumer),path.join(root,'nox-control/d3-r114/admitted_physical.cjs'));
const {checkAdmittedPhysical:check,schema}=require(staged.consumer);
const e={model_id:'fixture-model',route:'/fixture/model',dialog_id:'existing-fixture',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),window_start_ms:100,window_end_ms:200,process:{boot_id:'fixture',pid:42,start_ticks:123},turn_request_ids:['req2','req3']};
const receipt_payloads=Array.from({length:4},(_,i)=>JSON.stringify({...e,turn:2+Math.floor(i/2),phase:i%2?'after':'before',request_id:e.turn_request_ids[Math.floor(i/2)],observed_ms:110+i*10,readback_id:'receipt-'+i,installed_bridge_sha256:e.bridge_sha256,served_bridge_sha256:e.bridge_sha256}));
const receipt_index=receipt_payloads.map((s,i)=>({readback_id:'receipt-'+i,sha256:sha(s)}));
const receipts={schema:'NOX_B3_R66_READBACK_BYTES_V1',expected:e,receipt_payloads,receipt_index};
const admitted=raw({schema,expected:e,receipt_index}),payload=raw([{receipts},{},[]]);
const z=check(payload,sha(payload),admitted,sha(admitted));
a.equal(z.status,'MATCHED_R83_ADMISSION_OFFLINE');
for(const k of ['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted','production_ready']){a.equal(z[k],false);a.equal(staged[k],false);}
const bad=raw([{receipts:{...receipts,expected:{...e,tokenizer_manifest_sha256:h(99)}}},{},[]]);
a.equal(check(bad,sha(bad),admitted,sha(admitted)).status,'HOLD_R83_PHYSICAL_DRIFT');
a.equal(check(payload,sha(payload),null,null).status,'HOLD_R83_INPUT');
console.log(JSON.stringify({base_unchanged:Object.keys(before).length,added:1,consumer_blob:staged.git_blob,consumer_sha256:staged.sha256,matched:z.status,tokenizer_drift:'HOLD',missing_envelope:'HOLD',tampered_bridge_and_role:'HOLD',overwrite:'HOLD',native_accepted:false}));
