'use strict';
// Actual pinned R71/R74/R63 code, synthetic monotonic clock + stalled timers.
// No live HTTP, no model, no browser or canonical S03 proof.
async function exercise(load,createAdmissionBudget,createPreverifierFence){
  const eq=(a,b)=>{if(a!==b)throw Error('expected '+b+' got '+a);};
  const cases=[
    {name:'baseline_expired_preflight',pre:35,verify:0,newFence:false,calls:1,posts:0},
    {name:'expired_preflight',pre:35,verify:0,newFence:true,calls:0,posts:0,reason:'HOLD_B4_R64_EXPIRED_VERIFIER'},
    {name:'exact_boundary',pre:5,verify:0,newFence:true,calls:0,posts:0,reason:'HOLD_B4_R64_EXPIRED_VERIFIER'},
    {name:'within_budget',pre:1,verify:2,newFence:true,calls:1,posts:1,reason:null},
    {name:'cross_phase_expiry',pre:4,verify:3,newFence:true,calls:1,posts:0,reason:'HOLD_B4_BUDGET_EXPIRED'},
    {name:'clock_regression',pre:-1,verify:0,newFence:true,calls:0,posts:0,reason:'HOLD_B4_R64_CLOCK'}
  ];
  const results=[];
  for(const c of cases){
    let t=100,calls=0,posts=0,ui=0,verifierSignal=null;
    const now=()=>t,{clientApi,guardApi}=load(now);
    const scope={conversation_id:'fixture-dialog',exchange_id:'fixture-turn-2'};
    const transport={post(){posts++;throw Error('fixture: no upstream');},readback(){throw Error('unexpected readback');},ack(){throw Error('unexpected ack');}};
    const verifyWire=(pin,s,signal)=>{calls++;verifierSignal=signal;t+=c.verify;return true;};
    const gate=c.newFence?createPreverifierFence({createAdmissionBudget,transport,verifyWire,limitMs:5,now}):createAdmissionBudget({transport,limitMs:5,now});
    const guarded=guardApi.createWireGuard({transport:gate.transport,verifyWire:c.newFence?gate.verifyWire:verifyWire,deadlineMs:1000,contract:{wire:'named-delta-stable-server-id-v1',route:'fixture',served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)}});
    const client=clientApi.createClient({transport:guarded,host:{readCommitted(){t+=c.pre;return null;}},bridge:{acceptTerminal(){ui++;}},ui:{onDelta(){ui++;},upsertTerminal(){ui++;}},timeoutMs:5});
    const outcome=await gate.begin(client,scope).then(x=>x,e=>e.code);
    eq(outcome,'HOLD_STREAM_POST_OR_READ');eq(calls,c.calls);eq(posts,c.posts);eq(ui,0);
    if(c.calls)eq(verifierSignal.aborted,true);
    const report=gate.report(scope);eq(report.transport_invoked,Boolean(c.posts));eq(report.closed,true);eq(report.native_accepted,false);
    if(c.newFence){eq(report.verifier_invoked,Boolean(c.calls));eq(report.reason,c.reason);}
    const repeat=await gate.begin(client,scope).then(x=>x,e=>e.code);
    eq(repeat,c.newFence?'HOLD_B4_R64_NO_REPOST':'HOLD_B4_BUDGET_NO_REPOST');eq(posts,c.posts);eq(calls,c.calls);
    results.push({case:c.name,simulated_elapsed_ms:t-100,verifier_calls:calls,posts,ui,report});
  }
  return results;
}
module.exports={exercise};
if(require.main===module){
  const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
  const {createAdmissionBudget}=require('./b4_r63_admission_budget.cjs'),{createPreverifierFence}=require('./b4_r64_preverifier_fence.cjs');
  const files=[fs.readFileSync(require.resolve('./b4_r63_admission_budget.cjs')),...process.argv.slice(2).map(p=>fs.readFileSync(p))];
  const pins=['2c5d50ee0b3719f6e9f76eaff7feede359f06cd0','6db447710b579433496dfa64ceb4118461493864','22bb2217f82bb44bfadc92b979e1af22e0dfaab8'];
  if(files.length!==3)throw Error('need R71 and R74 file paths');
  files.forEach((b,i)=>{if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==pins[i])throw Error('source pin mismatch');});
  const load=now=>{const ctx={AbortController,TextDecoder,TextEncoder,performance:{now},setTimeout:()=>1,clearTimeout:()=>{}};files.slice(1).forEach(b=>vm.runInNewContext(b.toString('utf8'),ctx,{timeout:1000}));return {clientApi:ctx.NOXB1StreamReconnect,guardApi:ctx.NOXB1WireGuard};};
  exercise(load,createAdmissionBudget,createPreverifierFence).then(x=>console.log(JSON.stringify(x)),e=>{console.error(e);process.exitCode=1;});
}
