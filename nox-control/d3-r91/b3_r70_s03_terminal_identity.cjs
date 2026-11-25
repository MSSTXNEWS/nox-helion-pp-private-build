'use strict';
// Offline linkage only. Inputs must be independently authenticated by owner:
// R76 frozen binding, actual transport scope/attempt, explicit cross-system link,
// and B5 retained canonical writer/readback pair with detached digests.
// A successful comparison is NOT evidence of authentication or chain acceptance.
const r69=require('./b3_r69_exchange_scope_binding.cjs');
function check({wire,physical,mapping,scope,expectedTurn,terminal,link,canonical}={}){
 const fail=reason=>({status:'HOLD',reason,consistent:false,authentication_verified:false,native_accepted:false,next_post_allowed:false});
 const id=x=>typeof x==='string'&&x.length>0&&x.length<=160&&x===x.trim()&&!/[\x00-\x1f\x7f]/.test(x);
 const hash=x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x)&&!/^(.)\1+$/.test(x);
 const prior=r69.check({wire,physical,mapping,scope,expectedTurn});
 if(!prior.consistent)return fail('R69_'+prior.reason);
 if(!terminal||!link||!canonical||link.schema!=='NOX_B3_S03_TERMINAL_LINK_V1')return fail('LINK_REQUIRED');
 // R75 EOF only starts canonical readback; never promote it to an ACK.
 if(terminal.status!=='STREAM_ENDED_READBACK_REQUIRED'||terminal.sequence!==expectedTurn||link.sequence!==expectedTurn)return fail('TERMINAL_SCOPE');
 const actual={conversation_id:scope.conversation_id,exchange_id:scope.exchange_id,physical_dialog_id:physical.dialog_id,request_id:physical.turn_request_ids[expectedTurn-2]};
 for(const [k,v] of Object.entries(actual))if(!id(v)||terminal[k]!==v||link[k]!==v)return fail('EXCHANGE_'+k);
 if(!id(terminal.attempt_id)||link.attempt_id!==terminal.attempt_id)return fail('ATTEMPT');
 const {writer,readback,rows,writer_sha256,readback_sha256}=canonical;
 if(!writer||!readback||!Array.isArray(rows)||rows.length!==2*expectedTurn)return fail('CANONICAL_PAIR');
 if(writer.source!=='canonical_s03'||readback.source!=='canonical_s03'||writer.verified!==true||writer.durable!==true||readback.independent!==true)return fail('CANONICAL_WITNESS');
 if(!hash(writer_sha256)||!hash(readback_sha256)||writer_sha256===readback_sha256||link.writer_sha256!==writer_sha256||link.readback_sha256!==readback_sha256)return fail('DETACHED_PINS');
 for(const [key,lk] of [['dialog_id','s03_dialog_id'],['session_id','s03_session_id'],['turn_id','s03_turn_id'],['event_id','s03_event_id']]){
  if(!id(link[lk])||writer[key]!==link[lk]||readback[key]!==link[lk])return fail('S03_'+key);
 }
 if(writer.sequence!==expectedTurn||readback.sequence!==expectedTurn)return fail('S03_SEQUENCE');
 if(!Array.isArray(readback.messages)||readback.messages.length!==rows.length)return fail('S03_ROWS');
 const seen=new Set();
 for(let i=0;i<rows.length;i++){
  const row=rows[i],observed=readback.messages[i],role=i%2?'assistant':'user';
  if(!row||!observed||!id(row.message_id)||seen.has(row.message_id)||row.dialog_id!==link.s03_dialog_id||row.session_id!==link.s03_session_id||row.role!==role||typeof row.content!=='string')return fail('S03_ROW_SCOPE');
  for(const key of ['message_id','dialog_id','session_id','role','content'])if(row[key]!==observed[key])return fail('S03_ROW_READBACK');
  seen.add(row.message_id);
 }
 if(!id(link.user_message_id)||!id(link.assistant_message_id)||link.user_message_id!==rows.at(-2).message_id||link.assistant_message_id!==rows.at(-1).message_id)return fail('S03_MESSAGE_PAIR');
 return {status:'CONSISTENT_TERMINAL_LINK_ONLY',consistent:true,authentication_verified:false,native_accepted:false,next_post_allowed:false,requires_external_verifier:true,requires_b5_retained_chain:true};
}
function selfTest(){
 const h=n=>n.toString(16).padStart(64,'0');
 function fixture(n){
  const wire={wire:'named-delta-stable-server-id-v1',route:'logical-route',served_sha256:h(21),server_sha256:h(22)};
  const physical={route:'/fixture/model',model_id:'fixture',dialog_id:'physical-dialog',weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:'c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7',original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:'boot',pid:42,start_ticks:123},turn_request_ids:['physical-request-2','physical-request-3'],window_start_ms:100,window_end_ms:200};
  const mapping={...JSON.parse(JSON.stringify(physical)),schema:'NOX_B3_ROUTE_BINDING_V1',wire:wire.wire,symbolic_route:wire.route,served_sha256:wire.served_sha256,server_sha256:wire.server_sha256,conversation_id:'logical-conversation',exchange_bindings:[{turn:2,request_id:'physical-request-2',exchange_id:'logical-exchange-2'},{turn:3,request_id:'physical-request-3',exchange_id:'logical-exchange-3'}]};
  const scope={conversation_id:'logical-conversation',exchange_id:'logical-exchange-'+n};
  const terminal={...scope,physical_dialog_id:physical.dialog_id,request_id:physical.turn_request_ids[n-2],attempt_id:'attempt-'+n,sequence:n,status:'STREAM_ENDED_READBACK_REQUIRED'};
  const rows=Array.from({length:2*n},(_,i)=>({role:i%2?'assistant':'user',content:'fixture '+i,message_id:'msg-'+i,dialog_id:'canonical-dialog',session_id:'canonical-session'}));
  const common={source:'canonical_s03',event_id:'event-'+n,turn_id:'turn-'+n,sequence:n,dialog_id:'canonical-dialog',session_id:'canonical-session'};
  const canonical={writer:{...common,verified:true,durable:true},readback:{...common,independent:true,messages:JSON.parse(JSON.stringify(rows))},rows,writer_sha256:h(30+n),readback_sha256:h(40+n)};
  const link={schema:'NOX_B3_S03_TERMINAL_LINK_V1',...terminal,s03_dialog_id:common.dialog_id,s03_session_id:common.session_id,s03_event_id:common.event_id,s03_turn_id:common.turn_id,user_message_id:rows.at(-2).message_id,assistant_message_id:rows.at(-1).message_id,writer_sha256:canonical.writer_sha256,readback_sha256:canonical.readback_sha256};
  return {wire,physical,mapping,scope,expectedTurn:n,terminal,canonical,link};
 }
 const mutations=[
 ['valid distinct IDs',x=>{},true],['missing link',x=>delete x.link,false],['foreign attempt',x=>x.terminal.attempt_id='foreign',false],['foreign exchange',x=>x.terminal.exchange_id='foreign',false],['foreign physical request',x=>x.terminal.request_id='foreign',false],['wrong session',x=>x.canonical.readback.session_id='foreign',false],['foreign canonical dialog',x=>x.canonical.writer.dialog_id='foreign',false],['guessed physical equals canonical',x=>x.link.s03_dialog_id=x.physical.dialog_id,false],['wrong canonical turn',x=>x.canonical.writer.turn_id='foreign',false],['wrong canonical event',x=>x.canonical.readback.event_id='foreign',false],['wrong user ID',x=>x.link.user_message_id='foreign',false],['wrong assistant ID',x=>x.link.assistant_message_id='foreign',false],['previous pair reused',x=>x.link.user_message_id=x.canonical.rows[0].message_id,false],['coherent duplicate row ID',x=>{x.canonical.rows.at(-1).message_id=x.canonical.rows[0].message_id;x.canonical.readback.messages.at(-1).message_id=x.canonical.rows[0].message_id;x.link.assistant_message_id=x.canonical.rows[0].message_id;},false],['changed readback content',x=>x.canonical.readback.messages[0].content='foreign',false],['missing independent readback',x=>x.canonical.readback.independent=false,false],['wrong detached pin',x=>x.link.writer_sha256=h(99),false],['same witness pins',x=>x.link.readback_sha256=x.canonical.readback_sha256=x.canonical.writer_sha256,false],['wrong sequence',x=>x.canonical.writer.sequence=1,false],['false completion status',x=>x.terminal.status='COMPLETED',false],['turn1 replay',x=>x.expectedTurn=1,false],['EOF without canonical pair',x=>delete x.canonical,false],['tokenizer mismatch',x=>x.physical.tokenizer_manifest_sha256=h(99),false]];
 return [2,3].flatMap(n=>mutations.map(([name,mutate,want])=>{const x=fixture(n);mutate(x);const z=check(x);if(z.consistent!==want||z.native_accepted!==false||z.authentication_verified!==false||z.next_post_allowed!==false)throw Error(n+':'+name+':'+JSON.stringify(z));return {turn:n,name,consistent:z.consistent,reason:z.reason||null};}));
}
module.exports={check,selfTest};
if(require.main===module)console.log(JSON.stringify({cases:selfTest(),native_accepted:false},null,2));
