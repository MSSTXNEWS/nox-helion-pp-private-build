#!/usr/bin/env python3
"""Real Chromium IndexedDB + GET-only synthetic canonical ACK receipt; NOT native NOX."""
import json
import os
import tempfile
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "b1_cross_tab_ack_lease.js"

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        with self.server.lock: self.server.posts += 1
        self.send_error(405)
    def do_GET(self):
        if self.path.startswith("/canonical/"):
            kind = self.path.split("/canonical/", 1)[1]
            with self.server.lock: self.server.reads += 1
            if kind == "missing":
                self.send_error(404)
                return
            exchange = "x2" if kind == "x2" else "x1"
            event = ("b" if exchange == "x2" else "a") * 64
            import hashlib
            cursor_hash = hashlib.sha256(("cursor2" if exchange == "x2" else "cursor1").encode()).hexdigest()
            proof = {"version":1,"state":"ACKED","conversation_id":"dialog",
                "exchange_id":exchange,"event_id":event,"cursor_digest":cursor_hash,
                "ack_id":"ack-"+exchange,"server_cas":"server-cas-"+exchange,
                "s03_sha256":"c"*64,"signature":"synthetic-fixture-signature"}
            if kind == "wrong-scope": proof["exchange_id"] = "other"
            if kind == "forged": proof["signature"] = "forged-fixture-signature"
            payload = json.dumps(proof).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload))); self.end_headers()
            return self.wfile.write(payload)
        return super().do_GET()

def check(label, expression):
    if not expression: raise AssertionError(label)
    print("PASS:", label, flush=True)

def trial(page, js):
    return page.evaluate("""async source => {
      try {return await (new Function('return ('+source+')'))();}
      catch(err){return err.code || err.message || String(err);}
    }""", js)

def load(page, url, database):
    page.goto(url)
    page.add_script_tag(path=str(SOURCE))
    page.evaluate("""async name => {
      window.s1={conversation_id:'dialog',exchange_id:'x1'};
      window.s2={conversation_id:'dialog',exchange_id:'x2'};
      window.a='a'.repeat(64);window.b='b'.repeat(64);
      window.gate=await NOXB1CrossTabAckLease.createGate({
        indexedDB,databaseName:name,ttlMs:300
      });
      window.read=kind=>async expected=>{
        const res=await fetch('/canonical/'+kind, {method:'GET',cache:'no-store'});
        if(!res.ok)throw Error('CANONICAL_READ_UNAVAILABLE');
        return res.json();
      };
      // Fixture verifier only: production MUST cryptographically verify a
      // signed ACK, live owner/CAS state, immutable S03 and scoped freshness.
      window.verify=async (receipt, expected)=>Object.isFrozen(receipt)
        && Object.isFrozen(expected)
        && receipt.signature==='synthetic-fixture-signature'
        && receipt.s03_sha256==='c'.repeat(64)
        && receipt.server_cas==='server-cas-'+receipt.exchange_id;
    }""", database)

def main():
    assert SOURCE.is_file()
    with tempfile.TemporaryDirectory(prefix="nox-b1-canonical-") as root:
        Path(root, "index.html").write_text("<!doctype html><title>NOX B1 isolated source</title>")
        srv=ThreadingHTTPServer(("127.0.0.1",0),partial(Handler,directory=root))
        srv.lock=threading.Lock();srv.posts=0;srv.reads=0
        worker=threading.Thread(target=srv.serve_forever,daemon=True);worker.start()
        try:
            with sync_playwright() as p:
                chrome=os.getenv("NOX_B1_CHROME")
                browser=p.chromium.launch(headless=True,**({"executable_path":chrome} if chrome else {}))
                ctx=browser.new_context()
                url=f"http://127.0.0.1:{srv.server_port}/index.html"
                db="nox-b1-canonical-"+uuid.uuid4().hex
                a=ctx.new_page();b=ctx.new_page()
                for tab in (a,b): load(tab,url,db)
                grant=a.evaluate("()=>gate.reserve(s1,a,'cursor1')")
                check("unique first reservation", grant["status"]=="RESERVED")
                check("SENDING persists before ACK",a.evaluate("g=>gate.beginSend(g)",grant)=="SENDING")
                check("missing canonical GET fails closed",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('missing'),verify)")=="HOLD_CROSSTAB_READBACK")
                check("wrong canonical exchange rejected",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('wrong-scope'),verify)")=="HOLD_CROSSTAB_RECEIPT_MISMATCH")
                check("unverified signature rejected",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('forged'),verify)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                check("false verifier cannot reconcile",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('x1'),()=>false)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                check("unknown SENDING never leased to other tab",
                      trial(b,"gate.reserve(s1,a,'cursor1')")=="HOLD_CROSSTAB_ACK_UNCERTAIN")
                check("authenticated fixture GET recovers without ACK retransmit",
                      a.evaluate("()=>gate.reconcileSignedAck(s1,a,'cursor1',read('x1'),verify)")["status"]=="ACKED_RECOVERED")
                check("second tab observes durable ACKED",
                      b.evaluate("()=>gate.reserve(s1,a,'cursor1')")["status"]=="ALREADY_ACKED")
                check("changed terminal proof still fails closed",
                      trial(b,"gate.reserve(s1,a,'other-cursor')")=="HOLD_CROSSTAB_CONFLICT")
                x2=a.evaluate("()=>gate.reserve(s2,b,'cursor2')")
                check("second turn has independent reserve", x2["status"]=="RESERVED")
                check("second turn in SENDING",a.evaluate("g=>gate.beginSend(g)",x2)=="SENDING")
                # Two independent IDB connections and concurrent GET witness CAS.
                states=a.evaluate("""async db => {
                  const other=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:db,ttlMs:300});
                  try {
                    const outcomes=await Promise.all([
                      gate.reconcileSignedAck(s2,b,'cursor2',read('x2'),verify),
                      other.reconcileSignedAck(s2,b,'cursor2',read('x2'),verify)
                    ]);
                    return outcomes.map(v=>v.status).sort();
                  } finally {other.close();}
                }""",db)
                check("concurrent reconciliation CAS yields one transition",
                      states==["ACKED_RECOVERED","ALREADY_ACKED"])
                # ACKED without a canonical signed proof is not equivalent to
                # independently verified server reconciliation.
                unverified=a.evaluate("""async dbName => {
                  const g=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:dbName});
                  const scope={conversation_id:'dialog',exchange_id:'x1'};
                  try {
                    const grant=await g.reserve(scope,'a'.repeat(64),'cursor1');
                    await g.beginSend(grant);
                    await g.confirm(grant); // local transport ACK, no signed server proof
                    try {
                      return await g.reconcileSignedAck(scope,'a'.repeat(64),'cursor1',
                        async()=>{throw Error('GET_MUST_NOT_RUN');},async()=>false);
                    } catch(err) {return err.code;}
                  } finally {g.close();}
                }""",db+"-local-only")
                check("local ACKED cannot spoof signed canonical ACK",
                      unverified=="HOLD_CROSSTAB_ACKED_UNVERIFIED")
                # Two async verifiers for the same exchange can see distinct
                # syntactically valid receipts. An already committed receipt
                # is NOT proof that an independent, conflicting receipt won.
                clash=a.evaluate("""async dbName => {
                  const slow=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:dbName});
                  const fast=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:dbName});
                  const scope={conversation_id:'dialog',exchange_id:'x1'};
                  let started, release;
                  const entered=new Promise(resolve=>{started=resolve;});
                  const proceed=new Promise(resolve=>{release=resolve;});
                  try {
                    const grant=await slow.reserve(scope,'a'.repeat(64),'cursor1');
                    await slow.beginSend(grant);
                    const pending=slow.reconcileSignedAck(scope,'a'.repeat(64),'cursor1',
                      async expected=>{
                        const good=await read('x1')(expected);
                        return {...good,ack_id:'ack-conflict',server_cas:'server-cas-conflict',
                          s03_sha256:'d'.repeat(64)};
                      },async()=>{started();await proceed;return true;});
                    await entered;
                    const winner=await fast.reconcileSignedAck(scope,'a'.repeat(64),'cursor1',
                      read('x1'),verify);
                    release();
                    let late='UNEXPECTED_ACCEPT';
                    try {late=(await pending).status;} catch(err){late=err.code;}
                    return {winner:winner.status,late,
                      stillAcked:(await fast.reserve(scope,'a'.repeat(64),'cursor1')).status};
                  } finally {release();slow.close();fast.close();}
                }""",db+"-conflicting-receipts")
                check("first canonical receipt commits exactly once",
                      clash["winner"]=="ACKED_RECOVERED" and clash["stillAcked"]=="ALREADY_ACKED")
                check("stale concurrent verifier cannot accept contradictory ACKED proof",
                      clash["late"]=="HOLD_CROSSTAB_ACKED_PROOF_CONFLICT")

                # Already ACKED is only a local replay fence: canonical
                # reconciliation MUST re-fetch and verify the signed receipt.
                check("ACKED reread requires canonical GET",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('missing'),verify)")=="HOLD_CROSSTAB_READBACK")
                check("ACKED rejects invalid fresh signature verifier",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',read('x1'),()=>false)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                check("ACKED bound to exact signed receipt after revalidation",
                      a.evaluate("()=>gate.reconcileSignedAck(s1,a,'cursor1',read('x1'),verify)")["status"]=="ALREADY_ACKED")
                check("alternate signed receipt bytes cannot reuse ACKED projection",
                      trial(a,"gate.reconcileSignedAck(s1,a,'cursor1',async x=>({...await read('x1')(x),signature:'alternate-signature'}),async()=>true)")=="HOLD_CROSSTAB_ACKED_PROOF_CONFLICT")
                # A source-local replay fence can suppress duplicate network ACKs,
                # but only the explicit GET-verified API can report completion.
                local=b.evaluate("()=>gate.reserve(s1,a,'cursor1')")
                check("local ACKED is not signed server delivery",
                      local["status"]=="ALREADY_ACKED" and
                      local["authority"]=="LOCAL_DEDUP_ONLY" and
                      "ack_id" not in local)
                check("certified resume requires a fresh canonical GET",
                      trial(b,"gate.requireCanonicalAck(s1,a,'cursor1',read('missing'),verify)")=="HOLD_CROSSTAB_READBACK")
                check("certified resume rejects altered signed receipt",
                      trial(b,"gate.requireCanonicalAck(s1,a,'cursor1',read('forged'),verify)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                check("certified resume rejects false independent verifier",
                      trial(b,"gate.requireCanonicalAck(s1,a,'cursor1',read('x1'),()=>false)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                certified=b.evaluate("()=>gate.requireCanonicalAck(s1,a,'cursor1',read('x1'),verify)")
                check("certified resume returns distinct canonical-only status",
                      certified=={"status":"CANONICAL_ACK_CONFIRMED",
                        "authority":"VERIFIER_CALLBACK_APPROVED","ack_id":"ack-x1"})
                turn2=b.evaluate("()=>gate.requireCanonicalAck(s2,b,'cursor2',read('x2'),verify)")
                check("second turn has distinct independently verified ACK",
                      turn2["status"]=="CANONICAL_ACK_CONFIRMED" and
                      turn2["ack_id"]=="ack-x2")
                check("unrelated cursor cannot impersonate verified completion",
                      trial(b,"gate.requireCanonicalAck(s2,b,'wrong-cursor',read('x2'),verify)")=="HOLD_CROSSTAB_CONFLICT")
                integrity=a.evaluate("""async dbName => {
                  const gate2=await NOXB1CrossTabAckLease.createGate({
                    indexedDB,databaseName:dbName,ttlMs:300
                  });
                  const scope={conversation_id:'dialog',exchange_id:'x1'},
                    event='a'.repeat(64);
                  async function edit(field,value) {
                    return new Promise((resolve,reject)=>{
                      const request=indexedDB.open(dbName,1);
                      request.onerror=()=>reject(Error('db open failed'));
                      request.onsuccess=()=>{
                        const db=request.result,tx=db.transaction('ack_fences','readwrite');
                        tx.oncomplete=()=>{db.close();resolve();};
                        tx.onabort=()=>{db.close();reject(Error('db mutate failed'));};
                        const store=tx.objectStore('ack_fences');
                        const row=store.get(['dialog','x1']);
                        row.onsuccess=()=>{
                          const updated=row.result;updated[field]=value;
                          store.put(updated);
                        };
                      };
                    });
                  }
                  try {
                    const grant=await gate2.reserve(scope,event,'cursor1');
                    await gate2.beginSend(grant);
                    await gate2.reconcileSignedAck(scope,event,'cursor1',read('x1'),verify);
                    const initial=await new Promise((resolve,reject)=>{
                      const req=indexedDB.open(dbName,1);
                      req.onerror=()=>reject(Error('db open failed'));
                      req.onsuccess=()=>{
                        const database=req.result;
                        const tx=database.transaction('ack_fences','readonly');
                        const get=tx.objectStore('ack_fences').get(['dialog','x1']);
                        get.onsuccess=()=>{resolve(get.result);database.close();};
                        get.onerror=()=>reject(Error('db read failed'));
                      };
                    });
                    await edit('server_ack_id','ack-spoofed');
                    let spoof='ACCEPTED';
                    try{await gate2.reconcileSignedAck(scope,event,'cursor1',read('x1'),verify);}
                    catch(error){spoof=error.code;}
                    await edit('server_ack_id','ack-x1');
                    await edit('receipt_proof_sha256','f'.repeat(64));
                    let digest='ACCEPTED';
                    try{await gate2.reconcileSignedAck(scope,event,'cursor1',read('x1'),verify);}
                    catch(error){digest=error.code;}
                    return {initial,spoof,digest};
                  } finally {gate2.close();}
                }""",db+"-ack-digest-integrity")
                check("verified ACKED stores SHA256 of signed server receipt",
                      isinstance(integrity["initial"].get("receipt_proof_sha256"),str)
                      and len(integrity["initial"]["receipt_proof_sha256"])==64)
                check("edited local ACKED metadata cannot masquerade as canonical receipt",
                      integrity["spoof"]=="HOLD_CROSSTAB_ACKED_PROOF_CONFLICT")
                check("edited local ACKED proof digest is rejected",
                      integrity["digest"]=="HOLD_CROSSTAB_ACKED_PROOF_CONFLICT")
                a.reload();a.add_script_tag(path=str(SOURCE))
                a.evaluate("""async db=>{
                    window.s1={conversation_id:'dialog',exchange_id:'x1'};
                    window.gate=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:db});
                }""", db)
                check("reloaded browser never sends duplicate terminal",
                      a.evaluate("()=>gate.reserve(s1,'a'.repeat(64),'cursor1')")["status"]=="ALREADY_ACKED")
                # Revocation tombstone lives in the same IndexedDB store as ACK,
                # so its serialization with ACK projection is browser-real.
                check("trusted native owner revocation recorded durably",
                      a.evaluate("()=>gate.noteOwnerRevoked('server-cas-x1')")=="REVOKED")
                check("duplicate revocation is harmless and irreversible",
                      a.evaluate("()=>gate.noteOwnerRevoked('server-cas-x1')")=="ALREADY_REVOKED")
                check("already-ACKED local replay fails closed after revocation",
                      trial(a,"gate.reserve(s1,'a'.repeat(64),'cursor1')")=="HOLD_CROSSTAB_OWNER_REVOKED")
                check("unrelated second-turn CAS remains usable",
                      b.evaluate("()=>gate.reserve(s2,b,'cursor2')")["status"]=="ALREADY_ACKED")
                race=a.evaluate("""async dbName=>{
                  const fresh=await NOXB1CrossTabAckLease.createGate({
                    indexedDB,databaseName:dbName,ttlMs:300
                  });
                  const scope={conversation_id:'dialog',exchange_id:'x1'};
                  try {
                    const grant=await fresh.reserve(scope,'a'.repeat(64),'cursor1');
                    await fresh.beginSend(grant);
                    let entered;
                    const verifierStarted=new Promise(resolve=>{entered=resolve;});
                    const pending=fresh.reconcileSignedAck(
                      scope,'a'.repeat(64),'cursor1',
                      async ()=>{const response=await fetch('/canonical/x1',{method:'GET',cache:'no-store'});if(!response.ok)throw Error('ACK_MISSING');return response.json();},
                      async ()=>{entered();await new Promise(r=>setTimeout(r,85));return true;}
                    );
                    await verifierStarted;
                    await fresh.noteOwnerRevoked('server-cas-x1');
                    let outcome='UNEXPECTED_ACCEPT';
                    try {await pending;} catch(e){outcome=e.code;}
                    let pendingState='UNEXPECTED_RESERVE';
                    try {await fresh.reserve(scope,'a'.repeat(64),'cursor1');}
                    catch(e){pendingState=e.code;}
                    return {outcome,pendingState};
                  } finally {fresh.close();}
                }""",db+"-revocation-race")
                check("owner revoked during async verifier blocks ACK projection",
                      race["outcome"]=="HOLD_CROSSTAB_OWNER_REVOKED")
                check("revocation leaves uncertain SENDING fenced, no replay",
                      race["pendingState"]=="HOLD_CROSSTAB_ACK_UNCERTAIN")
                with srv.lock: posts,reads=srv.posts,srv.reads
                check("NO model or ACK POST emitted by recovery",posts==0 and reads>=6)
                a.evaluate("()=>gate.close()");b.evaluate("()=>gate.close()")
                browser.close()
        finally:
            srv.shutdown();worker.join(timeout=3);srv.server_close()
    print("NOX B1 CANONICAL READBACK CHROMIUM SOURCE PASS (synthetic server proof)",flush=True)

if __name__=="__main__": main()
