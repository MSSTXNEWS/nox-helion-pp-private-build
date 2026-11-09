'use strict';
// G2-C / legacy G3-B · R16, SOURCE-ONLY. No browser, Windows, network or Ollama required.
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const sourcePath=path.resolve(__dirname,'..','..','Packages','P03','Source','P03.ModelCenter.Wow','ui.js');
const source=fs.readFileSync(sourcePath,'utf8');
const marker="$('search').addEventListener";
assert.ok(source.includes(marker),'the original ModelCenter UI bootstrap must remain intact');
const prefix=source.slice(0,source.indexOf(marker));
function fixture(){
  const outbound=[],toasts=[];
  const window={chrome:{webview:{postMessage:x=>outbound.push(x)}}};
  const document={getElementById:id=>id==='licenseAck'?{checked:false}:null};
  const factory=new Function('window','document','setTimeout','clearTimeout','toasts',
    prefix+'\nrenderHero=()=>{};renderQuick20=()=>{};showToast=x=>toasts.push(x);return {state,sendAction,processMessage};');
  const app=factory(window,document,()=>1,()=>{},toasts);
  const jobId='11111111-1111-4111-8111-111111111111', modelTag='private-gguf:approved';
  app.state.hostReady=true;
  app.state.capabilities={stop:true,retry:true,pull:false,importGguf:false};
  app.state.activeJob={jobId,modelTag,state:'Running'};
  return {...app,outbound,toasts,jobId,modelTag};
}
let checks=0;
function check(value,message){assert.ok(value,message);checks++;}
const x=fixture();
x.sendAction('stop');
const cmd=x.outbound[0];
check(cmd?.action==='stop'&&cmd.jobId===x.jobId,'STOP remains bound to queue jobId, not card');
check(x.state.pending.has('stop'),'STOP is pending until matching ACK');
x.processMessage({type:'p03.command.ack.v1',action:'stop',commandId:cmd.commandId,accepted:true,
 jobId:'22222222-2222-4222-8222-222222222222',modelTag:x.modelTag});
check(x.state.pending.has('stop'),'other job ACK must not unlock STOP');
check(!x.toasts.some(s=>s.includes('Host принял команду')),'other job ACK must not claim host acceptance');
x.processMessage({type:'p03.command.ack.v1',action:'stop',commandId:cmd.commandId,accepted:true,
 jobId:x.jobId,modelTag:'wrong:model'});
check(x.state.pending.has('stop'),'other model ACK must not unlock STOP');
x.processMessage({type:'p03.command.ack.v1',action:'stop',commandId:'stale',accepted:true,
 jobId:x.jobId,modelTag:x.modelTag});
check(x.state.pending.has('stop'),'wrong commandId must remain blocked');
x.processMessage({type:'p03.command.ack.v1',action:'stop',commandId:cmd.commandId,accepted:true,
 jobId:x.jobId,modelTag:x.modelTag});
check(!x.state.pending.has('stop'),'matching STOP ACK clears pending');
check(x.toasts.some(s=>s.includes('Host принял команду')),'matching STOP ACK reports host acceptance only');
const y=fixture();y.sendAction('stop');
y.processMessage({type:'p03.command.ack.v1',action:'stop',commandId:y.outbound[0].commandId,accepted:false});
check(!y.state.pending.has('stop'),'legacy host ACK without optional target fields remains supported');
const z=fixture();z.state.activeJob.state='Cancelled';z.sendAction('retry');
const retry=z.outbound[0];
check(retry?.action==='retry'&&retry.jobId===z.jobId,'Retry retains durable jobId');
z.processMessage({type:'p03.command.ack.v1',action:'retry',commandId:retry.commandId,
 accepted:true,modelTag:'wrong:model'});
check(z.state.pending.has('retry'),'other model ACK must not unlock Retry');
z.processMessage({type:'p03.command.ack.v1',action:'retry',commandId:retry.commandId,
 accepted:true,jobId:z.jobId,modelTag:z.modelTag});
check(!z.state.pending.has('retry'),'matching Retry ACK clears pending');
const noHost=fixture();noHost.state.hostReady=false;noHost.sendAction('stop');
check(noHost.outbound.length===0,'offline host cannot receive STOP command');
console.log('G2-C / G3-B R16 queue ACK target binding: '+checks+'/'+checks+' PASS (source-only)');
