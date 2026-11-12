/* Policy-level synthetic fixtures: never a claim about real NOX training. */
import assert from 'node:assert/strict';
import {assessChatTraining} from '../nox-chat-training-v23.mjs';
const sha='a'.repeat(64);
const owner={backend:'EXISTING_NATIVE_ONEHOST',native_p02_bound:true,native_contract:{transport_bound:true},primary_model:'nox-prime:latest'};
const trainer={managed_coordinator_bound:true,nox_training_identity_verified:true,receipt_age_seconds:2,status:'running',
 gpu_admission:{lock_held:true,activity:'TRAINING'},controller_receipt:{actual_steps:16,requested_steps:64}};
const proof={schema:'nox-progress-receipt-v1',operation:'FULL_WEIGHT_DISTILLATION',model:'NOX',
 attestation:'LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED',status:'VERIFIED_CHECKPOINT_STEPS',
 weightUpdateVerified:true,studentWeightsSha256:sha,completedSteps:16,targetSteps:64,stepPercent:25,
 windowsSyncVerified:false,qualityGainVerified:false};
assert.equal(assessChatTraining().status,'HOLD_ONEHOST_NOT_BOUND');
assert.equal(assessChatTraining().checkpointPercent,null);
assert.equal(assessChatTraining({...owner,primary_model:'qwen3-8b'},trainer,proof).ownerReady,false);
const live=assessChatTraining(owner,trainer,{});
assert.equal(live.ownerReady,true);
assert.equal(live.live,true);
assert.equal(live.checkpointVerified,false);
assert.equal(live.checkpointPercent,null);
assert.equal(live.status,'LIVE_TRAINER_UNVERIFIED_WEIGHTS');
assert.equal(assessChatTraining(owner,{...trainer,receipt_age_seconds:60},{}).live,false);
assert.equal(assessChatTraining(owner,{...trainer,nox_training_identity_verified:false},{}).coordinatorVerified,false);
const realShape=assessChatTraining(owner,trainer,proof);
assert.equal(realShape.checkpointVerified,true);
assert.equal(realShape.checkpointPercent,25);
assert.equal(realShape.windowsVerified,false);
assert.equal(realShape.qualityVerified,false);
assert.equal(assessChatTraining(owner,trainer,{...proof,studentWeightsSha256:'invalid'}).checkpointVerified,false);
assert.equal(assessChatTraining(owner,trainer,{...proof,stepPercent:75}).checkpointVerified,false);
assert.equal(assessChatTraining(owner,trainer,{...proof,operation:'RAG_ONLY'}).checkpointVerified,false);
console.log('NOX_CHAT_TRAINING_POLICY_PASS: 12 synthetic assertions; NO real model or GPU proof claimed.');
