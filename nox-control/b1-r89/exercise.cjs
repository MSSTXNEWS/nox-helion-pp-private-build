async () => {
 if(!isSecureContext || !crypto.subtle) throw Error('secure browser required');
 const root=window;
 const hash=async x=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(x))),b=>b.toString(16).padStart(2,'0')).join('');
 const pair=async x=>{const b=JSON.stringify(x);return [b,await hash(b)]};
 const assert={equal:(a,b,m)=>{if(a!==b)throw Error((m||'assert')+': '+a+' != '+b)}};
 const results=[];
 let count=0;
 for(const n of [2,3])for(const fault of ['ok','pending','bad-pin','foreign','unverified','no-recheck','stop','changed','timeout','historical','missing','begin-hide','begin-replace','begin-stop','verify-hide','verify-stop']){
  const s={conversation_id:'conv',exchange_id:'ex'+n},visible=n===2?'Привет 🌞':'¡Hola! 🐾',digest=await hash(visible);
  const proof={schema:'NOX_B5_CANONICAL_ASSISTANT_TEXT_V1',...s,physical_dialog_id:'physical',s03_dialog_id:'dialog',s03_session_id:'session',served_sha256:'ab'.repeat(32),sequence:n,request_id:'req'+n,attempt_id:'att'+n,s03_event_id:'evt'+n,s03_turn_id:'turn'+n,assistant_message_id:'assistant'+n,assistant_text:visible,answer_sha256:digest,writer_sha256:'ac'.repeat(32),readback_sha256:'ad'.repeat(32),link_sha256:'ae'.repeat(32)};
  const container=document.querySelector('#chat');
  for(const old of Array.from(container.children))if(old.dataset.noxB1Exchange===s.exchange_id)old.remove();
  const el=document.createElement('div');
  Object.assign(el.dataset,{noxB1Conversation:'conv',noxB1Exchange:s.exchange_id,noxB1EventId:'projection'+n,noxB1State:'terminal'});
  el.textContent=visible;container.append(el);
  assert.equal(el.getClientRects().length>0,true,'visible');
  const context={scope:{conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'dialog',session_id:'session',served_sha256:proof.served_sha256,server_sha256:'cd'.repeat(32),owner_admission_receipt_sha256:'ef'.repeat(32)},terminal:{turn:n,exchange_id:s.exchange_id,request_id:proof.request_id,attempt_id:proof.attempt_id,event_id:proof.s03_event_id,turn_id:proof.s03_turn_id,user_message_id:'user'+n,assistant_message_id:proof.assistant_message_id,answer_sha256:digest,state:'TERMINAL_SAVED',eof:true},browser_sha256:'12'.repeat(32),terminal_receipt_sha256:'34'.repeat(32),ack_state:fault==='historical'?'SENDING':'NOT_SENT'};
  let posts=0,acks=0,retained=0,begins=0,finals=0,verified=0,client;
  const host={readCommitted:async()=>null,verifyCanonicalText:async()=>true,verifyCanonicalAck:async()=>false,verifyFreshCanonicalAck:async()=>false,readPreAckContext:async()=>context,retainPreAckObservation:async()=>{retained++;return true},
   requestFinalDisposition:async({observation,recheck},signal)=>{
    finals++;if(fault==='timeout')return new Promise(()=>{});
    if(fault!=='no-recheck')recheck();
    const {schema,visible_text_sha256,visible_row_count,state,ack_state,...common}=JSON.parse(observation.bytes);
    common.observation_sha256=observation.sha256;
    const reservation=await pair({...common,schema:'nox.browser.ack-reservation-readback.v1',reservation_id:'reserve'+n,state:'RESERVED_NOT_SENT'});
    const disposition=await pair({...common,schema:'nox.browser.projection-disposition.v1',reservation_id:'reserve'+n,reservation_sha256:reservation[1],disposition_id:'final'+n,state:fault==='pending'?'PENDING':'FINALIZED',dom_recheck:'MATCHED',stop_recheck:'CLEAR',...(fault==='foreign'?{request_id:'foreign'}:{})});
    if(fault==='bad-pin')disposition[1]='ab'.repeat(32);
    if(fault==='stop')client.stop(s);if(fault==='changed')el.textContent+='!';
    return {reservation,disposition};
   },verifyFinalDisposition:async()=>{verified++;if(fault==='verify-hide')el.hidden=true;if(fault==='verify-stop')client.stop(s);return fault!=='unverified'}};
  if(fault==='missing')delete host.requestFinalDisposition;
  const transport={post:async()=>{posts++;throw Error('POST forbidden')},readback:async()=>({...s,canonical_assistant_text:proof}),ack:async()=>{acks++;return true},readCanonicalAck:async()=>{throw Error('no fixture authority')}};
  const ackGate={reserve:async()=>{if(fault==='historical')throw Object.assign(Error('uncertain'),{code:'HOLD_CROSSTAB_ACK_UNCERTAIN'});return {status:'RESERVED'}},beginSend:async()=>{begins++;if(fault==='begin-hide')el.hidden=true;if(fault==='begin-replace')el.replaceWith(el.cloneNode(true));if(fault==='begin-stop')client.stop(s);return 'SENDING'},confirm:async()=>{},requireCanonicalAck:async()=>{throw Error('fixture authority absent')}};
  client=root.NOXB1StreamReconnect.createClient({transport,host,bridge:{acceptTerminal:async packet=>({...packet,safe_to_ack:true,model_post:false,projection_event_id:'projection'+n,ack_cursor:'cursor'+n})},ui:{onDelta:async()=>true,upsertTerminal:async()=>true},ackGate,observePreAck:root.NOXB1PreAckObserver.create({container,host}),reconnectReadTimeoutMs:500});
  let status;try{await client.reconnect(s)}catch(e){status=e.code}
  const expected=fault==='ok'?1:0;
  assert.equal(acks,expected,n+' '+fault+' '+status);
  assert.equal(begins,(expected||fault.startsWith('begin-'))?1:0,n+' '+fault+' begin');
  assert.equal(posts,0);assert.equal(retained,fault==='historical'?0:1);
  assert.equal(finals,['historical','missing'].includes(fault)?0:1);
  if(fault==='ok')assert.equal(verified,1);
  count++;results.push({n,fault,acks,begins,status});
 }
 return {count,results,rows:document.querySelector('#chat').children.length,real_dom:true,real_webcrypto:true,authority:'fixture',native_accepted:false,live_post:0,live_ack:0};
}
