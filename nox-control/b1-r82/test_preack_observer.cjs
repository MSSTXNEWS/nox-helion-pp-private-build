// Source regression; synthetic DOM/authority, no real ACK or native evidence.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto').webcrypto;
const bundle=fs.readFileSync(__dirname+'/b1_browser_bundle.js','utf8');
const root={crypto,TextEncoder,TextDecoder};
vm.runInNewContext(bundle,root);
const sha=async s=>Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))).toString('hex');
(async()=>{
const cases=[];
const sc={conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'dialog',session_id:'session',served_sha256:'ab'.repeat(32),server_sha256:'cd'.repeat(32),owner_admission_receipt_sha256:'ef'.repeat(32)};
for(const n of [2,3]){
const text=n===2?'Привет 🌞 ¡Hola!':'¿Qué tal? — отлично';
const hash=await sha(text),s={conversation_id:'conv',exchange_id:'ex'+n};
const proof={physical_dialog_id:'physical',s03_dialog_id:'dialog',s03_session_id:'session',served_sha256:sc.served_sha256,sequence:n,request_id:'req'+n,attempt_id:'att'+n,s03_event_id:'evt'+n,s03_turn_id:'turn'+n,assistant_message_id:'assistant'+n,answer_sha256:hash};
const t={turn:n,exchange_id:s.exchange_id,request_id:proof.request_id,attempt_id:proof.attempt_id,event_id:proof.s03_event_id,turn_id:proof.s03_turn_id,user_message_id:'user'+n,assistant_message_id:proof.assistant_message_id,answer_sha256:hash,state:'TERMINAL_SAVED',eof:true};
const el={dataset:{noxB1Conversation:'conv',noxB1Exchange:s.exchange_id,noxB1EventId:'projection'+n,noxB1State:'terminal'},isConnected:true,childElementCount:0,textContent:text,hidden:false,getAttribute:()=>null,getClientRects:()=>[{}],parentElement:null};
const container={isConnected:true,children:[el],ownerDocument:{defaultView:{getComputedStyle:()=>({display:'block',visibility:'visible',opacity:'1'})}}};
const context={scope:sc,terminal:t,browser_sha256:'12'.repeat(32),terminal_receipt_sha256:'34'.repeat(32),ack_state:'NOT_SENT'};
let retained=[],mutate=null;
const host={readPreAckContext:async()=>context,retainPreAckObservation:async pair=>{retained.push(pair);if(mutate)mutate();return true;}};
const observe=root.NOXB1PreAckObserver.create({container,host,crypto});
const w={projection_event_id:'projection'+n};
const run=()=>observe(s,proof,w,new AbortController().signal);
assert.equal(await run(),true);const pair=retained.pop(),doc=JSON.parse(pair.bytes);assert.equal(pair.sha256,await sha(pair.bytes));assert.equal(doc.visible_text_sha256,hash);assert.equal(doc.turn,n);assert.equal(Object.keys(doc).length,23);cases.push('turn'+n);
el.hidden=true;await assert.rejects(run());el.hidden=false;
container.children.push(el);await assert.rejects(run());container.children.pop();
el.textContent+='!';await assert.rejects(run());el.textContent=text;
t.attempt_id='foreign';await assert.rejects(run());t.attempt_id=proof.attempt_id;
context.ack_state='SENDING';assert.equal(await run(),false);context.ack_state='NOT_SENT';
const stop=new AbortController();stop.abort();await assert.rejects(()=>observe(s,proof,w,stop.signal));
assert.equal(retained.length,0);
mutate=()=>{el.textContent='changed'};await assert.rejects(run());cases.push('negative'+n);
}
assert.ok(bundle.indexOf('observed=await boundedRead')<bundle.indexOf('()=>ackGate.reserve'));
assert.ok(bundle.indexOf("if(observePreAck&&observed!==true)")<bundle.indexOf('()=>ackGate.beginSend'));
console.log('B1_R82 source observer PASS '+cases.join(',')+'; native=false');
})().catch(e=>{console.error(e);process.exitCode=1});
