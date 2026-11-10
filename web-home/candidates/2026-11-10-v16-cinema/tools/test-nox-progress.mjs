/* Deterministic policy tests — synthetic fixtures are NOT actual NOX progress evidence. */
import assert from 'node:assert/strict';
import {assessNoxProgress} from '../nox-progress-core.mjs';
const sha=n=>String(n).repeat(64);
assert.equal(assessNoxProgress(null).stepPercent,null);
assert.equal(assessNoxProgress({gpuUtil:100}).status,'HOLD');
const fixture={schema:'nox-distillation-evidence-v1',model:'NOX',
 operation:'FULL_WEIGHT_DISTILLATION',completedSteps:5,targetSteps:10,
 baselineCombinedSha256:sha('a'),
 weights:{kind:'FULL_STUDENT_WEIGHTS',combinedSha256:sha('b'),files:[{sha256:sha('c'),bytes:300_000_000,verified:true}]},
 teachers:[],quality:{verified:false},windowsSync:{verified:false}};
const r=assessNoxProgress(fixture);
assert.equal(r.status,'VERIFIED_CHECKPOINT_STEPS');
assert.equal(r.stepPercent,50);
assert.equal(r.complete,false);
assert.equal(r.qualityGainVerified,false);
assert.equal(r.windowsSyncVerified,false);
assert.equal(assessNoxProgress({...fixture,completedSteps:11}).status,'HOLD');
assert.equal(assessNoxProgress({...fixture,baselineCombinedSha256:sha('b')}).status,'HOLD');
assert.equal(assessNoxProgress({...fixture,weights:{...fixture.weights,kind:'ADAPTER'}}).status,'HOLD');
assert.equal(assessNoxProgress({...fixture,weights:{...fixture.weights,files:[{sha256:'bad',verified:true,bytes:1}]}}).status,'HOLD');
const done=assessNoxProgress({...fixture,completedSteps:10,
 quality:{verified:true,baseline:0.21,student:0.25,evalDatasetSha256:sha('d')},
 windowsSync:{verified:true,combinedSha256:sha('b')},
 teachers:[1,2,3].map(n=>({name:'TEST-'+n,sourceSha256:sha(String(n)),samplesVerified:true}))});
assert.equal(done.status,'VERIFIED_COMPLETE');
assert.equal(done.complete,true);
console.log('NOX_PROGRESS_POLICY_TEST_PASS: synthetic fixtures only; actual RunPod weights NOT verified.');
