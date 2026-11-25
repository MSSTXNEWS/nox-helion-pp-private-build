'use strict';
// B3 R57: source-only transform, no shared writes or live requests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {createHash}=require('node:crypto');
const src=fs.readFileSync(__dirname+'/b3_r56_combined_candidate.js','utf8');
assert.equal(createHash('sha256').update(src).digest('hex'),'1a9d46ea35042efe05d081e0d89642609c127a7fdc18c44b8235e03b21bbdce4');
const old="if(phase&&typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')\nwindow.dispatchEvent(new CustomEvent('nox:native-phase',{detail:{phase}}));";
const next="if(phase&&phase!==lastPhase){lastPhase=phase;\nif(typeof window.dispatchEvent==='function'&&typeof CustomEvent==='function')\nwindow.dispatchEvent(new CustomEvent('nox:native-phase',{detail:{phase}}));}";
assert.equal(src.split(old).length,2);
assert.equal(src.split('let firstVisibleMs=null;').length,2);
const candidate=src.replace('let firstVisibleMs=null;','let firstVisibleMs=null,lastPhase=null;').replace(old,next);
new Function(candidate);
assert(Buffer.byteLength(candidate)<=25454);
function simulate(s,payloads){
 const event=s.match(/const event=payload=>\{[\s\S]*?controller\.enqueue[^\n]+\n\};/)[0];
 return new Function('payloads','let closed=false,canceling=false,firstVisibleMs=null,lastPhase=null;const started=0;const phases=[],frames=[];const window={dispatchEvent:e=>phases.push(e.detail.phase)};class CustomEvent{constructor(n,o){this.detail=o.detail}};const controller={enqueue:x=>frames.push(x)},enc={encode:x=>x},performance={now:()=>10};'+event+';for(const p of payloads)event(p);return {phases,frames,firstVisibleMs};')(payloads);
}
const payloads=[{type:'meta'},...Array.from({length:128},()=>({type:'token',t:'т'})),{type:'done'}];
const before=simulate(src,payloads),after=simulate(candidate,payloads);
assert.equal(before.phases.length,130);
assert.deepEqual(after.phases,['waiting','speaking','idle']);
assert.deepEqual(after.frames,before.frames);
assert.equal(after.firstVisibleMs,before.firstVisibleMs);
if(process.argv.includes('--emit'))process.stdout.write(candidate);
else console.log(JSON.stringify({task:'5A05-B3-R56-PHASE-TRANSITION-PORT-20261124-R57',before:before.phases.length,after:after.phases.length,frames:after.frames.length,bytes:Buffer.byteLength(candidate),sha256:createHash('sha256').update(candidate).digest('hex'),native_accepted:false}));
