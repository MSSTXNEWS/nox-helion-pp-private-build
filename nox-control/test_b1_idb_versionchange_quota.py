#!/usr/bin/env python3
"""B1 real Chromium IDB versionchange and deterministic quota-fault regression.

Synthetic test origin and owner callbacks. Real Chromium IndexedDB transactions
and upgrades; QuotaExceededError is deliberately injected at native add() call,
NOT asserted to be an organic browser quota exhaustion. Never a NOX/S03
production acceptance test.
"""
import os
import tempfile
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

SOURCE = Path(__file__).with_name("b1_client_ack_indexeddb_store.js")
A, B, C, D = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)

def packet(exchange="x1", event=A):
    return {"conversation_id":"b1-version-dialog","exchange_id":exchange,
            "event_id":event,"next_cursor":"signed_synthetic_cursor",
            "response_sha256":B,"s03_proof_sha256":C,
            "readback_only":True,"emit_terminal":True}

def check(label, condition):
    if not condition: raise AssertionError(label)
    print("PASS:", label, flush=True)

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args): pass

def main():
    with tempfile.TemporaryDirectory(prefix="b1-idb-fence-") as d:
        Path(d, "index.html").write_text("<!doctype html><title>B1 test</title>", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=d))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("NOX_B1_CHROME"))
                context = browser.new_context()
                page = context.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/index.html")
                page.add_script_tag(path=str(SOURCE))
                db1=f"b1-schema-{uuid.uuid4().hex}"
                db2=f"b1-quota-{uuid.uuid4().hex}"
                page.evaluate("""async n => {
                    window.b1 = await NOXB1IndexedAckStore.openClientAckHost({
                        indexedDB, databaseName:n,
                        authorizeEnvelope:async()=>true, freshPermit:async()=>true
                    });
                }""",db1)
                check("version source: initial ACK stored on actual Chrome IDB",
                      page.evaluate("p=>b1.commitTerminalAndAck(p)",packet())=="COMMITTED")
                upgraded=page.evaluate("""async n => {
                    return await new Promise((resolve,reject)=>{
                        const req=indexedDB.open(n,2);
                        req.onblocked=()=>reject(Error('upgrade blocked'));
                        req.onupgradeneeded=()=>{};
                        req.onerror=()=>reject(req.error);
                        req.onsuccess=()=>{req.result.close();resolve(true)};
                    });
                }""",db1)
                check("real versionchange cleanly releases old DB for upgrade", upgraded is True)
                old_code=page.evaluate("""async p=>{
                    try {await b1.commitTerminalAndAck(p);return 'BAD'}
                    catch(e){return e.code}
                }""",packet("x2",D))
                check("upgraded schema invalidates stale host before ACK",old_code=="HOLD_ACK_VERSIONCHANGE")
                read_code=page.evaluate("""async ()=>{
                    try {await b1.readCommitted('b1-version-dialog','x1');return 'BAD'}
                    catch(e){return e.code}
                }""")
                check("stale host refuses even readback",read_code=="HOLD_ACK_VERSIONCHANGE")
                reopened=page.evaluate("""async n=>{
                    try {
                        await NOXB1IndexedAckStore.openClientAckHost({
                            indexedDB,databaseName:n,authorizeEnvelope:async()=>true,
                            freshPermit:async()=>true
                        });return 'BAD'
                    } catch(e){return e.code}
                }""",db1)
                check("version 1 open refuses version 2 database",reopened=="HOLD_ACK_DB_OPEN")
                rows=page.evaluate("""async n=>await new Promise((resolve,reject)=>{
                    const req=indexedDB.open(n,2);
                    req.onerror=()=>reject(req.error);
                    req.onsuccess=()=>{
                        const db=req.result,tx=db.transaction('terminal_acks','readonly');
                        const store=tx.objectStore('terminal_acks');
                        const a=store.get(['b1-version-dialog','x1']);
                        const b=store.get(['b1-version-dialog','x2']);
                        let first,second;
                        a.onsuccess=()=>first=a.result;
                        b.onsuccess=()=>second=b.result;
                        tx.oncomplete=()=>{db.close();resolve([first?.event_id,second??null])};
                        tx.onerror=()=>reject(tx.error);
                    };
                })""",db1)
                check("schema upgrade keeps original ACK and never writes x2",rows==[A,None])
                page.evaluate("""async n=>{
                    window.quotaHost=await NOXB1IndexedAckStore.openClientAckHost({
                        indexedDB,databaseName:n,authorizeEnvelope:async()=>true,
                        freshPermit:async()=>true
                    });
                }""",db2)
                quota_code=page.evaluate("""async p=>{
                    const original=IDBObjectStore.prototype.add;
                    IDBObjectStore.prototype.add=function(){throw new DOMException('fault injection','QuotaExceededError')};
                    try {
                        try {await quotaHost.commitTerminalAndAck(p);return 'BAD'}
                        catch(e){return e.code}
                    } finally {IDBObjectStore.prototype.add=original}
                }""",packet())
                check("injected native QuotaExceededError returns specific HOLD",quota_code=="HOLD_ACK_QUOTA")
                check("quota-aborted transaction created no ACK",page.evaluate(
                    "()=>quotaHost.readCommitted('b1-version-dialog','x1')") is None)
                check("after cleared fault, one complete transaction commits",page.evaluate(
                    "p=>quotaHost.commitTerminalAndAck(p)",packet())=="COMMITTED")
                check("same proof after recovery reads existing ACK without duplicate",page.evaluate(
                    "p=>quotaHost.commitTerminalAndAck(p)",packet())=="ALREADY_COMMITTED")
                page.evaluate("()=>{quotaHost.close();b1.close()}")
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

if __name__=="__main__":
    main()
