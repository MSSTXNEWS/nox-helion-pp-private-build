'use strict';
const assert=require('node:assert/strict');
const {test}=require('node:test');
const {openClientAckHost,HoldIndexedAck}=require('./b1_client_ack_indexeddb_store.js');
const {acceptTerminal,HoldClientReconnect}=require('./b1_client_reconnect_dedup_bridge.js');
const H='a'.repeat(64), R='b'.repeat(64), S='c'.repeat(64);
const packet=(ex='x1',event=H,emit=true)=>({
  readback_only:true,emit_terminal:emit,conversation_id:'dialog-1',
  exchange_id:ex,event_id:event,next_cursor:'signed_synthetic_cursor_1',
  response_sha256:R,s03_proof_sha256:S
});
const expected=(ex='x1')=>({conversation_id:'dialog-1',exchange_id:ex});
const wait=fn=>setImmediate(fn);

/* Small isolated IDB behavioral double. It schedules IDBRequest callbacks,
 * supports readwrite transactions, compound keys and unique event_id.
 * This does NOT substitute for actual browser IndexedDB or production tests. */
function fakeIDB() {
  const registry=new Map();
  return {open(name,version) {
    const request={result:null,transaction:{abort(){}},onupgradeneeded:null,
                   onsuccess:null,onerror:null,onblocked:null};
    wait(()=>{
      let state=registry.get(name),oldVersion=state?1:0;
      if(!state){state={rows:new Map(),schema:null};registry.set(name,state);}
      const db={
        objectStoreNames:{contains:k=>!!state.schema && state.schema.name===k},
        createObjectStore(k,opts) {
          if(state.schema) throw Error('exists');
          const schema={name:k,keyPath:opts.keyPath,unique:false,indexName:null};
          state.schema=schema;
          return {createIndex:(name,key,opts)=>{schema.indexName=name;
                   schema.indexKey=key;schema.unique=opts.unique;}};
        },
        transaction(k,mode) {
          if(!state.schema || state.schema.name!==k) throw Error('no store');
          let pending=0,abort=false,finished=false;
          const tx={oncomplete:null,onabort:null,onerror:null,
            abort(){if(!abort&&!finished){abort=true;wait(()=>tx.onabort?.());}},
            objectStore(){
              const schema=state.schema;
              function requestOp(fn) {
                const req={result:null,onsuccess:null,onerror:null};
                pending++;
                wait(()=>{
                  try {
                    if(!abort){req.result=fn();req.onsuccess?.({target:req});}
                  } catch(_) {req.onerror?.({target:req});tx.abort();}
                  pending--;
                  if(pending===0) wait(()=>{
                    if(!abort&&!finished){finished=true;tx.oncomplete?.();}
                  });
                });
                return req;
              }
              return {
                keyPath:schema.keyPath,
                indexNames:{contains:n=>schema.indexName===n},
                index:n=>{if(n!==schema.indexName)throw Error('index');
                          return {keyPath:schema.indexKey,unique:schema.unique};},
                get:pair=>requestOp(()=>state.rows.get(JSON.stringify(pair))),
                add:row=>requestOp(()=>{
                  if(mode!=='readwrite')throw Error('readonly');
                  const key=JSON.stringify([row.conversation_id,row.exchange_id]);
                  if(state.rows.has(key))throw Error('duplicate key');
                  if(schema.unique && [...state.rows.values()].some(x=>x.event_id===row.event_id))
                    throw Error('duplicate event');
                  state.rows.set(key,structuredClone(row));return key;
                })
              };
            }
          };return tx;
        },
        close(){}
      };
      request.result=db;
      if(oldVersion===0) request.onupgradeneeded?.({oldVersion});
      request.onsuccess?.({target:request});
    });
    return request;
  }};
}
async function host(idb,permitted=async()=>true) {
  return openClientAckHost({indexedDB:idb,databaseName:'b1-test',
    authorizeEnvelope:async()=>true,freshPermit:permitted});
}
async function rejects(code,fn,Class=HoldClientReconnect) {
  await assert.rejects(fn,e=>e instanceof Class&&e.code===code);
}
test('two distinct turns survive close/open, lost ACK never adds a third turn',async()=>{
  const idb=fakeIDB(); const h=await host(idb);
  const a=await acceptTerminal(packet(),expected(),h);
  const b=await acceptTerminal(packet(),expected(),h);
  assert.equal(a.projection_event_id,b.projection_event_id);
  await acceptTerminal(packet('x2','d'.repeat(64)),expected('x2'),h);
  h.close();
  const restarted=await host(idb);
  const resumed=await acceptTerminal(packet('x1',H,false),expected(),restarted);
  assert.equal(resumed.ack_cursor,a.ack_cursor);
  assert.equal((await restarted.readCommitted('dialog-1','x1')).event_id,H);
  assert.equal((await restarted.readCommitted('dialog-1','x2')).event_id,'d'.repeat(64));
  restarted.close();
});
test('same pair changed proof and alias event across exchanges fail closed',async()=>{
  const idb=fakeIDB(),h=await host(idb);
  await acceptTerminal(packet(),expected(),h);
  await rejects('HOLD_CLIENT_CALLBACK_OR_STORE',
    ()=>acceptTerminal({...packet(),s03_proof_sha256:'e'.repeat(64)},expected(),h));
  await rejects('HOLD_CLIENT_CALLBACK_OR_STORE',
    ()=>acceptTerminal(packet('x2',H),expected('x2'),h));
  assert.equal(await h.readCommitted('dialog-1','x2'),null);
  h.close();
});
test('revoked owner, missing authenticator and malformed packets never acknowledge',async()=>{
  const idb=fakeIDB();
  await rejects('HOLD_ACK_HOST_CONTRACT',
    ()=>openClientAckHost({indexedDB:idb,databaseName:'b1-test'}),
    HoldIndexedAck);
  const h=await host(idb,async()=>false);
  await rejects('HOLD_CLIENT_OWNER_REVOKED',()=>acceptTerminal(packet(),expected(),h));
  assert.equal(await h.readCommitted('dialog-1','x1'),null);
  await rejects('HOLD_ACK_PACKET',()=>h.commitTerminalAndAck({...packet(),readback_only:false}),HoldIndexedAck);
  h.close();
});
test('close and corrupted key names fail closed without replay',async()=>{
  const idb=fakeIDB(),h=await host(idb); h.close();
  await rejects('HOLD_ACK_CLOSED',()=>h.commitTerminalAndAck(packet()),HoldIndexedAck);
  await rejects('HOLD_ACK_DB_NAME',
    ()=>openClientAckHost({indexedDB:idb,databaseName:'illegal name',
        authorizeEnvelope:async()=>true,freshPermit:async()=>true}),HoldIndexedAck);
});
