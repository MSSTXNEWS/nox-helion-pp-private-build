#!/usr/bin/env node
/* NOX read-only progress verifier: process actual full student weight bytes, not GPU utilisation.
   Usage: node tools/nox-audit-distillation.mjs --workspace /workspace/NOX --manifest /workspace/NOX/distillation-evidence.json --out /workspace/NOX/nox-progress-receipt.json
   This script never modifies model weights, Pod state, trainer, checkpoints or environment.
*/
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {assessNoxProgress} from '../nox-progress-core.mjs';
const option = name => {const i=process.argv.indexOf(name);return i<0?null:process.argv[i+1]};
const workspace=path.resolve(option('--workspace')||'/workspace/NOX');
const manifestPath=path.resolve(option('--manifest')||path.join(workspace,'distillation-evidence.json'));
const outPath=path.resolve(option('--out')||path.join(workspace,'nox-progress-receipt.json'));
const hashBuffer=async filename=>new Promise((resolve,reject)=>{const hash=crypto.createHash('sha256');const stream=fs.createReadStream(filename,{highWaterMark:4*1024*1024});
 stream.on('data',chunk=>hash.update(chunk));stream.once('error',reject);stream.once('end',()=>resolve(hash.digest('hex')))});
const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/i.test(v);
function inside(root,p){const rel=path.relative(root,p);return !!rel&&!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel)}
async function verifySet(items,kind){
 if(!Array.isArray(items)||!items.length)throw Error(kind+'_FILES_MISSING');
 const found=[];let total=0;
 for(const item of items){
  if(!item||typeof item.path!=='string'||path.isAbsolute(item.path)||item.path.includes('..')||!hex(item.sha256))throw Error(kind+'_UNSAFE_MANIFEST_PATH');
  if(/adapter_model|\.lora\b|peft/i.test(item.path))throw Error('ADAPTER_WEIGHTS_NOT_ALLOWED');
  const abs=path.resolve(workspace,item.path);
  if(!inside(workspace,abs))throw Error(kind+'_PATH_OUTSIDE_WORKSPACE');
  const real=await fsp.realpath(abs);
  if(!inside(await fsp.realpath(workspace),real))throw Error('SYMLINK_ESCAPE');
  const stat=await fsp.stat(real);
  if(!stat.isFile()||stat.size<1024)throw Error(kind+'_WEIGHT_FILE_INVALID');
  const actual=await hashBuffer(real);if(actual.toLowerCase()!==item.sha256.toLowerCase())throw Error(kind+'_SHA256_MISMATCH:'+item.path);
  found.push({path:item.path,bytes:stat.size,sha256:actual,verified:true});total+=stat.size;
 }
 // Sharded full-weight sets must be large enough to exclude tiny prompt/adapter files.
 if(kind==='STUDENT'&&total<100_000_000)throw Error('STUDENT_FULL_WEIGHTS_BELOW_MINIMUM_BYTES');
 const combinedSha256=crypto.createHash('sha256').update(found.slice().sort((a,b)=>a.path.localeCompare(b.path))
  .map(x=>x.sha256+':'+x.bytes+':'+x.path).join('\n')).digest('hex');
 return {files:found,combinedSha256,totalBytes:total};
}
async function main(){
 let result;
 try{
  if(!inside(workspace,manifestPath))throw Error('MANIFEST_OUTSIDE_WORKSPACE');
  const input=JSON.parse(await fsp.readFile(manifestPath,'utf8'));
  if(input.schema!=='nox-distillation-evidence-v1'||input.model!=='NOX'||input.operation!=='FULL_WEIGHT_DISTILLATION')throw Error('NON_NOX_DISTILLATION_MANIFEST');
  const baseline=await verifySet(input.baseline?.files,'BASELINE');
  const weights=await verifySet(input.weights?.files,'STUDENT');
  if(input.baselineCombinedSha256&&input.baselineCombinedSha256!==baseline.combinedSha256)throw Error('BASELINE_COMBINED_DIGEST_DRIFT');
  if(input.weights?.combinedSha256&&input.weights.combinedSha256!==weights.combinedSha256)throw Error('STUDENT_COMBINED_DIGEST_DRIFT');
  // This proof only attests on-disk checkpoints. Trainer counters and quality are
  // declarations unless the separate trainer/evaluator signatures are independently audited.
  const evidence={...input,baselineCombinedSha256:baseline.combinedSha256,
   weights:{...weights,kind:'FULL_STUDENT_WEIGHTS'},quality:{...input.quality,verified:false},
   windowsSync:{...input.windowsSync,verified:false},
   teachers:(input.teachers||[]).map(t=>({...t,samplesVerified:false}))};
  result=assessNoxProgress(evidence);
  result.attestation='LOCAL_WEIGHT_BYTES_SHA256_CHECKED';
  result.qualityAttestation='NOT_INDEPENDENTLY_VERIFIED';
  result.windowsTransferAttestation='NOT_INDEPENDENTLY_VERIFIED';
  result.teacherAttestation='NOT_INDEPENDENTLY_VERIFIED';
 }catch(error){
  result={schema:'nox-progress-receipt-v1',status:'HOLD',
   reason:String(error.message||error).slice(0,230),stepPercent:null,complete:false,
   weightUpdateVerified:false,windowsSyncVerified:false,qualityGainVerified:false};
 }
 result.generatedAt=new Date().toISOString();
 if(!inside(workspace,outPath))throw Error('OUTPUT_OUTSIDE_WORKSPACE');
 await fsp.mkdir(path.dirname(outPath),{recursive:true});
 await fsp.writeFile(outPath,JSON.stringify(result,null,2)+'\n',{flag:'w'});
 console.log(JSON.stringify({status:result.status,reason:result.reason,stepPercent:result.stepPercent,
  weightUpdateVerified:result.weightUpdateVerified,output:outPath}));
 if(result.status==='HOLD')process.exitCode=2;
}
await main();
