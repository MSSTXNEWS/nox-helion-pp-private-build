#!/usr/bin/env python3
"""Real Chromium, same-origin two tabs, synthetic ACK transport; NO native NOX."""
import json
import hashlib
import os
import tempfile
import threading
import time
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
LEASE=HERE/"b1_cross_tab_ack_lease.js"
STREAM=HERE/"b1_client_stream_reconnect_harness.js"

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        if self.path!="/ack":return self.send_error(404)
        size=int(self.headers.get("Content-Length","0"))
        self.rfile.read(size)
        with self.server.counter_lock:self.server.acks+=1
        time.sleep(0.15)  # synthetic in-flight network ACK race
        self.send_response(200);self.send_header("Content-Type","application/json")
        self.end_headers();self.wfile.write(b'{"ok":true}')
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=="/canonical":
            nonce=parse_qs(parsed.query).get("request_nonce",[""])[0]
            with self.server.counter_lock: committed=self.server.acks>0
            if not committed:return self.send_error(404)
            now_ms=int(time.time()*1000)
            proof={"request_nonce":nonce,"issued_at_ms":now_ms,
                "expires_at_ms":now_ms+10000,
                "version":1,"state":"ACKED","conversation_id":"dialog",
                "exchange_id":"x5","event_id":"d"*64,
                "cursor_digest":hashlib.sha256(b"synthetic_cursor5").hexdigest(),
                "ack_id":"ack-x5","server_cas":"cas-x5",
                "s03_sha256":"c"*64,
                "signature":"synthetic-fixture-signature-"+nonce.replace("-","")}
            payload=json.dumps(proof).encode()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)));self.end_headers()
            return self.wfile.write(payload)
        if self.path=="/counts":
            with self.server.counter_lock:value=self.server.acks
            payload=json.dumps({"acks":value}).encode()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)));self.end_headers()
            return self.wfile.write(payload)
        return super().do_GET()

def check(label,ok):
    if not ok:raise AssertionError(label)
    print("PASS:",label,flush=True)

def call(page,expression):
    return page.evaluate("""async src=>{
      try{return await (new Function('return ('+src+')'))();}
      catch(e){return e.code||e.message||String(e);}
    }""",expression)

def main():
    assert LEASE.is_file() and STREAM.is_file()
    with tempfile.TemporaryDirectory(prefix="nox-b1-cross-tab-") as root:
        Path(root,"index.html").write_text("<!doctype html><title>NOX B1 source-only tabs</title>")
        server=ThreadingHTTPServer(("127.0.0.1",0),partial(Handler,directory=root))
        server.counter_lock=threading.Lock();server.acks=0
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                chrome=os.environ.get("NOX_B1_CHROME")
                kw={"executable_path":chrome} if chrome else {}
                browser=p.chromium.launch(headless=True,**kw)
                context=browser.new_context()
                url=f"http://127.0.0.1:{server.server_port}/index.html"
                db="nox-b1-cross-tab-"+uuid.uuid4().hex
                a=context.new_page();b=context.new_page()
                for tab in (a,b):
                    tab.goto(url)
                    tab.add_script_tag(path=str(LEASE))
                    tab.add_script_tag(path=str(STREAM))
                    tab.evaluate("""async db=>{
                      window.sc={conversation_id:'dialog',exchange_id:'x1'};
                      window.s2={conversation_id:'dialog',exchange_id:'x2'};
                      window.s3={conversation_id:'dialog',exchange_id:'x3'};
                      window.eventA='a'.repeat(64);window.eventB='b'.repeat(64);
                      window.gate=await NOXB1CrossTabAckLease.createGate({
                        indexedDB,databaseName:db,ttlMs:300
                      });
                    }""",db)
                grant=a.evaluate("()=>gate.reserve(sc,eventA,'cursor1')")
                check("tab A reserves x1 atomically",grant["status"]=="RESERVED")
                check("tab B blocked while x1 RESERVED",
                      call(b,"gate.reserve(sc,eventA,'cursor1')")=="HOLD_CROSSTAB_RESERVED")
                check("sender enters durable SENDING before network",
                      a.evaluate("g=>gate.beginSend(g)",grant)=="SENDING")
                check("tab B cannot send duplicate uncertain ACK",
                      call(b,"gate.reserve(sc,eventA,'cursor1')")=="HOLD_CROSSTAB_ACK_UNCERTAIN")
                check("sender confirms ACK only after completion",
                      a.evaluate("g=>gate.confirm(g)",grant)=="ACKED")
                check("tab B sees persisted ACK and must not retransmit",
                      b.evaluate("()=>gate.reserve(sc,eventA,'cursor1')")["status"]=="ALREADY_ACKED")
                check("other proof or event never reuses x1",
                      call(b,"gate.reserve(sc,eventA,'changed_cursor')")=="HOLD_CROSSTAB_CONFLICT"
                      and call(b,"gate.reserve(sc,eventB,'cursor1')")=="HOLD_CROSSTAB_CONFLICT")
                old=a.evaluate("()=>gate.reserve(s2,eventB,'cursor2')")
                check("new turn is independently reservable",old["status"]=="RESERVED")
                b.wait_for_timeout(380)
                new=b.evaluate("()=>gate.reserve(s2,eventB,'cursor2')")
                check("ONLY pre-send expired reservation can be reclaimed",
                      new["status"]=="RESERVED" and new["token"]!=old["token"] and new["generation"]==2)
                check("old sender fenced out after lease takeover",
                      call(a,"gate.beginSend("+json.dumps(old)+")")=="HOLD_CROSSTAB_FENCED")
                check("new sender can confirm distinct second turn",
                      b.evaluate("g=>gate.beginSend(g)",new)=="SENDING"
                      and b.evaluate("g=>gate.confirm(g)",new)=="ACKED")
                check("cross-turn event alias blocked by unique IndexedDB index",
                      call(a,"gate.reserve(s3,eventA,'cursor3')")=="HOLD_CROSSTAB_EVENT_COLLISION")
                # The stream adapter consumes the same durable gate. Its HTTP
                # readback and ACK endpoint below are FAKE, not NOX/S03.
                for tab in (a,b):
                    tab.evaluate("""()=>{
                      window.s5={conversation_id:'dialog',exchange_id:'x5'};
                      const host={readCommitted:async()=>null,
                        // Synthetic verifier only; cannot authenticate native S03.
                        verifyCanonicalAck:async receipt=>
                          receipt.signature.startsWith('synthetic-fixture-signature-') &&
                          receipt.server_cas==='cas-x5' &&
                          receipt.s03_sha256==='c'.repeat(64),
                        // Synthetic nonce signature witness, NOT native cryptography.
                        verifyFreshCanonicalAck:async(receipt,expected,scope,challenge)=>
                          receipt.request_nonce===challenge.request_nonce &&
                          receipt.signature==='synthetic-fixture-signature-'+
                            challenge.request_nonce.replaceAll('-','') &&
                          receipt.exchange_id===scope.exchange_id};
                      const transport={
                        post:async()=>{throw Error('UNEXPECTED_MODEL_POST')},
                        readback:async()=>({synthetic:true}),
                        readCanonicalAck:async(s,expected,challenge)=>{
                          const r=await fetch('/canonical?request_nonce='+
                            encodeURIComponent(challenge.request_nonce),
                            {method:'GET',cache:'no-store'});
                          if(!r.ok)throw Error('synthetic canonical ACK unavailable');
                          return r.json();
                        },
                        ack:async()=>{
                          let r=await fetch('/ack',{method:'POST',body:'{}'});
                          if(!r.ok)throw Error('ACK_FAILED');
                          return true;
                        }
                      };
                      const bridge={acceptTerminal:async()=>({
                        safe_to_ack:true,model_post:false,exchange_id:'x5',
                        conversation_id:'dialog',projection_event_id:'d'.repeat(64),
                        ack_cursor:'synthetic_cursor5'
                      })};
                      const ui={onDelta:async()=>{},
                        upsertTerminal:async(s,e)=>{
                          if(!document.querySelector('[data-terminal]')){
                            let el=document.createElement('div');el.dataset.terminal=e;
                            document.body.appendChild(el);
                          }
                          return true;
                        }};
                      window.client=NOXB1StreamReconnect.createClient({
                        host,transport,bridge,ui,ackGate:gate
                      });
                    }""")
                # Start tab A without blocking the host while synthetic ACK sleeps.
                a.evaluate("()=>{window.first=client.reconnect(s5).catch(e=>e.code);return true;}")
                outcome=call(b,"client.reconnect(s5)")
                check("concurrent second tab never sends another ACK",
                      outcome in ("HOLD_CROSSTAB_RESERVED","HOLD_CROSSTAB_ACK_UNCERTAIN")
                      or isinstance(outcome,dict))
                result=a.evaluate("()=>window.first")
                check("original tab completed guarded ACK",isinstance(result,dict)
                      and result["safe_to_ack"] is True)
                check("server receives one ACK across two tabs",
                      a.evaluate("()=>fetch('/counts').then(r=>r.json())")["acks"]==1)
                check("after confirmation second tab reconnect is readback-only",
                      b.evaluate("()=>client.reconnect(s5).then(r=>r.safe_to_ack)") is True
                      and a.evaluate("()=>fetch('/counts').then(r=>r.json())")["acks"]==1)
                # Losing the original sender after SENDING must not unlock retries.
                b.evaluate("""async()=>{
                  let x={conversation_id:'dialog',exchange_id:'x6'};
                  let g=await gate.reserve(x,'e'.repeat(64),'cursor6');
                  await gate.beginSend(g);
                }""")
                b.evaluate("()=>gate.close()");b.close()
                a.wait_for_timeout(400)
                check("crash after SENDING remains uncertain, never TTL-replayed",
                      call(a,"gate.reserve({conversation_id:'dialog',exchange_id:'x6'},'e'.repeat(64),'cursor6')")=="HOLD_CROSSTAB_ACK_UNCERTAIN")
                a.evaluate("()=>gate.close()");a.reload();a.add_script_tag(path=str(LEASE))
                a.evaluate("""async db=>{
                  window.gate=await NOXB1CrossTabAckLease.createGate({indexedDB,databaseName:db,ttlMs:300});
                }""",db)
                check("reload retains durable ACK without duplicate send",
                      a.evaluate("""()=>gate.reserve({conversation_id:'dialog',exchange_id:'x5'},
                          'd'.repeat(64),'synthetic_cursor5')""")["status"]=="ALREADY_ACKED")
                check("synthetic endpoint still saw exactly one ACK after reload",
                      a.evaluate("()=>fetch('/counts').then(r=>r.json())")["acks"]==1)
                a.evaluate("()=>gate.close()");context.close();browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)
if __name__=="__main__":main()
