#!/usr/bin/env node
/* NOX HELION one-invocation acceptance runner. Node.js >=22, Windows Edge,
   original V25.1 NOX site. No model switches, fake training, system reboots,
   deployment, GPU restarts, disk cleanup, credentials, or production changes.
   Repeats ONLY safe and retryable checks; all evidence is written atomically.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const site=path.join(root,'site');
const work=path.join(root,'NOX_QA_RESULTS');
const stopFile=path.join(root,'NOX_STOP');
const stateFile=path.join(work,'state.json');
const reportFile=path.join(work,'FULL_ACCEPTANCE.json');
const sourceManifestFile=path.join(root,'SOURCE_MANIFEST.json');
const PIN={
 repository:'MSSTXNEWS/nox-helion-pp-private-build',
 branch:'fix/home-v16-cinematic-contract-20261110',
 sourceHead:'b55e9979765ea35449a99f7dc54917cfedcd65bb',
 provenance:'https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43146688351',
 files:{
  'nox-home.mjs':'8066bc0a0f8ef5bb5f0fb1f58ad3f6ee29dc8506385c09d77d38d4235c7e42e9',
  'nox-engines/physical-worlds-v7.mjs':'3f27609ea37b96579a711928e4c67778ec71e2ff7b090a3b7bb41e29040f3905',
  'assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp':'3253d26819a70b49259fdb2a56c2eaa2455c6878cb2ccb8d62b225ec6ccdfa22'
 }
};
const PAGES=['index','chat','cinema','install','memory','models','projects','settings','system','training'];
if(!Number.isFinite(Number(process.versions.node.split('.')[0]))||Number(process.versions.node.split('.')[0])<22){
 console.error('BLOCKED: Node.js 22+ required.');process.exit(20);
}
fs.mkdirSync(work,{recursive:true});
const readJson=(p,fallback=null)=>{try{return JSON.parse(fs.readFileSync(p,'utf8'))}catch{return fallback}};
function writeJson(p,obj){const t=p+'.tmp-'+process.pid;fs.writeFileSync(t,JSON.stringify(obj,null,2));fs.renameSync(t,p)}
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const now=()=>new Date().toISOString();
const stop=()=>fs.existsSync(stopFile);
const IMG_FILES=['320.png','390.png','800x480.png','1024.png','1440.png','1920.png','4k.jpg'];
const validSha=x=>typeof x==='string'&&/^[a-f0-9]{64}$/i.test(x);
const recent=(iso,maxMs)=>Number.isFinite(Date.parse(iso))&&Date.now()-Date.parse(iso)>=0&&Date.now()-Date.parse(iso)<=maxMs;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const retryMs=Number(process.env.NOX_RETRY_SECONDS||180)*1000;
let state=readJson(stateFile,{schema:'NOX_ONEPASS_STATE_1',created:now(),sourceHead:PIN.sourceHead,phases:{},history:[]});
let stopped=false,hostServer=null;
function log(kind,message){const line=`${now()} [${kind}] ${message}`;console.log(line);fs.appendFileSync(path.join(work,'events.log'),line+'\n')}
function persist(){state.lastUpdated=now();writeJson(stateFile,state)}
function phase(name,status,detail={}){state.phases[name]={status,at:now(),...detail};state.history.push({name,status,at:now()});if(state.history.length>300)state.history=state.history.slice(-300);persist();log(name,status)}
function assertReady(){if(stop())throw Error('NOX_STOP_FLAG');if(!fs.existsSync(site))throw Error('NOX_SITE_NOT_EXTRACTED');}
function walk(p,rel=''){
 const out=[];
 for(const ent of fs.readdirSync(p,{withFileTypes:true})){
  if(['node_modules','.git','nox-v21-acceptance','nox-physical-gpu-qa','NOX_QA_RESULTS','package-lock.json','package.json'].includes(ent.name))continue;
  const name=rel?rel+'/'+ent.name:ent.name;
  if(ent.isDirectory())out.push(...walk(path.join(p,ent.name),name));else if(ent.isFile())out.push(name);
 }return out;
}
function checkSource(){
 assertReady();const mismatches=[];
 for(const [rel,expected] of Object.entries(PIN.files)){
  const p=path.join(site,rel);const actual=fs.existsSync(p)?sha(p):null;
  if(expected!==actual)mismatches.push({file:rel,expected,actual});
 }
 for(const f of PAGES){if(!fs.existsSync(path.join(site,f+'.html')))mismatches.push({missing:f+'.html'})}
 if(mismatches.length){phase('SOURCE','BLOCKED_SOURCE_INTEGRITY',{mismatches});throw Error('SOURCE_SHA_OR_10_PAGES_FAILED')}
 const manifest=readJson(sourceManifestFile,{});
 if(manifest.schema!=='NOX_SITE_SOURCE_LOCK_V1'||manifest.sourceHead!==PIN.sourceHead||
    typeof manifest.files!=='object'||Object.keys(manifest.files).length<290)throw Error('NOX_MISSING_SOURCE_MANIFEST');
 const all=walk(site).sort(),listed=Object.keys(manifest.files).sort();
 if(JSON.stringify(all)!==JSON.stringify(listed))throw Error('NOX_SITE_FILE_SET_CHANGED_REQUIRES_NEW_MANIFEST');
 for(const rel of listed){if(sha(path.join(site,rel))!==manifest.files[rel]){
   phase('SOURCE','BLOCKED_SOURCE_DRIFT',{file:rel});throw Error('NOX_SOURCE_DRIFT:'+rel)
 }}
 const fp=sha(sourceManifestFile);
 if(state.fingerprint&&state.fingerprint!==fp){
  log('SOURCE','File changes detected; invalidating earlier QA results for previous fingerprint');
  for(const key of ['STATIC','CHROMIUM','PHYSICAL_GPU'])delete state.phases[key];
 }
 state.fingerprint=fp;state.sourceHead=PIN.sourceHead;phase('SOURCE','PASS',{fingerprint:fp,filesChecked:all.length,pins:PIN.files,sourceHead:PIN.sourceHead});
}
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8',
 '.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.wasm':'application/wasm',
 '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml',
 '.hdr':'application/octet-stream','.stl':'model/stl','.mp4':'video/mp4','.woff2':'font/woff2','.woff':'font/woff',
 '.map':'application/json','.bin':'application/octet-stream','.pdf':'application/pdf','.txt':'text/plain; charset=utf-8'};
function startServer(){return new Promise((resolve,reject)=>{
 const srv=http.createServer((req,res)=>{
  if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);res.end('METHOD_NOT_ALLOWED');return}
  const u=new URL(req.url||'/', 'http://localhost');let uri;
  try{uri=decodeURIComponent(u.pathname)}catch{res.writeHead(400);res.end();return}
  if(uri.includes('\0')||uri.split('/').includes('..')){res.writeHead(403);res.end();return}
  const real=path.resolve(site,'.'+(uri==='/'?'/index.html':uri));
  if(!real.startsWith(site+path.sep)){res.writeHead(403);res.end();return}
  fs.stat(real,(err,st)=>{
   if(err||!st.isFile()){res.writeHead(404,{'Cache-Control':'no-store'});res.end('NOX_FILE_NOT_FOUND');return}
   res.writeHead(200,{'Content-Type':types[path.extname(real).toLowerCase()]||'application/octet-stream',
     'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
   if(req.method==='HEAD'){res.end();return}fs.createReadStream(real).pipe(res);
  });
 });srv.once('error',reject);srv.listen(0,'127.0.0.1',()=>resolve(srv));
})}
function exec(program,args,env={},name='command',timeoutMinutes=50){return new Promise((resolve,reject)=>{
 if(stop())return reject(Error('NOX_STOP_FLAG'));
 let child;const logfile=fs.createWriteStream(path.join(work,`${name}.log`),{flags:'a'});
 const win=process.platform==='win32',cmd=win&&['npm','npx'].includes(program)?program+'.cmd':program;
 try{child=spawn(cmd,args,{cwd:site,env:{...process.env,...env},shell:win&&cmd.endsWith('.cmd'),windowsHide:false});}
 catch(e){logfile.end();return reject(e)}
 const timer=setTimeout(()=>child.kill('SIGTERM'),timeoutMinutes*60000);
 const stopper=setInterval(()=>{if(stop()&&!child.killed){log('STOP','Canceling only active QA child '+name);child.kill('SIGTERM')}},1000);let last='';
 const capture=d=>{const s=String(d);logfile.write(s);last=(last+s).slice(-4500)};
 child.stdout.on('data',capture);child.stderr.on('data',capture);
 child.on('error',e=>{clearTimeout(timer);clearInterval(stopper);logfile.end();reject(e)});
 child.on('close',(code,signal)=>{clearTimeout(timer);clearInterval(stopper);logfile.end();
  if(code===0)resolve({code});else reject(Error(`${name} exited ${code} ${signal||''}: ${last.slice(-800)}`));
 });
})}
async function staticQA(){
 if(state.phases.STATIC?.status==='PASS')return;
 await exec(process.execPath,['tools/audit-static-references.mjs','.'],{},'static-references',4);
 await exec(process.execPath,['tools/audit-wow-wiring-v24.mjs','.'],{},'source-wow-engines',5);
 phase('STATIC','PASS',{pages:10,originalWowWiring:true});
}
async function browsersInstalled(){
 if(fs.existsSync(path.join(site,'node_modules','playwright','package.json')))return;
 log('SETUP','Installing Playwright 1.58.2 locally (not changing NOX binaries)');
 await exec('npm',['install','--no-save','--no-audit','--no-fund','playwright@1.58.2'],{},'install-playwright',15);
}
function validateChromiumReport(){
 const dir=path.join(work,'chromium'),q=readJson(path.join(dir,'report.json'),{});
 const ok=q.sourceRevision===PIN.sourceHead&&q.summary?.browserCandidates===7&&q.summary?.total===7&&
   q.summary?.pageUiPassed===10&&q.summary?.v19ModulesPassed===5&&
   q.originalVisualAuditV7?.status==='BROWSER_CANDIDATE'&&
   q.cases?.length===7&&q.cases.every(c=>c.acceptance==='BROWSER_CANDIDATE'&&(!c.errors||c.errors.length===0))&&
   q.sections?.length===10&&q.sections.every(c=>c.acceptance==='PAGE_UI_PASS')&&
   q.v19Modules?.length>=5&&q.v19Modules.filter(c=>c.passed).length>=5;
 if(!ok)return {ok:false,reason:'CHROMIUM_REPORT_INCOMPLETE_OR_DIFFERENT_SHA'};
 const screenshotHashes={};
 for(const f of IMG_FILES){const file=path.join(dir,f);
  if(!fs.existsSync(file)||fs.statSync(file).size<12000)return {ok:false,reason:'CHROMIUM_MISSING_SCREENSHOT:'+f};
  screenshotHashes[f]=sha(file);
 }
 const previous=state.phases.CHROMIUM?.screenshots;
 if(previous&&Object.keys(previous).some(f=>previous[f]!==screenshotHashes[f]))
  return {ok:false,reason:'CHROMIUM_SCREENSHOT_CHANGED'};
 return {ok:true,q,screenshotHashes};
}
async function chromiumQA(localUrl){
 if(state.phases.CHROMIUM?.status==='PASS'){
  const previous=validateChromiumReport();
  if(previous.ok){log('CHROMIUM','previous PASS readback reverified against source SHA, 7 screenshots and 10 routes');return}
  phase('CHROMIUM','HOLD_INVALID_CACHED_EVIDENCE',{reason:previous.reason});
 }
 await browsersInstalled();
 await exec('npx',['playwright','install','chromium'],{},'install-chromium',20);
 await exec(process.execPath,['tools/browser-acceptance.mjs'],{
  NOX_PREVIEW_URL:localUrl+'index.html',NOX_ACCEPTANCE_DIR:path.join(work,'chromium'),
  NOX_AUDIT_SOURCE_SHA:PIN.sourceHead},'browser-10routes-14worlds',30);
 const proof=validateChromiumReport();
 if(!proof.ok){
  phase('CHROMIUM','HOLD_UNVERIFIED_BROWSER_RECEIPT',{reason:proof.reason});
  throw Error('BROWSER_HARD_GATES_NOT_MET:'+proof.reason)
 }
 phase('CHROMIUM','PASS',{sourceHead:PIN.sourceHead,summary:proof.q.summary,
  originalV7:proof.q.originalVisualAuditV7.status,report:'chromium/report.json',screenshots:proof.screenshotHashes});
}
function validatePhysicalEvidence(){
 const p=readJson(path.join(work,'physical-gpu','qa-report.json'),{});
 if(p.acceptance!=='PASS'||p.kind!=='HARDWARE_GPU_BROWSER'||!p.conditions?.realHardware||
   Object.values(p.conditions||{}).some(x=>x!==true)||p.routes?.length!==10||
   !p.routes.every(x=>x.status===200)||p.screenshots?.length!==7||
   !recent(p.finishedAt,24*3600000))return {ok:false,reason:'PHYSICAL_RECEIPT_MISSING_STALE_OR_HOLD'};
 const gpu=p.render?.renderer||'';
 if(!gpu||/swiftshader|llvmpipe|software rasterizer|microsoft basic render|warp/i.test(gpu))
   return {ok:false,reason:'SOFTWARE_RENDERER_NOT_PHYSICAL_GPU'};
 const checks={};
 for(const shot of p.screenshots){
  const file=path.join(work,'physical-gpu',path.basename(shot.path||''));
  if(!['320','390','800x480','1024','1440','1920','4k'].includes(String(shot.viewport))||path.basename(file)!==shot.viewport+'.png')return {ok:false,reason:'PHYSICAL_UNEXPECTED_SCREENSHOT'};
  if(!fs.existsSync(file)||fs.statSync(file).size<12000||!validSha(shot.sha256)||sha(file)!==shot.sha256)
   return {ok:false,reason:'PHYSICAL_SCREENSHOT_HASH_FAILED'};
  checks[shot.viewport]=shot.sha256;
 }
 if(new Set(p.screenshots.map(x=>x.viewport)).size!==7)return {ok:false,reason:'PHYSICAL_DUPLICATED_VIEWPORT'};
 return {ok:true,report:p,screenshots:checks};
}
async function gpuQA(localUrl){
 if(state.phases.PHYSICAL_GPU?.status==='PASS'){
  const prev=validatePhysicalEvidence();
  if(prev.ok&&state.phases.PHYSICAL_GPU.sourceHead===PIN.sourceHead&&state.phases.PHYSICAL_GPU.fingerprint===state.fingerprint){
   log('PHYSICAL_GPU','recent hardware receipt and all 7 screenshot hashes verified');return;
  }
  phase('PHYSICAL_GPU','HOLD_STALE_OR_INVALID_GPU_RECEIPT',{reason:prev.reason||'SOURCE_OR_FINGERPRINT_CHANGED'});
 }
 if(process.platform!=='win32'){
  phase('PHYSICAL_GPU','HOLD_REQUIRES_WINDOWS_INTERACTIVE_EDGE');return;
 }
 // One hardware check per hour when still HOLD: don't endlessly relaunch Edge.
 const prev=state.phases.PHYSICAL_GPU;
 if(prev?.status?.startsWith('HOLD')&&Date.now()-Date.parse(prev.at)<3600000)return;
 try{
  await browsersInstalled();
  await exec(process.execPath,['tools/physical-gpu-acceptance.mjs'],{
   NOX_SITE_URL:localUrl,NOX_GPU_QA_OUT:path.join(work,'physical-gpu')},'physical-edge-gpu',25);
  const proof=validatePhysicalEvidence();
  if(!proof.ok)throw Error('PHYSICAL_GPU_GATE_UNVERIFIED:'+proof.reason);
  phase('PHYSICAL_GPU','PASS',{renderer:proof.report.render?.renderer||null,sourceHead:PIN.sourceHead,
    fingerprint:state.fingerprint,screenshots:proof.screenshots,report:'physical-gpu/qa-report.json'});
 }catch(e){phase('PHYSICAL_GPU','HOLD_REAL_GPU_QA_FAILED',{reason:String(e.message||e).slice(0,400)})}
}
async function liveQA(){
 if(state.phases.LIVE_ONEHOST?.status==='FULL_VERIFIED'&&recent(state.phases.LIVE_ONEHOST.at,120000))return;
 const prev=state.phases.LIVE_ONEHOST;
 if(prev?.status?.startsWith('HOLD')&&Date.now()-Date.parse(prev.at)<120000)return;
 try{
  await exec(process.execPath,[path.join(root,'NOX_LIVE_ONEHOST_E2E.mjs')],{
   NOX_ONEHOST_URL:process.env.NOX_ONEHOST_URL||'http://127.0.0.1:18775/',
   NOX_LIVE_OUT:path.join(work,'onehost-proof.json'),
   NOX_ALLOW_TEST_CHAT:process.env.NOX_ALLOW_TEST_CHAT||'0'},'onehost-existing-api',6);
 }catch(e){log('ONEHOST',String(e.message||e).slice(0,200))}
 const p=readJson(path.join(work,'onehost-proof.json'),{});
 const facts=p.checks||{};
 // A separate exclusive native STOP/S03-restart test must provide a full
 // transcript and a hash-pinned receipt. This runner cannot safely cause the
 // shared STOP or reboot an active OneHost to produce these itself.
 const isolated=readJson(path.join(work,'isolated-native-proof.json'),{});
 const transcript=path.join(work,'isolated-native-transcript.ndjson');
 const isolatedVerified=isolated.schema==='NOX_ISOLATED_NATIVE_PROOF_V1'&&
   isolated.sourceHead===PIN.sourceHead&&isolated.exclusiveScope===true&&
   isolated.stop?.acknowledged===true&&isolated.stop?.lateTokensRejected===true&&
   isolated.s03?.persistedAcrossRestart===true&&isolated.s03?.sqliteIntegrity==='ok'&&
   fs.existsSync(transcript)&&sha(transcript)===isolated.transcriptSha256;
 const full=facts.ownerBound&&facts.s03DialogsBound&&facts.voiceRuEs&&facts.trainingCoordinator&&facts.weightsComplete&&facts.windowsSynced&&facts.qualityVerified&&
  p.chat?.state==='PASS'&&isolatedVerified;
 phase('LIVE_ONEHOST',full?'FULL_VERIFIED':'HOLD_NEEDS_REAL_ONEHOST_END_TO_END',{
  readPaths:p.reads||{},checks:facts,chat:p.chat?.state||'NOT_TESTED',
  isolatedStopAndS03:isolatedVerified?'VERIFIED':'HOLD_NEEDS_EXCLUSIVE_PHYSICAL_QA',
  stop:p.stop?.state||'NOT_TESTED',s03:p.s03?.state||'NOT_TESTED'});
}
function finalManifest(){
 const check=['SOURCE','STATIC','CHROMIUM','PHYSICAL_GPU','LIVE_ONEHOST'];
 const states=Object.fromEntries(check.map(k=>[k,state.phases[k]?.status||'NOT_TESTED']));
 // Owner visual sign-off is intentionally NOT inferred from browser screenshots.
 const owner=readJson(path.join(work,'owner-acceptance.json'),{});
 const ownerOkay=owner.sourceHead===PIN.sourceHead&&owner.siteFingerprint===state.fingerprint&&owner.result==='OWNER_APPROVED'&&
    typeof owner.evidence==='string'&&owner.evidence.length>10;
 const chrome=states.CHROMIUM==='PASS'&&validateChromiumReport().ok;
 const physical=states.PHYSICAL_GPU==='PASS'&&validatePhysicalEvidence().ok;
 const full=states.SOURCE==='PASS'&&states.STATIC==='PASS'&&chrome&&
   physical&&states.LIVE_ONEHOST==='FULL_VERIFIED'&&recent(state.phases.LIVE_ONEHOST?.at,120000)&&ownerOkay;
 const m={schema:'NOX_FULL_ACCEPTANCE_V1',at:now(),sourceHead:PIN.sourceHead,
  siteFingerprint:state.fingerprint,productionChanged:false,source:PIN.provenance,
  phases:states,ownerVisualAcceptance:ownerOkay?'OWNER_APPROVED':'HOLD_NOT_SIGNED_OFF',
  finalStatus:full?'FULL_ACCEPTED':'HOLD',reason:full?null:'Outstanding real-hardware/native/owner evidence; do not claim PASS'};
 writeJson(reportFile,m);return m;
}
async function main(){
 const info={at:now(),pid:process.pid};let lock=path.join(work,'runner.lock');
 if(fs.existsSync(lock)){
  const v=readJson(lock,{}),age=Date.now()-Date.parse(v.updated||v.at||'1970-01-01');
  if(age<120000){console.error('Another NOX one-pass runner currently holds this workspace lock.');process.exitCode=20;return}
  log('RECOVERY','Stale runner lock; continuing from atomic state without discarding evidence');
 }
 writeJson(lock,info);
 const heartbeat=setInterval(()=>{try{writeJson(lock,{...info,updated:now()})}catch{}},10000);
 try{
  checkSource();await staticQA();
  if(process.env.NOX_PREFLIGHT_ONLY==='1'){phase('PREFLIGHT','PASS',{sourceHead:PIN.sourceHead});finalManifest();return}
  hostServer=await startServer();const addr=hostServer.address(),url=`http://127.0.0.1:${addr.port}/`;
  log('SITE',`QA-only local server ${url} ; /api routes are NOT mocked`);
  let cycle=0;
  while(!stop()){
   cycle++;log('CYCLE',String(cycle));
   try{await chromiumQA(url)}catch(e){log('CHROMIUM','HOLD '+String(e.message||e).slice(0,250))}
   try{await gpuQA(url)}catch(e){log('GPU','HOLD '+String(e.message||e).slice(0,250))}
   try{await liveQA()}catch(e){log('ONEHOST','HOLD '+String(e.message||e).slice(0,250))}
   const m=finalManifest();log('RESULT',m.finalStatus+' '+JSON.stringify(m.phases));
   if(m.finalStatus==='FULL_ACCEPTED'){log('RESULT','Real QA completed; production was NOT promoted');return}
   if(process.env.NOX_ONCE==='1'){
    log('RESULT','One-cycle mode requested: preserve HOLD and exit');process.exitCode=2;return;
   }
   // Repeating a deterministic source defect without a code change will never
   // repair it. Leave evidence and continue only for recovering external conditions.
   for(let ms=retryMs;ms>0&&!stop();ms-=5000)await sleep(Math.min(ms,5000));
  }
  stopped=true;log('STOP','Owner NOX_STOP marker detected. Preserving reports and all existing data');
  process.exitCode=130;
 }finally{clearInterval(heartbeat);if(hostServer)await new Promise(r=>hostServer.close(r));
   try{fs.unlinkSync(lock)}catch{}
 }
}
main().catch(e=>{log('BLOCKED',String(e.stack||e).slice(0,2000));
 writeJson(path.join(work,'fatal.json'),{at:now(),error:String(e.message||e),sourceHead:PIN.sourceHead});
 process.exitCode=20;
});