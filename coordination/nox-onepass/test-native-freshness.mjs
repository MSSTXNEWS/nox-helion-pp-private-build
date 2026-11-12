// Mock HTTP in this file is deliberately a NEGATIVE test fixture, not a real OneHost.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const dir=path.dirname(fileURLToPath(import.meta.url));
const head='b55e9979765ea35449a99f7dc54917cfedcd65bb';
const fp='e'.repeat(64),weights='a'.repeat(64);
const api=url=>{
 if(url==='/api/nox/status')return {backend:'EXISTING_NATIVE_ONEHOST',native_p02_bound:true,native_contract:{transport_bound:true},primary_model:'nox-test'};
 if(url==='/api/nox/training/status')return {managed_coordinator_bound:true,nox_training_identity_verified:true,status:'running',gpu_admission:{lock_held:true,activity:'TRAINING'}};
 if(url==='/api/nox/progress')return {schema:'nox-progress-receipt-v1',operation:'FULL_WEIGHT_DISTILLATION',model:'NOX',weightUpdateVerified:true,attestation:'LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED',studentWeightsSha256:weights,completedSteps:10,targetSteps:10,status:'VERIFIED_COMPLETE',complete:true,windowsSyncVerified:true,qualityGainVerified:true};
 if(url==='/api/ui/memory/dialogs/status')return {persistent_threads:true,status:'READY'};
 if(url==='/api/nox/voice/status')return {models:{ru:{weights_verified:true},es:{weights_verified:true}}};
 return {status:'READY'};
};
const exec=env=>new Promise((resolve,reject)=>{
 const p=spawn(process.execPath,[path.join(dir,'NOX_LIVE_ONEHOST_E2E.mjs')],{env:{...process.env,...env},stdio:'ignore'});
 p.on('error',reject);p.on('close',code=>resolve(code));
});
test('stale NOX chat receipt cannot claim fresh native completion',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'nox-native-qa-'));
 let gets=0,posts=0;
 const server=http.createServer((req,res)=>{req.method==='GET'?gets++:posts++;
 res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(api(req.url)));});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 try{
  const old={schema:'NOX_NATIVE_CHAT_QA_1',sourceHead:'0'.repeat(40),siteFingerprint:fp,
    modelIdentity:'nox-test',studentWeightsSha256:weights,nonce:'old',
    at:new Date().toISOString(),acceptance:'PASS'};
  fs.writeFileSync(path.join(tmp,'native-chat-write-receipt.json'),JSON.stringify(old));
  const out=path.join(tmp,'result.json');
  const code=await exec({NOX_ONEHOST_URL:'http://127.0.0.1:'+server.address().port+'/',
    NOX_LIVE_OUT:out,NOX_ALLOW_TEST_CHAT:'1',
    NOX_EXPECTED_SOURCE_SHA:head,NOX_EXPECTED_SITE_FINGERPRINT:fp});
  const report=JSON.parse(fs.readFileSync(out,'utf8'));
  assert.equal(code,2);assert.equal(posts,0);assert.equal(gets,6);
  assert.equal(report.acceptance,'HOLD');assert.equal(report.chat.state,'HOLD_PRIOR_TEST_STALE_OR_UNVERIFIED');
  assert.equal(report.sourceHead,head);assert.equal(report.siteFingerprint,fp);
 }finally{await new Promise(resolve=>server.close(resolve));fs.rmSync(tmp,{recursive:true,force:true})}
});
test('prior training weights or expired chat timestamps never reuse native PASS',async()=>{
 const runner=fs.readFileSync(path.join(dir,'NOX_ONEPASS.mjs'),'utf8');
 for(const marker of ['p.sourceHead===PIN.sourceHead','p.siteFingerprint===state.fingerprint',
   'p.origin===nativeOrigin','Date.parse(p.at)>=attemptStart-5000','liveProofFresh:fresh'])
  assert.ok(runner.includes(marker),'Missing native receipt freshness proof: '+marker);
 const helper=fs.readFileSync(path.join(dir,'NOX_LIVE_ONEHOST_E2E.mjs'),'utf8');
 for(const marker of ['prev.studentWeightsSha256===proof.studentWeightsSha256','isRecent(prev.at,24*3600000)'])
  assert.ok(helper.includes(marker),'Missing native chat replay prevention: '+marker);
});
