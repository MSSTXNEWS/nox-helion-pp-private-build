'use strict';
// Deterministic elapsed-clock / stalled-timer witness, no physical latency claim.
async function exercise(load,createAdmissionBudget){
  const eq=(a,b)=>{if(a!==b)throw Error('expected '+b+' got '+a);};
  const cases=[
    {name:'baseline_late_preflight',pre:35,verify:0,budget:false,posts:1},
    {name:'absolute_late_preflight',pre:35,verify:0,budget:true,posts:0,elapsed:35},
    {name:'absolute_cross_phase',pre:4,verify:3,budget:true,posts:0,elapsed:7},
    {name:'within_budget',pre:1,verify:2,budget:true,posts:1,elapsed:3},
    {name:'exact_deadline',pre:2,verify:3,budget:true,posts:0,elapsed:5},
    {name:'clock_regression',pre:2,verify:-3,budget:true,posts:0,elapsed:null}
  ];
  const results=[];
  for(const c of cases){
    let t=100,posts=0,verifyCalls=0,ui=0;
    const now=()=>t,{clientApi,guardApi}=load(now);
    const scope={conversation_id:'fixture-dialog',exchange_id:'fixture-turn-2'};
    const underlying={post(){posts++;throw Error('fixture: no upstream or SSE');},readback(){throw Error('unexpected readback');},ack(){throw Error('unexpected ack');}};
    const budget=createAdmissionBudget({transport:underlying,limitMs:5,now});
    const guarded=guardApi.createWireGuard({transport:c.budget?budget.transport:underlying,deadlineMs:1000,contract:{wire:'named-delta-stable-server-id-v1',route:'fixture',served_sha256:'a'.repeat(64),server_sha256:'b'.repeat(64)},verifyWire(){verifyCalls++;t+=c.verify;return true;}});
    const client=clientApi.createClient({transport:guarded,host:{readCommitted(){t+=c.pre;return null;}},bridge:{acceptTerminal(){ui++;}},ui:{onDelta(){ui++;},upsertTerminal(){ui++;}},timeoutMs:5});
    const call=()=>c.budget?budget.begin(client,scope):client.begin(scope);
    const outcome=await call().then(x=>x,e=>e.code);
    eq(outcome,'HOLD_STREAM_POST_OR_READ');eq(posts,c.posts);eq(verifyCalls,1);eq(ui,0);
    const again=await call().then(x=>x,e=>e.code);
    eq(again,c.budget?'HOLD_B4_BUDGET_NO_REPOST':'HOLD_STREAM_NO_REPOST');eq(posts,c.posts);
    const report=c.budget?budget.report(scope):null;
    if(report){eq(report.admission_elapsed_ms,c.elapsed);eq(report.transport_invoked,Boolean(c.posts));eq(report.closed,true);eq(report.native_accepted,false);if(!c.posts&&c.elapsed!==null)eq(report.reason,'HOLD_B4_BUDGET_EXPIRED');}
    results.push({case:c.name,fixture_elapsed_ms:t-100,posts,ui,report});
  }
  return results;
}
module.exports={exercise};
if(require.main===module){
  const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
  const {createAdmissionBudget}=require('./b4_r63_admission_budget.cjs');
  const [p1,p2]=process.argv.slice(2),files=[p1,p2].map(p=>fs.readFileSync(p));
  const expected=['6db447710b579433496dfa64ceb4118461493864','f55da5b53b496b8f78f72822f1be83c171727884'];
  files.forEach((b,i)=>{if(crypto.createHash('sha1').update('blob '+b.length+'\0').update(b).digest('hex')!==expected[i])throw Error('source pin mismatch');});
  const load=now=>{const ctx={AbortController,TextDecoder,TextEncoder,performance:{now},setTimeout:()=>1,clearTimeout:()=>{}};files.forEach(b=>vm.runInNewContext(b.toString('utf8'),ctx,{timeout:1000}));return {clientApi:ctx.NOXB1StreamReconnect,guardApi:ctx.NOXB1WireGuard};};
  exercise(load,createAdmissionBudget).then(x=>console.log(JSON.stringify(x)),e=>{console.error(e);process.exitCode=1;});
}
