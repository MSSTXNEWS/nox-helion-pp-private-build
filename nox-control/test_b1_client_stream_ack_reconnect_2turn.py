#!/usr/bin/env python3
"""B1 isolated Chrome 2-turn SSE STOP/reconnect fixture.

Real Chromium fetch streaming + IndexedDB transactions, but SYNTHETIC local HTTP
transport and fake authorizeEnvelope/freshPermit callbacks. NO authenticated
NOX model invocation, genuine S03 writer/readback, or production acceptance.
"""
import json
import os
import tempfile
import threading
import time
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
ACK=HERE/"b1_client_ack_indexeddb_store.js"
BRIDGE=HERE/"b1_client_reconnect_dedup_bridge.js"
HARNESS=HERE/"b1_client_stream_reconnect_harness.js"
A,B,C,D,E,F=("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64)

class State:
    def __init__(self):
        self.posts={}
        self.acks={}
        self.conflict=False
        self.lock=threading.Lock()

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*_): pass
    def reply(self,code,body,ctype="application/json"):
        raw=body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=="/readback":
            exchange=parse_qs(u.query).get("exchange_id",[""])[0]
            if exchange not in ("x1","x2"):
                return self.reply(404,'{"error":"no durable readback"}')
            with self.server.state.lock:
                conflict=self.server.state.conflict
            packet=dict(conversation_id="b1-stream-dialog",exchange_id=exchange,
                        event_id=A if exchange=="x1" else D,
                        next_cursor="synthetic_only_unverified_HMAC_cursor",
                        response_sha256=B,
                        s03_proof_sha256=F if exchange=="x2" and conflict else C,
                        readback_only=True,emit_terminal=True)
            return self.reply(200,json.dumps(packet))
        if u.path=="/conflict":
            with self.server.state.lock:
                self.server.state.conflict=True
            return self.reply(200,'{"ok":true}')
        if u.path=="/counts":
            with self.server.state.lock:
                counts={"posts":dict(self.server.state.posts),"acks":dict(self.server.state.acks)}
            return self.reply(200,json.dumps(counts))
        return super().do_GET()
    def do_POST(self):
        u=urlparse(self.path)
        size=int(self.headers.get("Content-Length","0"))
        try: body=json.loads(self.rfile.read(size) or b"{}")
        except Exception: return self.reply(400,'{"error":"bad"}')
        exchange=body.get("exchange_id")
        if u.path=="/ack":
            with self.server.state.lock:
                self.server.state.acks[exchange]=self.server.state.acks.get(exchange,0)+1
            return self.reply(200,'{"ok":true}')
        if u.path!="/stream" or exchange not in ("x1","x2","x3"):
            return self.reply(404,'{"error":"invalid"}')
        with self.server.state.lock:
            self.server.state.posts[exchange]=self.server.state.posts.get(exchange,0)+1
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        try:
            if exchange=="x3": time.sleep(0.30)
            self.wfile.write(("event: delta\ndata: "+exchange+"-partial\n\n").encode())
            self.wfile.flush()
            time.sleep(0.60 if exchange=="x1" else 0.02)
            self.wfile.write(b"event: terminal\ndata: unverified-stream-terminal\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

def check(label, condition):
    if not condition: raise AssertionError(label)
    print("PASS:",label,flush=True)

def attach(page,db):
    for file in (ACK,BRIDGE,HARNESS):
        page.add_script_tag(path=str(file))
    page.evaluate("""async (db)=>{
        window.sc={conversation_id:'b1-stream-dialog',exchange_id:'x1'};
        window.s2={conversation_id:'b1-stream-dialog',exchange_id:'x2'};
        window.s3={conversation_id:'b1-stream-dialog',exchange_id:'x3'};
        window.deltas=[];window.projections=new Map();
        window.ackDelayMs=0;window.ackFailOnce=0;
        window.uiFalseOnce=0;window.uiFailAfterWriteOnce=0;
        window.host=await NOXB1IndexedAckStore.openClientAckHost({
            indexedDB,databaseName:db,
            authorizeEnvelope:async()=>true, // intentionally synthetic!
            freshPermit:async()=>true           // intentionally synthetic!
        });
        const transport={
            post:(s,signal)=>fetch('/stream',{method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify(s),signal}),
            readback:async s=>{
                const r=await fetch('/readback?exchange_id='+encodeURIComponent(s.exchange_id));
                if(!r.ok) throw Error('no durable server readback');
                return r.json();
            },
            ack:async (s,cursor)=>{
                if(window.ackFailOnce>0){
                    window.ackFailOnce--;
                    throw Error('synthetic ACK delivery failure');
                }
                if(window.ackDelayMs)
                    await new Promise(ok=>setTimeout(ok,window.ackDelayMs));
                const r=await fetch('/ack',{method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({...s,cursor})});
                if(!r.ok) throw Error('ACK failed');
            }
        };
        const ui={
            onDelta:async(s,value)=>window.deltas.push([s.exchange_id,value]),
            upsertTerminal:async(s,event_id)=>{
                if(window.uiFalseOnce>0){
                    window.uiFalseOnce--;
                    return false; // caller says no durable projection witness
                }
                if(!window.projections.has(event_id)){
                    window.projections.set(event_id,s.exchange_id);
                    const element=document.createElement('div');
                    element.dataset.eventId=event_id;
                    element.textContent='terminal:'+s.exchange_id;
                    document.body.appendChild(element);
                }
                if(window.uiFailAfterWriteOnce>0){
                    window.uiFailAfterWriteOnce--;
                    throw Error('synthetic UI failure after partial DOM mutation');
                }
            }
        };
        window.client=NOXB1StreamReconnect.createClient({
            transport,host,bridge:NOXB1ReconnectDedup,ui,timeoutMs:90
        });
    }""",db)

def code(page,expression):
    return page.evaluate("""async exp=>{
        try{return await Function('return ('+exp+')')();}
        catch(e){return e.code||e.message||String(e);}
    }""",expression)

def main():
    for item in (ACK,BRIDGE,HARNESS):
        assert item.is_file(),str(item)
    with tempfile.TemporaryDirectory(prefix="b1-2turn-sse-") as d:
        Path(d,"index.html").write_text("<!doctype html><title>B1 Synthetic SSE</title>")
        server=ThreadingHTTPServer(("127.0.0.1",0),partial(Handler,directory=d))
        server.state=State()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=os.environ.get("NOX_B1_CHROME"))
                context=browser.new_context()
                url=f"http://127.0.0.1:{server.server_port}/index.html"
                db="b1-sse-"+uuid.uuid4().hex
                page=context.new_page();page.goto(url);attach(page,db)
                page.evaluate("()=>{window.pending=client.begin(sc);}")
                page.wait_for_function("window.deltas.some(d=>d[0]==='x1')",timeout=5000)
                check("first turn receives real Chrome streaming delta before STOP",
                      page.evaluate("()=>deltas[0][1]")=="x1-partial")
                check("STOP aborts active fetch",page.evaluate("()=>client.stop(sc)") is True)
                check("aborted first turn cannot be assumed terminal",
                      page.evaluate("()=>window.pending")=="STOPPED")
                check("first reconnect uses separately readback terminal",
                      page.evaluate("()=>client.reconnect(sc).then(x=>x.safe_to_ack)") is True)
                page.evaluate("()=>{window.ackDelayMs=35}")
                page.evaluate("()=>Promise.all([client.reconnect(sc),client.reconnect(sc)])")
                page.evaluate("()=>{window.ackDelayMs=0}")
                counts=page.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("two simultaneous reconnects issue only one network ACK",
                      counts["acks"].get("x1",0)==2)
                check("duplicate reconnect projects one terminal event",
                      page.evaluate("()=>document.querySelectorAll('[data-event-id]').length")==1)
                check("fresh second turn streams without re-POST of first",
                      page.evaluate("()=>client.begin(s2)")=="STREAM_ENDED_READBACK_REQUIRED")
                page.evaluate("()=>{window.uiFalseOnce=1}")
                check("explicitly unconfirmed UI projection blocks ACK",
                      code(page,"client.reconnect(s2)")=="HOLD_STREAM_UI_NOT_CONFIRMED"
                      and page.evaluate("()=>fetch('/counts').then(r=>r.json())")["acks"].get("x2",0)==0)
                page.evaluate("()=>{window.uiFailAfterWriteOnce=1}")
                check("partial UI write then failure blocks ACK",
                      code(page,"client.reconnect(s2)")=="HOLD_STREAM_UI_PROJECTION"
                      and page.evaluate("()=>fetch('/counts').then(r=>r.json())")["acks"].get("x2",0)==0)
                check("readback-only retry ACKs same event once, no second UI",
                      page.evaluate("()=>client.reconnect(s2).then(x=>x.safe_to_ack)") is True
                      and page.evaluate("()=>document.querySelectorAll('[data-event-id]').length")==2)
                page.evaluate("()=>{window.ackFailOnce=1}")
                check("lost ACK returns HOLD without claiming success",
                      code(page,"client.reconnect(s2)")=="HOLD_STREAM_ACK_UNCONFIRMED")
                check("ACK recovery uses same terminal event without new POST",
                      page.evaluate("()=>client.reconnect(s2).then(x=>x.safe_to_ack)") is True
                      and page.evaluate("()=>document.querySelectorAll('[data-event-id]').length")==2)
                counts=page.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("one fake model POST per unique turn; ACK retry only on readback",
                      counts["posts"]=={"x1":1,"x2":1} and counts["acks"].get("x1",0)==2
                      and counts["acks"].get("x2",0)==2)
                page.evaluate("()=>fetch('/conflict')")
                check("tampered S03 proof rejects reconnect without extra POST",
                      code(page,"client.reconnect(s2)") in ("HOLD_ACK_CONFLICT","HOLD_CLIENT_ACK_WITNESS","HOLD_CLIENT_CALLBACK_OR_STORE"))
                page.evaluate("()=>host.close()");page.close()
                new=context.new_page();new.goto(url);attach(new,db)
                # Re-enable valid synthetic server proof before rehydration.
                with server.state.lock:server.state.conflict=False
                new.evaluate("()=>Promise.all([client.reconnect(sc),client.reconnect(s2)])")
                check("reload rehydrates exactly two persisted unique terminals",
                      new.evaluate("()=>document.querySelectorAll('[data-event-id]').length")==2)
                check("known exchange never starts another fake model POST after reload",
                      code(new,"client.begin(sc)")=="HOLD_STREAM_RECONNECT_ONLY")
                new.evaluate("()=>{window.timeoutTask=client.begin(s3);}")
                check("silent third stream stops at total wall deadline",
                      new.evaluate("()=>window.timeoutTask")=="STOPPED_TIMEOUT")
                check("timed-out uncertain exchange not automatically POSTed again",
                      code(new,"client.begin(s3)")=="HOLD_STREAM_NO_REPOST")
                check("no phantom durable terminal for incomplete third turn",
                      new.evaluate("()=>host.readCommitted('b1-stream-dialog','x3')") is None)
                final=new.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("only three distinct POSTs across STOP, retry, reload and timeout",
                      final["posts"]=={"x1":1,"x2":1,"x3":1})
                new.evaluate("()=>host.close()")
                context.close();browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=="__main__":
    main()
