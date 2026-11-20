'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { acceptTerminal, HoldClientReconnect } = require('./b1_client_reconnect_dedup_bridge.js');
const H = 'a'.repeat(64), R = 'b'.repeat(64), S = 'c'.repeat(64);
const cursor = 'SIGNED_TEST_CURSOR_NOT_A_REAL_SIGNATURE';
function packet(exchange='x1', emit_terminal=true) {
  return {readback_only:true, emit_terminal, conversation_id:'conversation-1',
    exchange_id:exchange, event_id:exchange==='x1'?H:'d'.repeat(64),
    next_cursor:cursor+(exchange==='x1'?'1':'2'),
    response_sha256:R, s03_proof_sha256:S};
}
function fixture() {
  const db = new Map(), calls = { model_post:0, atomic:0, verify:0, gate:0 };
  const host = {
    async authorizeEnvelope() {calls.verify++; return true;},
    async freshPermit() {calls.gate++; return true;},
    async commitTerminalAndAck(p) {
      calls.atomic++;
      const k = p.conversation_id + '/' + p.exchange_id;
      const old = db.get(k);
      if (old) return 'ALREADY_COMMITTED'; // external unique key; bridge compares witness
      db.set(k, {...p, durable:true});
      return 'COMMITTED';
    },
    async readCommitted(conversation, exchange) {return db.get(conversation + '/' + exchange);}
  };
  const expected = (exchange='x1')=>({conversation_id:'conversation-1',exchange_id:exchange});
  return {db,calls,host,expected};
}
async function rejects(code, fn) {await assert.rejects(fn, e=>e instanceof HoldClientReconnect && e.code===code);}

test('one terminal, lost ACK replay and consumed cursor never duplicate durable turn', async()=>{
  const f=fixture(), p=packet();
  const a=await acceptTerminal(p,f.expected(),f.host);
  const b=await acceptTerminal(p,f.expected(),f.host); // lost ACK, same event_id
  const c=await acceptTerminal(packet('x1',false),f.expected(),f.host);
  assert.equal(a.safe_to_ack,true); assert.equal(a.model_post,false);
  assert.equal(a.projection_event_id,b.projection_event_id);
  assert.equal(a.ack_cursor,c.ack_cursor);
  assert.equal(f.db.size,1); assert.equal(f.calls.model_post,0);
});

test('same dialog two exchanges remain separate with no cross-turn cursor', async()=>{
  const f=fixture();
  await acceptTerminal(packet('x1'),f.expected('x1'),f.host);
  await acceptTerminal(packet('x2'),f.expected('x2'),f.host);
  assert.equal(f.db.size,2);
  await rejects('HOLD_CLIENT_CROSS_TURN',()=>acceptTerminal(packet('x1'),f.expected('x2'),f.host));
});

test('server terminal ACK without locally committed event fails closed', async()=>{
  const f=fixture();
  await rejects('HOLD_CLIENT_ACK_WITNESS',()=>acceptTerminal(packet('x1',false),f.expected(),f.host));
});

test('same exchange with changed server event id or S03 hash never acknowledged', async()=>{
  const f=fixture();
  await acceptTerminal(packet(),f.expected(),f.host);
  const bad={...packet(),event_id:'e'.repeat(64)};
  await rejects('HOLD_CLIENT_ACK_WITNESS',()=>acceptTerminal(bad,f.expected(),f.host));
  await rejects('HOLD_CLIENT_ACK_WITNESS',()=>acceptTerminal({...packet(),s03_proof_sha256:'f'.repeat(64)},f.expected(),f.host));
  assert.equal(f.db.size,1);
});

test('tamper, missing proof, missing atomic contract block before commit', async()=>{
  const f=fixture();
  await rejects('HOLD_CLIENT_NOT_READBACK',()=>acceptTerminal({...packet(),readback_only:false},f.expected(),f.host));
  await rejects('HOLD_CLIENT_EVENT_ID',()=>acceptTerminal({...packet(),event_id:'not-hex'},f.expected(),f.host));
  await rejects('HOLD_CLIENT_CURSOR',()=>acceptTerminal({...packet(),next_cursor:'bad!'},f.expected(),f.host));
  await rejects('HOLD_CLIENT_HOST_CONTRACT',()=>acceptTerminal(packet(),f.expected(),{...f.host,commitTerminalAndAck:null}));
  assert.equal(f.calls.atomic,0);
});

test('owner revoked or proof unverified means no ACK even if existing', async()=>{
  const f=fixture();
  f.host.authorizeEnvelope=async()=>false;
  await rejects('HOLD_CLIENT_UNVERIFIED',()=>acceptTerminal(packet(),f.expected(),f.host));
  f.host.authorizeEnvelope=async()=>true;
  const gates=[true,true,false]; f.host.freshPermit=async()=>gates.shift();
  await rejects('HOLD_CLIENT_OWNER_REVOKED',()=>acceptTerminal(packet(),f.expected(),f.host));
});

test('callback mutation cannot change frozen scope or store identity', async()=>{
  const f=fixture(); const p=packet();
  f.host.authorizeEnvelope=async snapshot=>{p.exchange_id='forged'; assert.equal(snapshot.exchange_id,'x1'); return true;};
  const result=await acceptTerminal(p,f.expected(),f.host);
  assert.equal(result.exchange_id,'x1');
  assert.equal(f.db.size,1);
});

test('atomic commit and IO failures are HOLD, never auto-infer or auto-POST', async()=>{
  const f=fixture();
  f.host.commitTerminalAndAck=async()=>{throw Error('db down');};
  await rejects('HOLD_CLIENT_CALLBACK_OR_STORE',()=>acceptTerminal(packet(),f.expected(),f.host));
  f.host.commitTerminalAndAck=async()=>false;
  await rejects('HOLD_CLIENT_ATOMIC_COMMIT',()=>acceptTerminal(packet(),f.expected(),f.host));
  assert.equal(f.calls.model_post,0);
});

test('concurrent duplicate reconnect uses one durable unique-key projection', async()=>{
  const f=fixture();
  const results=await Promise.all(Array.from({length:8},()=>acceptTerminal(packet(),f.expected(),f.host)));
  assert.equal(f.db.size,1);
  assert.equal(new Set(results.map(v=>v.projection_event_id)).size,1);
  assert.equal(new Set(results.map(v=>v.ack_cursor)).size,1);
});
