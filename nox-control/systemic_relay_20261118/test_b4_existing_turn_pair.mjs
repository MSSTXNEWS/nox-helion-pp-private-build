import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';
import {bindExistingTurnPair} from './b4_existing_turn_pair.mjs';
const hash=s=>createHash('sha256').update(s).digest('hex');
test('R53 bind actual measured source fixtures for existing turns 2/3 without replay',async()=>{
  const dialog='a'.repeat(32);
  const expected={dialog_id:dialog,prior_exchange_id:'exchange-1',
    baseline_browser_posts:7,baseline_admitted_posts:5,turns:[]};
  const observed=[];
  for(const turn of [2,3]){
    const exchange='exchange-'+turn,answer='Hola 🌈 Привет';
    const frames=[{type:'meta',dialog_id:dialog,answer_source:'NATIVE_PENDING'},
      {type:'token',t:'Hola '},{type:'token',t:'🌈 Привет'},
      {type:'done',status:'done',saved:true,history_persisted:true,dialog_id:dialog,
       exchange_id:exchange,answer_source:'LIVE_NOX',s03_integrated:turn===3,
       first_visible_token_ms:999999}];
    const wire=frames.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('');
    // Independent expected fixture digests, not copied from the probe result.
    expected.turns.push({turn,exchange_id:exchange,body_sha256:hash(wire),visible_text_sha256:hash(answer)});
    const proof=await measureSseResponse(new Response(wire,{headers:{'content-type':'text/event-stream'}}),
      {protocol:'nox-browser',expectedDialogId:dialog});
    observed.push({turn,proof,browser_posts:7+turn-1,admitted_posts:5+turn-1});
  }
  const result=bindExistingTurnPair(expected,observed);
  assert.equal(result.status,'B4_PAIR_INPUTS_MATCHED');
  assert.deepEqual(result.turns.map(x=>x.exchange_id),['exchange-2','exchange-3']);
  assert.equal(result.turns[0].visible_text_sha256,result.turns[1].visible_text_sha256);
  assert.equal(result.native_verified,false);
  assert.equal(result.browser_authenticated,false);
  assert.equal(result.canonical_s03_verified,false);
  assert.equal(result.model_tokens_per_second,null);
  const cases=[
    ['swapped turns',(e,o)=>o.reverse(),'B4_PAIR_SEQUENCE'],
    ['replayed first turn',(e,o)=>e.turns[0].exchange_id=e.prior_exchange_id,'B4_PAIR_SEQUENCE'],
    ['duplicate exchange',(e,o)=>e.turns[1].exchange_id=e.turns[0].exchange_id,'B4_PAIR_SEQUENCE'],
    ['duplicate raw capture',(e,o)=>e.turns[1].body_sha256=e.turns[0].body_sha256,'B4_PAIR_SEQUENCE'],
    ['extra browser POST',(e,o)=>o[1].browser_posts++,'B4_PAIR_POST_COUNT'],
    ['extra admission',(e,o)=>o[0].admitted_posts++,'B4_PAIR_POST_COUNT'],
    ['foreign dialog',(e,o)=>o[1].proof.dialog_id='b'.repeat(32),'B4_PAIR_PROOF'],
    ['wrong exchange',(e,o)=>o[1].proof.exchange_id='exchange-2','B4_PAIR_PROOF'],
    ['wrong raw digest',(e,o)=>o[1].proof.body_sha256='0'.repeat(64),'B4_PAIR_PROOF'],
    ['wrong answer digest',(e,o)=>o[0].proof.visible_text_sha256='0'.repeat(64),'B4_PAIR_PROOF'],
    ['fake native proof',(e,o)=>o[0].proof.native_verified=true,'B4_PAIR_PROOF'],
    ['fake S03 proof',(e,o)=>o[0].proof.canonical_s03_verified=true,'B4_PAIR_PROOF'],
    ['fake model speed',(e,o)=>o[0].proof.model_tokens_per_second=10,'B4_PAIR_PROOF'],
    ['invalid latency',(e,o)=>o[0].proof.ttft_ms=-1,'B4_PAIR_TIMING'],
    ['EOF before done',(e,o)=>o[0].proof.completion_ms=-1,'B4_PAIR_TIMING'],
    ['missing turn',(e,o)=>o.pop(),'B4_PAIR_SCOPE']
  ];
  for(const [name,mutate,code] of cases){
    const e=structuredClone(expected),o=structuredClone(observed);
    mutate(e,o);assert.throws(()=>bindExistingTurnPair(e,o),x=>x.code===code,name);
  }
  console.log('B4_R53_SOURCE_ONLY '+JSON.stringify({turns:result.turns.map(t=>({turn:t.turn,ttft_ms:t.ttft_ms,completion_ms:t.completion_ms})),negative_cases:cases.length,real_glm:false}));
});
