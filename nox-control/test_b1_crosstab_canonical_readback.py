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
                a.reload();a.add_script_tag(path=str(SOURCE))
                a.evaluate("""async db=>{
                    window.s1={conversation_id:'dialog',exchange_id:'x1'};
                    window.gate=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:db});
                }""", db)
                check("reloaded browser never sends duplicate terminal",
                      a.evaluate("()=>gate.reserve(s1,'a'.repeat(64),'cursor1')")["status"]=="ALREADY_ACKED")
                with srv.lock: posts,reads=srv.posts,srv.reads
                check("NO model or ACK POST emitted by recovery",posts==0 and reads>=6)
                a.evaluate("()=>gate.close()");b.evaluate("()=>gate.close()")
                browser.close()
        finally:
            srv.shutdown();worker.join(timeout=3);srv.server_close()
    print("NOX B1 CANONICAL READBACK CHROMIUM SOURCE PASS (synthetic server proof)",flush=True)

if __name__=="__main__": main()
