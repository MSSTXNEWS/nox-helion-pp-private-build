'use strict';
const assert=require('node:assert/strict'),{createHash}=require('node:crypto');
const {checkAdmittedPhysical:check,schema}=require('./b3_r83_admitted_physical.cjs');
const {check:checkR66,SCHEMA}=require('./b3_r66_raw_readback_binding.cjs');
const raw=x=>Buffer.from(JSON.stringify(x)),sha=b=>createHash('sha256').update(b).digest('hex'),h=n=>n.toString(16).padStart(64,'0');
const e={model_id:'fixture-model',route:'/fixture/model',dialog_id:'existing-fixture',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),window_start_ms:100,window_end_ms:200,process:{boot_id:'fixture',pid:42,start_ticks:123},turn_request_ids:['req2','req3']};
const makeReceipts=expected=>{
 const receipt_payloads=Array.from({length:4},(_,i)=>JSON.stringify({...expected,turn:2+Math.floor(i/2),phase:i%2?'after':'before',request_id:expected.turn_request_ids[Math.floor(i/2)],observed_ms:110+i*10,readback_id:'receipt-'+i,installed_bridge_sha256:expected.bridge_sha256,served_bridge_sha256:expected.bridge_sha256}));
 return {schema:SCHEMA,expected,receipt_payloads,receipt_index:receipt_payloads.map((s,i)=>({readback_id:'receipt-'+i,sha256:sha(Buffer.from(s))}))};
};
const receipts=makeReceipts(e),admission=raw({schema,expected:e,receipt_index:receipts.receipt_index});
const pin=sha(admission),payload=raw([{receipts},{},[]]);
const flags=['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted','production_ready'];
let cases=0;
function expect(p,a=admission,ap=pin,status='MATCHED_R83_ADMISSION_OFFLINE',pp=sha(p)){
 const z=check(p,pp,a,ap);assert.equal(z.status,status,JSON.stringify(z));
 assert.equal(z.consistent,status==='MATCHED_R83_ADMISSION_OFFLINE');
 flags.forEach(k=>assert.equal(z[k],false));cases++;
}
assert.equal(checkR66(receipts).consistent,true);
expect(payload);
for(const [key,value] of [['model_id','other-model'],['route','/other'],['weights_manifest_sha256',h(91)],['tokenizer_manifest_sha256',h(92)],['original_checkpoint_sha256',h(93)],['owner_admission_receipt_sha256',h(94)],['process',{...e.process,start_ticks:124}],['turn_request_ids',['other2','other3']],['window_end_ms',201]]){
 const altered=makeReceipts({...e,[key]:value});
 assert.equal(checkR66(altered).consistent,true,'coherent old R66 '+key);
 expect(raw([{receipts:altered},{},[]]),admission,pin,'HOLD_R83_PHYSICAL_DRIFT');
}
const changed=JSON.parse(JSON.stringify(receipts));
const first=JSON.parse(changed.receipt_payloads[0]);first.observed_ms++;
changed.receipt_payloads[0]=JSON.stringify(first);changed.receipt_index[0].sha256=sha(Buffer.from(changed.receipt_payloads[0]));
assert.equal(checkR66(changed).consistent,true);
expect(raw([{receipts:changed},{},[]]),admission,pin,'HOLD_R83_RECEIPT_DRIFT');
expect(payload,Buffer.concat([admission,Buffer.from(' ')]),pin,'HOLD_R83_DETACHED_DIGEST');
expect(payload,admission,undefined,'MATCHED_R83_ADMISSION_OFFLINE'); // default is exact pin
expect(payload,admission,'','HOLD_R83_INPUT');
expect(payload,admission,pin,'HOLD_R83_DETACHED_DIGEST',h(99));
const duplicate=Buffer.from(admission.toString().replace('{','{"schema":"shadow",'));
expect(payload,duplicate,sha(duplicate),'HOLD_R83_ENVELOPE');
console.log('B3 R83 '+cases+' cases; coherent R66 drift reproduced; independent admission/index guard holds; no authority');
