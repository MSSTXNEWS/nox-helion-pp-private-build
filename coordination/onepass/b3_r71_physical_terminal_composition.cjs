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
  // Each R70 proof is internally consistent; it must also preserve the prior S03 prefix.
  if(a.link.s03_dialog_id!==b.link.s03_dialog_id||a.link.s03_session_id!==b.link.s03_session_id)return fail('CANONICAL_SCOPE_DRIFT');
  const previous=a.canonical.rows, next=b.canonical.rows;
  if(next.length!==previous.length+2||previous.some((row,i)=>['message_id','dialog_id','session_id','role','content'].some(k=>row[k]!==next[i][k])))return fail('CANONICAL_PREFIX_DRIFT');
  return {status:'CONSISTENT_COMPOSED_PHYSICAL_ONLY',consistent:true,readbacks:4,turns:2,native_accepted:false,authentication_verified:false,next_post_allowed:false,requires_external_verifier:true,requires_b5_retained_chain:true};
 }catch{return fail('INVALID_INPUT');}
}
// Joint offline consumer of the exact B5 R78 compare_pair result.
// The owner supplies B5 output and original link bytes independently, not from
// the B3 candidate. This checks consistency, never authentication or ACK.
function checkRetainedPair(input,pair,linkPayloads){
 const fail=reason=>({status:'HOLD',reason,consistent:false,native_accepted:false,authentication_verified:false,ack_allowed:false,next_post_allowed:false});
 try{
  const base=check(input);
  if(!base.consistent)return fail('R71_'+base.reason);
  const {createHash}=require('node:crypto'),sha=s=>createHash('sha256').update(s,'utf8').digest('hex');
  const flags=['authentication_verified','native_accepted','ack_allowed','next_post_allowed'];
  const offline=x=>x&&flags.every(k=>x[k]===false);
  if(!offline(pair)||pair.status!=='S03_PROJECTION_PAIR_MATCHED_OFFLINE'||!Array.isArray(pair.turns)||pair.turns.length!==2||!Array.isArray(linkPayloads)||linkPayloads.length!==2)return fail('B5_PAIR');
  for(let i=0;i<2;i++){
   const t=input.turns[i],p=pair.turns[i],raw=linkPayloads[i];
   if(!offline(p)||p.status!=='S03_PROJECTION_MATCHED_OFFLINE'||p.sequence!==i+2)return fail('B5_TURN_'+(i+2));
   if(p.writer_sha256!==t.canonical.writer_sha256||p.readback_sha256!==t.canonical.readback_sha256)return fail('B5_WITNESS_'+(i+2));
   if(typeof raw!=='string'||raw.length>65536||sha(raw)!==p.link_sha256)return fail('B5_LINK_BYTES_'+(i+2));
   const link=JSON.parse(raw);
   if(!link||typeof link!=='object'||Array.isArray(link)||Object.keys(t.link).some(k=>link[k]!==t.link[k]))return fail('B5_LINK_SCOPE_'+(i+2));
   const answer=t.canonical.rows.at(-1).content;
   if(!answer||p.answer_sha256!==sha(answer))return fail('B5_ANSWER_'+(i+2));
  }
  return {...base,status:'CONSISTENT_PHYSICAL_RETAINED_PAIR_ONLY',ack_allowed:false};
 }catch{return fail('B5_INVALID_INPUT');}
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
 const cases=[['valid',x=>{},true],['missing receipt',x=>x.receipts.receipt_payloads.pop(),false],['modified raw',x=>x.receipts.receipt_payloads[0]+=' ',false],['wrong digest',x=>x.receipts.receipt_index[0].sha256=h(91),false],['foreign weights both turns',x=>x.turns.forEach(t=>coherent(t,'weights_manifest_sha256',h(92))),false],['foreign tokenizer turn3',x=>coherent(x.turns[1],'tokenizer_manifest_sha256',h(93)),false],['foreign process',x=>coherent(x.turns[1],'process',{boot_id:'other',pid:42,start_ticks:123}),false],['foreign model',x=>coherent(x.turns[0],'model_id','other'),false],['foreign route',x=>coherent(x.turns[0],'route','/other'),false],['foreign checkpoint',x=>coherent(x.turns[0],'original_checkpoint_sha256',h(94)),false],['foreign admission',x=>coherent(x.turns[0],'owner_admission_receipt_sha256',h(95)),false],['foreign window',x=>coherent(x.turns[1],'window_end_ms',201),false],['wire drift',x=>{x.turns[1].wire.server_sha256=x.turns[1].mapping.server_sha256=h(96)},false],['conversation drift',x=>{const t=x.turns[1];for(const o of [t.scope,t.mapping,t.terminal,t.link])o.conversation_id='other'},false],['exchange map drift',x=>{x.turns[1].mapping.exchange_bindings[0].exchange_id='other'},false],['reordered turns',x=>x.turns.reverse(),false],['wrong terminal request',x=>x.turns[1].terminal.request_id='other',false],['foreign terminal browser build',x=>x.turns[1].link.served_sha256=h(99),false],['wrong saved status',x=>x.turns[1].terminal.status='TERMINAL_SAVED',false],['foreign canonical dialog',x=>{const t=x.turns[1];t.link.s03_dialog_id='other';for(const o of [t.canonical.writer,t.canonical.readback,...t.canonical.rows,...t.canonical.readback.messages])o.dialog_id='other';},false],['foreign canonical session',x=>{const t=x.turns[1];t.link.s03_session_id='other';for(const o of [t.canonical.writer,t.canonical.readback,...t.canonical.rows,...t.canonical.readback.messages])o.session_id='other';},false],['rewritten previous assistant',x=>{const t=x.turns[1];t.canonical.rows[3].content=t.canonical.readback.messages[3].content='foreign';},false],['rewritten previous user',x=>{const t=x.turns[1];t.canonical.rows[2].content=t.canonical.readback.messages[2].content='foreign';},false],['rewritten earlier message id',x=>{const t=x.turns[1];t.canonical.rows[0].message_id=t.canonical.readback.messages[0].message_id='other';},false],['reordered same-role prefix rows',x=>{const t=x.turns[1];for(const r of [t.canonical.rows,t.canonical.readback.messages])[r[0],r[2]]=[r[2],r[0]];},false]];
 let reproduced=0;
 const results=cases.map(([name,mutate,want])=>{const x=copy(fixture);mutate(x);const separately=r66.check(x.receipts).consistent&&x.turns.every(t=>r70.check(t).consistent);const z=check(x);if(!want&&separately)reproduced++;if(z.consistent!==want||z.native_accepted!==false||z.authentication_verified!==false||z.next_post_allowed!==false)throw Error(name+JSON.stringify(z));return {name,separately,consistent:z.consistent,reason:z.reason||null};});
 if(reproduced<10)throw Error('missing differential reproduction '+reproduced);
 const flags={authentication_verified:false,native_accepted:false,ack_allowed:false,next_post_allowed:false};
 const makePair=x=>({status:'S03_PROJECTION_PAIR_MATCHED_OFFLINE',...flags,turns:x.turns.map((t,i)=>({status:'S03_PROJECTION_MATCHED_OFFLINE',sequence:i+2,writer_sha256:t.canonical.writer_sha256,readback_sha256:t.canonical.readback_sha256,link_sha256:sha(JSON.stringify(t.link)),answer_sha256:sha(t.canonical.rows.at(-1).content),...flags}))});
 const retainedCases=[
 ['same independently supplied pair',()=>{},true],
 ['different writer witness',(_x,p)=>p.turns[1].writer_sha256=h(91),false],
 ['different readback witness',(_x,p)=>p.turns[0].readback_sha256=h(92),false],
 ['different answer digest',(_x,p)=>p.turns[1].answer_sha256=h(93),false],
 ['different raw link',(_x,_p,l)=>l[0]+=' ',false],
 ['coherently repinned foreign attempt',(_x,p,l)=>{const v=JSON.parse(l[1]);v.attempt_id='foreign';l[1]=JSON.stringify(v);p.turns[1].link_sha256=sha(l[1]);},false],
 ['swapped B5 results',(_x,p)=>p.turns.reverse(),false],
 ['truncated B5 result',(_x,p)=>p.turns.pop(),false],
 ['B5 authority escalation',(_x,p)=>p.ack_allowed=true,false],
 ['turn authority escalation',(_x,p)=>p.turns[1].native_accepted=true,false],
 ['B3 coherent changed answer',x=>{const t=x.turns[1];t.canonical.rows.at(-1).content=t.canonical.readback.messages.at(-1).content='foreign';},false],
 ['B3 coherent changed terminal attempt',x=>{const t=x.turns[1];t.link.attempt_id=t.terminal.attempt_id='foreign';},false]
 ];
 const retained=retainedCases.map(([name,mutate,want])=>{
  const x=copy(fixture),p=makePair(x),l=x.turns.map(t=>JSON.stringify(t.link));
  mutate(x,p,l);
  const standalone=check(x).consistent,z=checkRetainedPair(x,p,l);
  if(!standalone||z.consistent!==want||z.native_accepted!==false||z.authentication_verified!==false||z.ack_allowed!==false||z.next_post_allowed!==false)throw Error(name+JSON.stringify(z));
  return {name,standalone,consistent:z.consistent,reason:z.reason||null};
 });
 return {results,reproduced,retained,native_accepted:false};
}
module.exports={check,checkRetainedPair,selfTest};
if(require.main===module)console.log(JSON.stringify(selfTest(),null,2));
