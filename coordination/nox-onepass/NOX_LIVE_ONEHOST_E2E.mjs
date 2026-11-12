#!/usr/bin/env node
/** Read-only by default; one controlled chat write only when explicitly enabled.
 * NEVER calls /api/nox/stop: that is a shared-scope STOP and must be tested in
 * an exclusive, isolated, owner-authorized physical QA session.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const base = new URL(process.env.NOX_ONEHOST_URL || 'http://127.0.0.1:18775/');
if (!['127.0.0.1','localhost','[::1]'].includes(base.hostname) || !['http:','https:'].includes(base.protocol)) {
  throw new Error('ONEHOST_MUST_BE_LOCAL_TO_AVOID_PRIVATE_INFORMATION_LEAKS');
}
const out = path.resolve(process.env.NOX_LIVE_OUT || './runtime/onehost-proof.json');
fs.mkdirSync(path.dirname(out), {recursive:true});
const stamp=()=>new Date().toISOString();
const report={schema:'NOX_LIVE_ONEHOST_QA_1',at:stamp(),origin:base.origin,reads:{},checks:{},
  chat:{state:'NOT_TESTED'},stop:{state:'HOLD_SHARED_SCOPE_NEEDS_ISOLATED_TEST'},
  s03:{state:'NOT_TESTED'}, acceptance:'HOLD'};
const save=()=>{let tmp=out+'.tmp-'+process.pid;fs.writeFileSync(tmp,JSON.stringify(report,null,2));fs.renameSync(tmp,out);};
async function read(p,ms=9000){
  try{
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),ms);
    try{
      const response=await fetch(new URL(p,base),{method:'GET',redirect:'manual',headers:{Accept:'application/json'},signal:ctrl.signal});
      if(!response.ok)throw Error('HTTP_'+response.status);
      if(!(response.headers.get('content-type')||'').includes('json'))throw Error('EXPECTED_JSON_NOT_LOGIN_PAGE');
      return {ok:true,data:await response.json()};
    }finally{clearTimeout(timer)}
  }catch(e){return {ok:false,reason:String(e.message||e).slice(0,160)}}
}
const paths={owner:'/api/nox/status',trainer:'/api/nox/training/status',progress:'/api/nox/progress',
  s03:'/api/ui/memory/dialogs/status',voice:'/api/nox/voice/status',activity:'/api/nox/activity'};
const raw={};
for(const [kind,p] of Object.entries(paths)){
 const r=await read(p);raw[kind]=r.ok?r.data:null;report.reads[kind]=r.ok?'HTTP_JSON_OK':r.reason;
}
const owner=raw.owner||{},trainer=raw.trainer||{},proof=raw.progress||{},s03=raw.s03||{};
report.checks.ownerBound=owner.backend==='EXISTING_NATIVE_ONEHOST'&&owner.native_p02_bound===true&&
 owner.native_contract?.transport_bound===true&&/^nox(?:[-_:]|$)/i.test(String(owner.primary_model||''));
report.checks.model=report.checks.ownerBound?owner.primary_model:'UNVERIFIED';
report.checks.trainingCoordinator=trainer.managed_coordinator_bound===true&&trainer.nox_training_identity_verified===true;
report.checks.trainingObserved=trainer.gpu_admission?.lock_held===true&&trainer.gpu_admission?.activity==='TRAINING'&&String(trainer.status).toLowerCase()==='running';
report.checks.weightsShaVerified=proof.schema==='nox-progress-receipt-v1'&&proof.operation==='FULL_WEIGHT_DISTILLATION'&&
 proof.model==='NOX'&&proof.weightUpdateVerified===true&&proof.attestation==='LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED'&&
 /^[a-f\d]{64}$/i.test(String(proof.studentWeightsSha256||''))&&Number.isSafeInteger(proof.completedSteps)&&
 Number.isSafeInteger(proof.targetSteps)&&proof.targetSteps>0&&proof.completedSteps<=proof.targetSteps&&
 ['VERIFIED_CHECKPOINT_STEPS','VERIFIED_COMPLETE'].includes(proof.status);
report.checks.weightsComplete=report.checks.weightsShaVerified&&proof.complete===true&&proof.status==='VERIFIED_COMPLETE';
report.checks.windowsSynced=report.checks.weightsShaVerified&&proof.windowsSyncVerified===true;
report.checks.qualityVerified=report.checks.weightsShaVerified&&proof.qualityGainVerified===true;
report.checks.s03DialogsBound=s03.persistent_threads===true&&s03.status==='READY';
report.checks.voiceRuEs=raw.voice?.models?.ru?.weights_verified===true&&raw.voice?.models?.es?.weights_verified===true;
report.checks.studentShaPrefix=report.checks.weightsShaVerified?String(proof.studentWeightsSha256).slice(0,16):null;
report.checks.completedSteps=report.checks.weightsShaVerified?proof.completedSteps:null;
report.s03.state=report.checks.s03DialogsBound?'READ_ONLY_BOUND_NOT_RESTART_TESTED':'HOLD_NO_LIVE_DIALOG_DATABASE';
save();

// A fresh chat writes to native S03. Never replay a potentially committed
// request after a crash: precommit an intent and leave reconciliation to owner.
const enableWrite=process.env.NOX_ALLOW_TEST_CHAT==='1';
const intent=path.join(path.dirname(out),'native-chat-write-intent.json');
const reply=path.join(path.dirname(out),'native-chat-write-receipt.json');
if(enableWrite&&report.checks.ownerBound&&report.checks.s03DialogsBound){
 if(fs.existsSync(reply)){
  const prev=JSON.parse(fs.readFileSync(reply,'utf8'));
  report.chat={state:prev.acceptance==='PASS'?'PASS':'HOLD_PRIOR_TEST_UNVERIFIED',nonce:prev.nonce||null};
 }else if(fs.existsSync(intent))report.chat={state:'HOLD_UNCERTAIN_PRIOR_POST_DO_NOT_REPLAY'};
 else {
  const nonce=crypto.randomUUID(),prompt='NOX E2E '+nonce+': ответь коротко, только слово NOX.';
  const attempt={nonce,at:stamp(),path:'/api/nox/chat/stream',replayAllowed:false};
  fs.writeFileSync(intent,JSON.stringify(attempt,null,2));
  try {
   const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),120000);
   let text='',frameCount=0,done=null,model=null;
   try{
    const response=await fetch(new URL('/api/nox/chat/stream',base),{
     method:'POST',redirect:'manual',headers:{'Content-Type':'application/json','Accept':'application/x-ndjson'},
     body:JSON.stringify({message:prompt,task:'general',history:[]}),signal:ctrl.signal});
    if(!response.ok||!response.body)throw Error('STREAM_HTTP_'+response.status);
    let buffer='';
    for await(const bytes of response.body){
     buffer+=new TextDecoder().decode(bytes);if(buffer.length>300000)throw Error('STREAM_OVERSIZE');
     let pos;while((pos=buffer.indexOf('\n'))>=0){
      const l=buffer.slice(0,pos).trim();buffer=buffer.slice(pos+1);if(!l)continue;
      const frame=JSON.parse(l);frameCount++;
      if(frame.type==='error')throw Error('NATIVE_ERROR');
      if(frame.type==='start')model=frame.model||null;
      if(frame.type==='delta')text+=String(frame.text||'');
      if(frame.type==='done'){done=frame;break}
     }
     if(done)break;
    }
   }finally{clearTimeout(timer)}
   const valid=!!text.trim()&&!!done&&done.saved===true&&done.s03_integrated===true&&
    (!model||/^nox(?:[-_:]|$)/i.test(model));
   const evidence={schema:'NOX_NATIVE_CHAT_QA_1',at:stamp(),nonce,frames:frameCount,
     replyBytes:Buffer.byteLength(text),nativeCommit:done?.saved===true,s03Integrated:done?.s03_integrated===true,
     exchangeId:done?.exchange_id||null,acceptance:valid?'PASS':'HOLD'};
   fs.writeFileSync(reply,JSON.stringify(evidence,null,2));
   report.chat={state:evidence.acceptance,nonce,frames:frameCount};
   if(valid)report.s03.state='NATIVE_STREAM_COMMIT_CONFIRMED_RESTART_UNTESTED';
  }catch(e){report.chat={state:'HOLD_STREAM_OUTCOME_UNCERTAIN_NO_REPLAY',reason:String(e.message||e).slice(0,160)}}
 }
}else if(!enableWrite)report.chat={state:'HOLD_TEST_CHAT_NOT_AUTHORIZED',hint:'Set NOX_ALLOW_TEST_CHAT=1 only on a test-owned native session'};

report.acceptance=report.checks.ownerBound&&report.checks.weightsShaVerified&&report.chat.state==='PASS'?'PARTIAL_LIVE_PROOF':'HOLD';
report.at=stamp();save();
console.log(JSON.stringify({schema:report.schema,acceptance:report.acceptance,reads:report.reads,checks:report.checks,chat:report.chat.state,stop:report.stop.state}));
// Return 2 for HOLD, never an invented success. Does not expose raw API payloads.
if(report.acceptance==='HOLD')process.exitCode=2;