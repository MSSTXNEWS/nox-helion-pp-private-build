'use strict';
// Offline only. All inputs require independent authenticated providers.
// Compose R66 and R70 under one physical expectation; do not synthesize a
// terminal-saved receipt from EOF or grant next POST. R71 does not replace B5.
const r66=require('./b3_r66_raw_readback_binding.cjs');
const r70=require('./b3_r70_s03_terminal_identity.cjs');
const fields=['model_id','route','dialog_id','weights_manifest_sha256','tokenizer_manifest_sha256','bridge_sha256','original_checkpoint_sha256','owner_admission_receipt_sha256','window_start_ms','window_end_ms'];
function samePhysical(a,b){
 return !!a&&!!b&&fields.every(k=>a[k]===b[k])&&!!a.process&&!!b.process&&
 ['boot_id','pid','start_ticks'].every(k=>a.process[k]===b.process[k])&&
 Array.isArray(a.turn_request_ids)&&Array.isArray(b.turn_request_ids)&&a.turn_request_ids.length===2&&b.turn_request_ids.length===2&&a.turn_request_ids.every((x,i)=>x===b.turn_request_ids[i]);
}
function check(input){
 const fail=reason=>({status:'HOLD',reason,consistent:false,native_accepted:false,authentication_verified:false,next_post_allowed:false});
 try{
  if(!input||!input.receipts||!Array.isArray(input.turns)||input.turns.length!==2)return fail('PAIR_REQUIRED');
  const receipts=r66.check(input.receipts);
  if(!receipts.consistent)return fail('R66_'+receipts.reason);
  const expected=input.receipts.expected;
  for(let i=0;i<2;i++){
   const t=input.turns[i];
   if(!t||t.expectedTurn!==i+2||!samePhysical(expected,t.physical))return fail('PHYSICAL_SCOPE_'+(i+2));
   const result=r70.check({...t,physical:expected});
   if(!result.consistent)return fail('R70_'+result.reason);
  }
  const [a,b]=input.turns;
  if(['wire','route','served_sha256','server_sha256'].some(k=>a.wire[k]!==b.wire[k]))return fail('WIRE_DRIFT');
  if(a.scope.conversation_id!==b.scope.conversation_id||
    a.mapping.exchange_bindings.some((x,i)=>x.exchange_id!==b.mapping.exchange_bindings[i].exchange_id))return fail('LOGICAL_SCOPE_DRIFT');
  return {status:'CONSISTENT_COMPOSED_PHYSICAL_ONLY',consistent:true,readbacks:4,turns:2,native_accepted:false,authentication_verified:false,next_post_allowed:false,requires_external_verifier:true,requires_b5_retained_chain:true};
 }catch{return fail('INVALID_INPUT');}
}
function selfTest(){
 const {createHash}=require('node:crypto'),sha=s=>createHash('sha256').update(s,'utf8').digest('hex');
 const h=n=>n.toString(16).padStart(64,'0'),copy=x=>JSON.parse(JSON.stringify(x));
 const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['req2','req3'],window_start_ms:100,window_end_ms:200};
 const wire={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
 function turn(n){
  const scope={conversation_id:'logical-conversation',exchange_id:'exchange-'+n};
  const mapping={...copy(physical),schema:'NOX_B3_ROUTE_BINDING_V1',wire:wire.wire,symbolic_route:wire.route,served_sha256:wire.served_sha256,server_sha256:wire.server_sha256,conversation_id:scope.conversation_id,exchange_bindings:[{turn:2,request_id:'req2',exchange_id:'exchange-2'},{turn:3,request_id:'req3',exchange_id:'exchange-3'}]};
  const terminal={...scope,physical_dialog_id:physical.dialog_id,request_id:physical.turn_request_ids[n-2],attempt_id:'attempt-'+n,sequence:n,status:'STREAM_ENDED_READBACK_REQUIRED'};
  const rows=Array.from({length:2*n},(_,i)=>({role:i%2?'assistant':'user',content:'fixture '+i,message_id:'msg-'+i,dialog_id:'canonical-dialog',session_id:'canonical-session'}));
  const common={source:'canonical_s03',event_id:'event-'+n,turn_id:'turn-'+n,sequence:n,dialog_id:'canonical-dialog',session_id:'canonical-session'};
  const canonical={writer:{...common,verified:true,durable:true},readback:{...common,independent:true,messages:copy(rows)},rows,writer_sha256:h(30+n),readback_sha256:h(40+n)};
  const link={schema:'NOX_B3_S03_TERMINAL_LINK_V1',...terminal,served_sha256:wire.served_sha256,s03_dialog_id:common.dialog_id,s03_session_id:common.session_id,s03_event_id:common.event_id,s03_turn_id:common.turn_id,user_message_id:rows.at(-2).message_id,assistant_message_id:rows.at(-1).message_id,writer_sha256:canonical.writer_sha256,readback_sha256:canonical.readback_sha256};
  return {wire:copy(wire),physical:copy(physical),mapping,scope,expectedTurn:n,terminal,canonical,link};
 }
 const payloads=Array.from({length:4},(_,i)=>JSON.stringify({...physical,turn:2+Math.floor(i/2),phase:i%2?'after':'before',request_id:physical.turn_request_ids[Math.floor(i/2)],observed_ms:110+i*10,readback_id:'receipt-'+i,installed_bridge_sha256:physical.bridge_sha256,served_bridge_sha256:physical.bridge_sha256}));
 const fixture={receipts:{schema:'NOX_B3_R66_READBACK_BYTES_V1',expected:physical,receipt_payloads:payloads,receipt_index:payloads.map((s,i)=>({readback_id:'receipt-'+i,sha256:sha(s)}))},turns:[turn(2),turn(3)]};
 const coherent=(t,k,v)=>{t.physical[k]=copy(v);t.mapping[k]=copy(v);};
 const cases=[['valid',x=>{},true],['missing receipt',x=>x.receipts.receipt_payloads.pop(),false],['modified raw',x=>x.receipts.receipt_payloads[0]+=' ',false],['wrong digest',x=>x.receipts.receipt_index[0].sha256=h(91),false],['foreign weights both turns',x=>x.turns.forEach(t=>coherent(t,'weights_manifest_sha256',h(92))),false],['foreign tokenizer turn3',x=>coherent(x.turns[1],'tokenizer_manifest_sha256',h(93)),false],['foreign process',x=>coherent(x.turns[1],'process',{boot_id:'other',pid:42,start_ticks:123}),false],['foreign model',x=>coherent(x.turns[0],'model_id','other'),false],['foreign route',x=>coherent(x.turns[0],'route','/other'),false],['foreign checkpoint',x=>coherent(x.turns[0],'original_checkpoint_sha256',h(94)),false],['foreign admission',x=>coherent(x.turns[0],'owner_admission_receipt_sha256',h(95)),false],['foreign window',x=>coherent(x.turns[1],'window_end_ms',201),false],['wire drift',x=>{x.turns[1].wire.server_sha256=x.turns[1].mapping.server_sha256=h(96)},false],['conversation drift',x=>{const t=x.turns[1];for(const o of [t.scope,t.mapping,t.terminal,t.link])o.conversation_id='other'},false],['exchange map drift',x=>{x.turns[1].mapping.exchange_bindings[0].exchange_id='other'},false],['reordered turns',x=>x.turns.reverse(),false],['wrong terminal request',x=>x.turns[1].terminal.request_id='other',false],['foreign terminal browser build',x=>x.turns[1].link.served_sha256=h(99),false],['wrong saved status',x=>x.turns[1].terminal.status='TERMINAL_SAVED',false]];
 let reproduced=0;
 const results=cases.map(([name,mutate,want])=>{const x=copy(fixture);mutate(x);const separately=r66.check(x.receipts).consistent&&x.turns.every(t=>r70.check(t).consistent);const z=check(x);if(!want&&separately)reproduced++;if(z.consistent!==want||z.native_accepted!==false||z.authentication_verified!==false||z.next_post_allowed!==false)throw Error(name+JSON.stringify(z));return {name,separately,consistent:z.consistent,reason:z.reason||null};});
 if(reproduced<10)throw Error('missing differential reproduction '+reproduced);
 return {results,reproduced,native_accepted:false};
}
module.exports={check,selfTest};
if(require.main===module)console.log(JSON.stringify(selfTest(),null,2));
