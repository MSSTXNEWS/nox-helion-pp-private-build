#!/usr/bin/env python3
"""B1 source-only real Chromium SSE -> STOP -> canonical ACK reconnect (synthetic server).

Actual NOX serving, immutable owner verifier, model/S03 and production are NOT tested.
"""
import hashlib
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

HERE = Path(__file__).resolve().parent
STREAM = HERE / "b1_client_stream_reconnect_harness.js"
FENCE = HERE / "b1_cross_tab_ack_lease.js"

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.posts = {}
        self.acks = {}
        self.tamper = False

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
    def reply(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        u = urlparse(self.path)
        query = parse_qs(u.query)
        x = query.get("exchange_id", [""])[0]
        if u.path == "/counts":
            with self.server.state.lock:
                return self.reply(200, {"posts":dict(self.server.state.posts),
                                        "acks":dict(self.server.state.acks)})
        if u.path == "/committed":
            with self.server.state.lock:
                return self.reply(200, {"committed":self.server.state.acks.get(x,0)>0})
        if u.path == "/readback":
            if x not in ("x1","x2"): return self.reply(404,{"error":"unknown"})
            return self.reply(200, {"conversation_id":"dialog","exchange_id":x,
                "event_id":("a" if x=="x1" else "b")*64,
                "cursor":"cursor1" if x=="x1" else "cursor2"})
        if u.path == "/canonical":
            with self.server.state.lock:
                acked = self.server.state.acks.get(x,0)>0
                tamper = self.server.state.tamper
            if x not in ("x1","x2") or not acked:
                return self.reply(404, {"error":"no durable ACK"})
            cursor = "cursor1" if x=="x1" else "cursor2"
            nonce = query.get("request_nonce", [""])[0]
            now_ms = int(time.time()*1000)
            return self.reply(200, {
                "request_nonce":nonce,"issued_at_ms":now_ms,
                "expires_at_ms":now_ms+10000,
                "version":1,"state":"ACKED","conversation_id":"dialog",
                "exchange_id":x,"event_id":("a" if x=="x1" else "b")*64,
                "cursor_digest":hashlib.sha256(cursor.encode()).hexdigest(),
                "ack_id":"ack-"+x,"server_cas":"cas-"+x,
                "s03_sha256":"c"*64,
                "signature":"forged-fixture" if tamper else "synthetic-fixture-signature",
                "freshness_signature":"synthetic-freshness-"+
                    nonce.replace("-","")+"-"+str(now_ms)+"-"+str(now_ms+10000)})
        if u.path == "/tamper":
            with self.server.state.lock: self.server.state.tamper = True
            return self.reply(200, {"tamper":True})
        return super().do_GET()
    def do_POST(self):
        u = urlparse(self.path)
        body = self.rfile.read(int(self.headers.get("Content-Length","0")))
        try: x=json.loads(body).get("exchange_id")
        except (ValueError,TypeError): return self.reply(400,{"error":"body"})
        if x not in ("x1","x2"): return self.reply(400,{"error":"scope"})
        if u.path == "/ack":
            with self.server.state.lock:
                self.server.state.acks[x] = self.server.state.acks.get(x,0)+1
            return self.reply(200, {"ok":True})
        if u.path != "/stream": return self.reply(404,{"error":"path"})
        with self.server.state.lock:
            self.server.state.posts[x] = self.server.state.posts.get(x,0)+1
        self.send_response(200)
        self.send_header("Content-Type","text/event-stream")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        try:
            self.wfile.write(("event: delta\ndata: "+x+"-partial\n\n").encode())
            self.wfile.flush()
            time.sleep(0.30 if x=="x1" else 0.01)
            self.wfile.write(b"event: terminal\ndata: unsigned-not-ack\n\n")
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,OSError): pass

def check(label, ok):
    if not ok: raise AssertionError(label)
    print("PASS:",label,flush=True)

def evaluate(page, source):
    return page.evaluate("""async source=>{
        try {return await Function('return ('+source+')')();}
        catch(e){return e.code||e.message||String(e);}
    }""",source)

def attach(page, name):
    page.add_script_tag(path=str(FENCE))
    page.add_script_tag(path=str(STREAM))
    page.evaluate("""async name=>{
        window.s1={conversation_id:'dialog',exchange_id:'x1'};
        window.s2={conversation_id:'dialog',exchange_id:'x2'};
        window.deltas=[];
        window.uiEvents=new Set();
        window.dropAfterSend=false;
        window.gate=await NOXB1CrossTabAckLease.createGate({
            indexedDB,databaseName:name,ttlMs:200
        });
        window.host={
          readCommitted:async(c,x)=>{
            const r=await fetch('/committed?exchange_id='+encodeURIComponent(x),
              {method:'GET',cache:'no-store'});
            return (await r.json()).committed?{durable:true}:null;
          },
          verifyCanonicalAck:async(receipt,expected,scope)=>
            receipt.signature==='synthetic-fixture-signature' &&
            receipt.server_cas==='cas-'+scope.exchange_id &&
            receipt.s03_sha256==='c'.repeat(64) &&
            expected.exchange_id===scope.exchange_id,
          // SYNTHETIC ONLY. Production MUST verify server signature over the
          // challenge nonce, timestamp bounds, canonical ACK and owner/S03.
          verifyFreshCanonicalAck:async(receipt,expected,scope,challenge)=>
            receipt.request_nonce===challenge.request_nonce &&
            receipt.freshness_signature==='synthetic-freshness-'+
              challenge.request_nonce.replaceAll('-','')+'-'+
              receipt.issued_at_ms+'-'+receipt.expires_at_ms &&
            receipt.exchange_id===scope.exchange_id &&
            expected.exchange_id===scope.exchange_id
        };
        window.transport={
          post:(s,signal)=>fetch('/stream',{method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify(s),signal}),
          readback:async s=>{
            const r=await fetch('/readback?exchange_id='+encodeURIComponent(s.exchange_id),
              {cache:'no-store'});
            if(!r.ok)throw Error('no readback');
            return r.json();
          },
          readCanonicalAck:async (s,expected,challenge)=>{
            const r=await fetch('/canonical?exchange_id='+encodeURIComponent(s.exchange_id)+
              '&request_nonce='+encodeURIComponent(challenge.request_nonce),
              {method:'GET',cache:'no-store'});
            if(!r.ok)throw Error('canonical ACK missing');
            return r.json();
          },
          ack:async (s,cursor)=>{
            const r=await fetch('/ack',{method:'POST',
              headers:{'Content-Type':'application/json'},
              body:JSON.stringify({...s,cursor})});
            if(!r.ok)throw Error('ack failure');
            if(window.dropAfterSend){window.dropAfterSend=false;
              throw Error('synthetic lost ACK response');}
          }
        };
        window.bridge={acceptTerminal:async(packet,s,host)=>({
            safe_to_ack:true,model_post:false,
            conversation_id:s.conversation_id,exchange_id:s.exchange_id,
            projection_event_id:packet.event_id,ack_cursor:packet.cursor
        })};
        window.ui={
          onDelta:async(s,text)=>window.deltas.push([s.exchange_id,text]),
          upsertTerminal:async(s,id)=>{
            if(!window.uiEvents.has(id)){
              window.uiEvents.add(id);
              const node=document.createElement('div');
              node.dataset.eventId=id;document.body.appendChild(node);
            }
            return true;
          }
        };
        window.client=NOXB1StreamReconnect.createClient({
            transport,host,bridge,ui,ackGate:gate,timeoutMs:1000
        });
    }""",name)

def main():
    assert STREAM.is_file() and FENCE.is_file()
    with tempfile.TemporaryDirectory(prefix="nox-b1-sse-canonical-") as folder:
        Path(folder,"index.html").write_text("<!doctype html><title>isolated B1</title>")
        server=ThreadingHTTPServer(("127.0.0.1",0),partial(Handler,directory=folder))
        server.state=State()
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                exe=os.getenv("NOX_B1_CHROME")
                browser=p.chromium.launch(headless=True,**({"executable_path":exe} if exe else {}))
                ctx=browser.new_context()
                url=f"http://127.0.0.1:{server.server_port}/index.html"
                db="b1-canonical-"+uuid.uuid4().hex
                page=ctx.new_page();page.goto(url);attach(page,db)
                page.evaluate("()=>{window.task=client.begin(s1)}")
                page.wait_for_function("deltas.some(x=>x[0]==='x1')",timeout=5000)
                check("real Chromium first SSE delta arrived",page.evaluate("()=>deltas[0][1]")=="x1-partial")
                check("STOP aborts stream",page.evaluate("()=>client.stop(s1)") is True)
                check("aborted first exchange not terminal",page.evaluate("()=>task")=="STOPPED")
                first=page.evaluate("()=>client.reconnect(s1)")
                check("first turn requires canonical ACK GET",first.get("canonical_ack_status")=="CANONICAL_ACK_CONFIRMED"
                      and first.get("canonical_ack_id")=="ack-x1")
                check("local ACKED replay still revalidates canonical GET",
                      page.evaluate("()=>client.reconnect(s1)")["canonical_ack_status"]=="CANONICAL_ACK_CONFIRMED")
                counts=page.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("reconnect did not duplicate first model or ACK POST",
                      counts["posts"]=={"x1":1} and counts["acks"]=={"x1":1})
                check("second distinct turn streams",page.evaluate("()=>client.begin(s2)")=="STREAM_ENDED_READBACK_REQUIRED")
                page.evaluate("()=>{window.dropAfterSend=true}")
                check("lost ACK response is never falsely accepted",
                      evaluate(page,"client.reconnect(s2)")=="HOLD_STREAM_ACK_UNCONFIRMED")
                second=page.evaluate("()=>client.reconnect(s2)")
                check("uncertain SENDING recovers by canonical GET without new ACK",
                      second.get("canonical_ack_status")=="CANONICAL_ACK_CONFIRMED"
                      and second.get("canonical_ack_id")=="ack-x2")
                counts=page.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("one model POST + one ACK POST per each two turns",
                      counts["posts"]=={"x1":1,"x2":1}
                      and counts["acks"]=={"x1":1,"x2":1})
                check("two unique UI event projections",
                      page.evaluate("()=>document.querySelectorAll('[data-event-id]').length")==2)
                # STOP while a reader is pending: even a non-cooperative reader
                # that resolves a buffered delta AFTER abort must never reach UI.
                page.evaluate("""()=>{
                  const mk=(post,onDelta,timeout=1000)=>NOXB1StreamReconnect.createClient({
                    transport:{...transport,post},host,bridge,
                    ui:{...ui,onDelta},timeoutMs:timeout
                  });
                  window.lateReadEvents=[];
                  window.lateReadClient=mk(async()=>({ok:true,body:{getReader:()=>({
                    read:()=>new Promise(resolve=>{
                      window.releaseLateRead=()=>resolve({done:false,value:
                        new TextEncoder().encode('event: delta\\n'+'data: late-after-stop\\n\\n')});
                    })
                  })}}),async(_s,d)=>lateReadEvents.push(d));
                  window.lateReadTask=lateReadClient.begin({
                    conversation_id:'dialog',exchange_id:'late-read'});
                }""")
                page.wait_for_function("typeof releaseLateRead==='function'",timeout=5000)
                check("STOP active while reader pending",page.evaluate("""()=>{
                  return lateReadClient.stop({conversation_id:'dialog',
                    exchange_id:'late-read'});
                }""") is True)
                page.evaluate("()=>releaseLateRead()")
                check("buffered delta after STOP dropped before UI",
                      page.evaluate("()=>lateReadTask")=="STOPPED" and
                      page.evaluate("()=>lateReadEvents.length")==0)

                # Response object can resolve after AbortController STOP, too.
                page.evaluate("""()=>{
                  window.latePostEvents=[];
                  window.latePostClient=NOXB1StreamReconnect.createClient({
                    transport:{...transport,post:()=>new Promise(resolve=>{
                      window.releaseLatePost=()=>resolve({ok:true,body:{
                        getReader:()=>({read:async()=>({done:false,value:
                          new TextEncoder().encode('event: delta\\ndata: late-post\\n\\n')})})
                      }});
                    })},
                    host,bridge,ui:{...ui,onDelta:async(_s,d)=>latePostEvents.push(d)},
                    timeoutMs:1000
                  });
                  window.latePostTask=latePostClient.begin({
                    conversation_id:'dialog',exchange_id:'late-post'});
                }""")
                page.wait_for_function("typeof releaseLatePost==='function'",timeout=5000)
                check("STOP active while POST response pending",
                      page.evaluate("""()=>latePostClient.stop({
                        conversation_id:'dialog',exchange_id:'late-post'})""") is True)
                page.evaluate("()=>releaseLatePost()")
                check("late POST response cannot project buffered delta",
                      page.evaluate("()=>latePostTask")=="STOPPED" and
                      page.evaluate("()=>latePostEvents.length")==0)

                # A frame with two deltas must not emit its second frame when
                # STOP happens inside an awaited UI callback. The UI adapter
                # must check the passed AbortSignal before its DOM commit.
                page.evaluate("""()=>{
                  window.invokedUI=[];window.committedUI=[];window.signalProvided=false;
                  window.lateUIClient=NOXB1StreamReconnect.createClient({
                    transport:{...transport,post:async()=>({ok:true,body:{
                      getReader:()=>({read:async()=>({done:false,value:
                        new TextEncoder().encode(
                          'event: delta\\ndata: first\\n\\n'+
                          'event: delta\\ndata: second\\n\\n')})})
                    }})},
                    host,bridge,
                    ui:{...ui,onDelta:async(_s,d,signal)=>{
                      invokedUI.push(d);signalProvided=!!signal;
                      if(d==='first')await new Promise(resolve=>window.releaseUI=resolve);
                      if(!signal.aborted)committedUI.push(d);
                    }},
                    timeoutMs:1000
                  });
                  window.lateUITask=lateUIClient.begin({
                    conversation_id:'dialog',exchange_id:'late-ui'});
                }""")
                page.wait_for_function("typeof releaseUI==='function'",timeout=5000)
                check("STOP accepted inside pending UI callback",
                      page.evaluate("""()=>lateUIClient.stop({
                        conversation_id:'dialog',exchange_id:'late-ui'})""") is True)
                page.evaluate("()=>releaseUI()")
                check("UI AbortSignal fences delayed commit and second delta",
                      page.evaluate("()=>lateUITask")=="STOPPED" and
                      page.evaluate("()=>signalProvided") is True and
                      page.evaluate("()=>invokedUI") == ["first"] and
                      page.evaluate("()=>committedUI")==[])
                check("late STOP tests did not post model or ACK",
                      page.evaluate("()=>fetch('/counts').then(r=>r.json())")==counts)
                # An uncooperative ui.onDelta must not keep begin() pending after
                # STOP or timeout, and late settlement must not project state.
                page.evaluate("""()=>{
                  window.hungStats={};
                  window.makeHungClient=(exchangeId,onDelta,timeout=1000)=>{
                    const stats={posts:0,acks:0,terminals:0};
                    hungStats[exchangeId]=stats;
                    const client=NOXB1StreamReconnect.createClient({
                      transport:{
                        ...transport,
                        post:async()=>{
                          stats.posts++;
                          return {ok:true,body:{getReader:()=>({
                            read:async()=>({done:false,value:new TextEncoder().encode(
                              'event: delta\\ndata: first\\n\\n'+
                              'event: delta\\ndata: second\\n\\n')})
                          })}};
                        },
                        ack:async()=>{stats.acks++;return true;}
                      },
                      host,bridge,
                      ui:{...ui,onDelta,
                        upsertTerminal:async()=>{stats.terminals++;return true;}},
                      timeoutMs:timeout
                    });
                    return client;
                  };
                  window.hungStopInvoked=[];window.hungStopCommitted=[];
                  window.hungStopEntered=false;
                  window.hungStopClient=makeHungClient('hung-stop',async(_s,d,signal)=>{
                    hungStopInvoked.push(d);window.hungStopSignal=signal;
                    hungStopEntered=true;
                    await new Promise(()=>{});
                    if(!signal.aborted)hungStopCommitted.push(d);
                  });
                  window.hungStopTask=hungStopClient.begin({
                    conversation_id:'dialog',exchange_id:'hung-stop'});
                }""")
                page.wait_for_function("window.hungStopEntered===true",timeout=5000)
                check("STOP accepted while ui.onDelta never settles",
                      page.evaluate("""()=>hungStopClient.stop({
                        conversation_id:'dialog',exchange_id:'hung-stop'})""") is True)
                check("STOP promptly unblocks begin despite hung UI callback",
                      page.evaluate("""()=>Promise.race([hungStopTask,
                        new Promise(resolve=>setTimeout(()=>resolve('HUNG'),750))])""")
                      =="STOPPED")
                check("STOP abort signal and single delta are preserved",
                      page.evaluate("()=>hungStopSignal.aborted") is True and
                      page.evaluate("()=>hungStopInvoked")==["first"] and
                      page.evaluate("()=>hungStopCommitted")==[])

                # The configured timeout must also unblock a callback that
                # ignores AbortSignal and never settles.
                page.evaluate("""()=>{
                  window.hungTimeoutInvoked=[];window.hungTimeoutCommitted=[];
                  window.hungTimeoutEntered=false;
                  window.hungTimeoutClient=makeHungClient('hung-timeout',
                    async(_s,d,signal)=>{
                      hungTimeoutInvoked.push(d);window.hungTimeoutSignal=signal;
                      hungTimeoutEntered=true;
                      await new Promise(()=>{});
                      if(!signal.aborted)hungTimeoutCommitted.push(d);
                    },80);
                  window.hungTimeoutTask=hungTimeoutClient.begin({
                    conversation_id:'dialog',exchange_id:'hung-timeout'});
                }""")
                page.wait_for_function("window.hungTimeoutEntered===true",timeout=5000)
                check("timeout promptly unblocks begin despite hung UI callback",
                      page.evaluate("""()=>Promise.race([hungTimeoutTask,
                        new Promise(resolve=>setTimeout(()=>resolve('HUNG'),1000))])""")
                      =="STOPPED_TIMEOUT")
                check("timeout signal fences later frame and commit",
                      page.evaluate("()=>hungTimeoutSignal.aborted") is True and
                      page.evaluate("()=>hungTimeoutInvoked")==["first"] and
                      page.evaluate("()=>hungTimeoutCommitted")==[])

                # A callback released after STOP must see the aborted signal
                # before its actual UI commit.
                page.evaluate("""()=>{
                  window.lateResolveInvoked=[];window.lateResolveCommitted=[];
                  window.lateResolveEntered=false;
                  window.lateResolveClient=makeHungClient('late-resolve',
                    async(_s,d,signal)=>{
                      lateResolveInvoked.push(d);
                      if(d==='first'){
                        lateResolveEntered=true;
                        await new Promise(resolve=>window.releaseLateResolve=resolve);
                      }
                      if(!signal.aborted)lateResolveCommitted.push(d);
                    });
                  window.lateResolveTask=lateResolveClient.begin({
                    conversation_id:'dialog',exchange_id:'late-resolve'});
                }""")
                page.wait_for_function("window.lateResolveEntered===true",timeout=5000)
                check("late-resolve STOP accepted",
                      page.evaluate("""()=>lateResolveClient.stop({
                        conversation_id:'dialog',exchange_id:'late-resolve'})""") is True)
                check("late-resolve callback no longer blocks begin",
                      page.evaluate("""()=>Promise.race([lateResolveTask,
                        new Promise(resolve=>setTimeout(()=>resolve('HUNG'),750))])""")
                      =="STOPPED")
                page.evaluate("()=>releaseLateResolve()")
                page.evaluate("()=>new Promise(resolve=>setTimeout(resolve,0))")
                check("late callback resolution cannot commit or emit next delta",
                      page.evaluate("()=>lateResolveInvoked")==["first"] and
                      page.evaluate("()=>lateResolveCommitted")==[])

                # A late rejection after cancellation must stay observed.
                page.evaluate("""()=>{
                  window.unhandledHungRejections=0;
                  window.addEventListener('unhandledrejection',()=>{
                    window.unhandledHungRejections++;
                  });
                  window.lateRejectInvoked=[];window.lateRejectEntered=false;
                  window.lateRejectClient=makeHungClient('late-reject',
                    async(_s,d)=>{
                      lateRejectInvoked.push(d);lateRejectEntered=true;
                      await new Promise((_resolve,reject)=>{
                        window.rejectLateCallback=()=>reject(new Error('late UI rejection'));
                      });
                    });
                  window.lateRejectTask=lateRejectClient.begin({
                    conversation_id:'dialog',exchange_id:'late-reject'});
                }""")
                page.wait_for_function("window.lateRejectEntered===true",timeout=5000)
                check("late-reject STOP accepted",
                      page.evaluate("""()=>lateRejectClient.stop({
                        conversation_id:'dialog',exchange_id:'late-reject'})""") is True)
                check("late rejection cannot replace STOP result",
                      page.evaluate("""()=>Promise.race([lateRejectTask,
                        new Promise(resolve=>setTimeout(()=>resolve('HUNG'),750))])""")
                      =="STOPPED")
                page.evaluate("()=>rejectLateCallback()")
                page.evaluate("()=>new Promise(resolve=>setTimeout(resolve,20))")
                check("late callback rejection is handled without unhandled rejection",
                      page.evaluate("()=>unhandledHungRejections")==0 and
                      page.evaluate("()=>lateRejectInvoked")==["first"])
                # An already queued STOP can run between read resolution and the
                # onDelta microtask; the callback must not start afterward.
                page.evaluate("""()=>{
                  window.sameTurnInvoked=[];window.sameTurnCommitted=[];
                  window.sameTurnStopResult=null;
                  const scope={conversation_id:'dialog',exchange_id:'same-turn-stop'};
                  const stats={posts:0,acks:0,terminals:0};
                  hungStats[scope.exchange_id]=stats;
                  window.sameTurnClient=NOXB1StreamReconnect.createClient({
                    transport:{
                      ...transport,
                      post:async()=>{
                        stats.posts++;
                        return {ok:true,body:{getReader:()=>({
                          read:()=>new Promise(resolve=>{
                            queueMicrotask(()=>{
                              resolve({done:false,value:new TextEncoder().encode(
                                'event: delta\\ndata: first\\n\\n'+
                                'event: delta\\ndata: second\\n\\n')});
                              queueMicrotask(()=>{
                                sameTurnStopResult=sameTurnClient.stop(scope);
                              });
                            });
                          })
                        })}};
                      },
                      ack:async()=>{stats.acks++;return true;}
                    },
                    host,bridge,
                    ui:{...ui,onDelta:async(_s,d,signal)=>{
                      sameTurnInvoked.push(d);
                      if(!signal.aborted)sameTurnCommitted.push(d);
                    },upsertTerminal:async()=>{stats.terminals++;return true;}},
                    timeoutMs:1000
                  });
                  window.sameTurnTask=sameTurnClient.begin(scope);
                }""")
                check("queued STOP wins before ui.onDelta callback microtask",
                      page.evaluate("""()=>Promise.race([sameTurnTask,
                        new Promise(resolve=>setTimeout(()=>resolve('HUNG'),750))])""")
                      =="STOPPED" and
                      page.evaluate("()=>sameTurnStopResult") is True and
                      page.evaluate("()=>sameTurnInvoked")==[] and
                      page.evaluate("()=>sameTurnCommitted")==[])
                check("hung UI callbacks never ACK or create terminal state",
                      page.evaluate("""()=>Object.values(hungStats).every(x=>
                        x.posts===1&&x.acks===0&&x.terminals===0)"""))
                page.evaluate("()=>gate.close()");page.close()
                nextpage=ctx.new_page();nextpage.goto(url);attach(nextpage,db)
                check("reload uses canonical GET not duplicate POST/ACK",
                      nextpage.evaluate("()=>client.reconnect(s1)")["canonical_ack_status"]=="CANONICAL_ACK_CONFIRMED")
                check("known committed first turn cannot rePOST after reload",
                      evaluate(nextpage,"client.begin(s1)")=="HOLD_STREAM_RECONNECT_ONLY")
                # Captured signed ACK from a prior GET must NOT satisfy a
                # different challenge. Test this before permanent tamper.
                nextpage.evaluate("""()=>{
                  window.freshRead=transport.readCanonicalAck;
                  transport.readCanonicalAck=(s,e,ch)=>
                    freshRead(s,e,{...ch,request_nonce:'captured-replay'});
                }""")
                check("replayed signed ACK GET nonce is rejected",
                      evaluate(nextpage,"client.reconnect(s1)")=="HOLD_CROSSTAB_READBACK")
                nextpage.evaluate("()=>{transport.readCanonicalAck=freshRead}")
                nextpage.evaluate("""()=>{
                  window.freshRead=transport.readCanonicalAck;
                  transport.readCanonicalAck=async(s,e,ch)=>{
                    const p=await freshRead(s,e,ch);
                    return {...p,issued_at_ms:Date.now()-80000,
                      expires_at_ms:Date.now()-70000};
                  };
                }""")
                check("expired canonical ACK GET fails closed",
                      evaluate(nextpage,"client.reconnect(s1)")=="HOLD_CROSSTAB_READBACK")
                nextpage.evaluate("()=>{transport.readCanonicalAck=freshRead}")
                nextpage.evaluate("()=>fetch('/tamper')")
                check("forged canonical receipt fails closed",
                      evaluate(nextpage,"client.reconnect(s1)")=="HOLD_CROSSTAB_RECEIPT_UNVERIFIED")
                final=nextpage.evaluate("()=>fetch('/counts').then(r=>r.json())")
                check("tampering/reload produced no extra network POST",
                      final==counts)
                nextpage.evaluate("()=>gate.close()")
                ctx.close();browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

if __name__ == "__main__":
    main()
