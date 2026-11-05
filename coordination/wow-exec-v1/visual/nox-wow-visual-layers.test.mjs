import test from 'node:test';
import assert from 'node:assert/strict';
import {asTrustedWowEvent,mountNoxWowVisualLayers} from './nox-wow-visual-layers.mjs';
const NOW=Date.parse('2026-11-01T15:30:00Z');
const sample=(patch={})=>({schema:'NOX-INSTALLER-EVENT-v3',evidence_verified:true,event_type:'task.progress',event_id:'e1',run_id:'r1',task_id:'t1',action_id:'model.pull',package_id:'P03',event_sequence:1,receipt_sha256:'a'.repeat(64),timestamp_utc:new Date(NOW).toISOString(),numerator:3,denominator:10,...patch});
test('real signed-shape event shows native route and actual progress',()=>{const x=asTrustedWowEvent(sample(),NOW);assert.equal(x.route,'model-library');assert.equal(x.percent,30);});
test('invalid evidence, old, future, spoofed hashes and unsupported types fail closed',()=>{
 for(const x of [{evidence_verified:false},{timestamp_utc:new Date(NOW-31000).toISOString()},{timestamp_utc:new Date(NOW+6000).toISOString()},{receipt_sha256:'bad'},{event_type:'gpu.sample'},{run_id:'script()'},{numerator:11,denominator:10},{package_id:'P04'}])assert.equal(asTrustedWowEvent(sample(x),NOW),null);
});
test('RAG completion maps only to approved learning proof',()=>{
 const x=asTrustedWowEvent(sample({event_type:'task.completed',package_id:'P04',action_id:'rag.index',numerator:null,denominator:null}),NOW);
 assert.equal(x.route,'learning-proofs');assert.equal(x.percent,null);
});
test('cannot mount an extra UI without the original trusted native host',()=>{
 assert.throws(()=>mountNoxWowVisualLayers({root:{ownerDocument:{}},notificationHost:{},nativeBus:{},routePort:{}}),/NOX_EXISTING_TRUSTED_VISUAL_HOST_REQUIRED/);
});
