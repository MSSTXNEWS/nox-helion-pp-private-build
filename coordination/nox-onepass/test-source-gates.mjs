// Source- and network-contract tests. Synthetic local HTTP is NEVER proof of live NOX.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {spawn,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const dir=path.dirname(fileURLToPath(import.meta.url));
const checker=path.join(dir,'NOX_LIVE_ONEHOST_E2E.mjs');
const runner=path.join(dir,'NOX_ONEPASS.mjs');
const run=(url,out)=>new Promise((resolve,reject)=>{
 const p=spawn(process.execPath,[checker],{env:{...process.env,NOX_ONEHOST_URL:url,NOX_LIVE_OUT:out,NOX_ALLOW_TEST_CHAT:'0'},stdio:['ignore','pipe','pipe']});
 let err='';p.stderr.on('data',v=>err+=v);p.on('error',reject);p.on('close',code=>resolve({code,err}));
});
test('JavaScript source syntax is valid',()=>{
 for(const script of [runner,checker]){
  const r=spawnSync(process.execPath,['--check',script],{encoding:'utf8'});
  assert.equal(r.status,0,r.stderr);
 }
});
test('non-loopback OneHost target is blocked before any network read',async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'nox-external-'));
 try{const f=path.join(folder,'out.json'),r=await run('https://example.invalid/',f);
  assert.notEqual(r.code,0);assert.match(r.err,/ONEHOST_MUST_BE_LOCAL/);assert.equal(fs.existsSync(f),false);
 }finally{fs.rmSync(folder,{recursive:true,force:true})}
});
test('six read-only failures are HOLD, never a fictional PASS',async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'nox-hold-'));
 let reads=0,writes=0;const server=http.createServer((req,res)=>{
  req.method==='GET'?reads++:writes++;
  res.writeHead(404,{'Content-Type':'application/json'});res.end('{"error":"NOT_CONNECTED"}');
 });await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
 try{
  const out=path.join(folder,'out.json'),r=await run('http://127.0.0.1:'+server.address().port+'/',out);
  const report=JSON.parse(fs.readFileSync(out,'utf8'));
  assert.equal(r.code,2);assert.equal(reads,6);assert.equal(writes,0);
  assert.equal(report.acceptance,'HOLD');assert.equal(report.checks.ownerBound,false);
  assert.match(report.stop.state,/HOLD/);
 }finally{await new Promise(ok=>server.close(ok));fs.rmSync(folder,{recursive:true,force:true})}
});
test('source requires independent screenshot and native STOP/S03 receipts',()=>{
 const s=fs.readFileSync(runner,'utf8');
 for(const key of ['validateChromiumReport','validatePhysicalEvidence','NOX_ISOLATED_NATIVE_PROOF_V1',
  'facts.voiceRuEs&&facts.trainingCoordinator','owner.siteFingerprint===state.fingerprint']){
  assert.ok(s.includes(key),'Missing source gate: '+key);
 }
});
