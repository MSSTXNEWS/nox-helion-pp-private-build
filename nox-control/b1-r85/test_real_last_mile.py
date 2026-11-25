"""R85 real DOM differential of pinned R82/R84. Fixture authority only."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<!doctype html><meta charset=utf-8><main id=chat></main>")
    def log_message(self, *args):
        pass
CASE = r"""async baseline => {
if (!isSecureContext || !crypto.subtle) throw Error("secure context required");
async function exercise(root, baseline=false){
 const check=(b,m)=>{if(!b)throw Error(m)};
 const hash=async s=>Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',new root.TextEncoder().encode(s))),b=>b.toString(16).padStart(2,'0')).join('');
 const results=[];
 for(const n of [2,3])for(const fault of ['none','reserve-text','begin-hide','begin-replace','begin-stop','historical']){
  const s={conversation_id:'conv',exchange_id:'ex'+n}, visible=n===2?'Привет 🌞 ¡Hola!':'¿Qué tal? — отлично', digest=await hash(visible);
  const proof={schema:'NOX_B5_CANONICAL_ASSISTANT_TEXT_V1',...s,physical_dialog_id:'physical',s03_dialog_id:'dialog',s03_session_id:'session',served_sha256:'ab'.repeat(32),sequence:n,request_id:'req'+n,attempt_id:'att'+n,s03_event_id:'evt'+n,s03_turn_id:'turn'+n,assistant_message_id:'assistant'+n,assistant_text:visible,answer_sha256:digest,writer_sha256:'ac'.repeat(32),readback_sha256:'ad'.repeat(32),link_sha256:'ae'.repeat(32)};
  const el=document.createElement('div'); Object.assign(el.dataset,{noxB1Conversation:'conv',noxB1Exchange:s.exchange_id,noxB1EventId:'projection'+n,noxB1State:'terminal'});el.textContent=visible;
  const container=document.querySelector('#chat');for(const old of Array.from(container.children))if(old.dataset.noxB1Exchange===s.exchange_id)old.remove();container.append(el);check(el.getClientRects().length>0,'visible real DOM');
  const context={scope:{conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'dialog',session_id:'session',served_sha256:proof.served_sha256,server_sha256:'cd'.repeat(32),owner_admission_receipt_sha256:'ef'.repeat(32)},terminal:{turn:n,exchange_id:s.exchange_id,request_id:proof.request_id,attempt_id:proof.attempt_id,event_id:proof.s03_event_id,turn_id:proof.s03_turn_id,user_message_id:'user'+n,assistant_message_id:proof.assistant_message_id,answer_sha256:digest,state:'TERMINAL_SAVED',eof:true},browser_sha256:'12'.repeat(32),terminal_receipt_sha256:'34'.repeat(32),ack_state:fault==='historical'?'SENDING':'NOT_SENT'};
  let posts=0,acks=0,retained=0,begins=0,client;
  const host={readCommitted:async()=>null,verifyCanonicalText:async()=>true,verifyCanonicalAck:async()=>false,verifyFreshCanonicalAck:async()=>false,readPreAckContext:async()=>context,retainPreAckObservation:async()=>{retained++;return true}};
  const transport={post:async()=>{posts++;throw Error('POST forbidden')},readback:async()=>({...s,canonical_assistant_text:proof}),ack:async()=>{acks++;return true},readCanonicalAck:async()=>{throw Error('no fixture authority')}};
  const ackGate={reserve:async()=>{if(fault==='historical')throw Object.assign(Error('uncertain'),{code:'HOLD_CROSSTAB_ACK_UNCERTAIN'});if(fault==='reserve-text')el.textContent+='!';return {status:'RESERVED'}},beginSend:async()=>{begins++;if(fault==='begin-hide')el.hidden=true;if(fault==='begin-replace')el.replaceWith(el.cloneNode(true));if(fault==='begin-stop')client.stop(s);return 'SENDING'},confirm:async()=>{},requireCanonicalAck:async()=>{throw Error('fixture authority absent')}};
  client=root.NOXB1StreamReconnect.createClient({transport,host,bridge:{acceptTerminal:async packet=>({...packet,safe_to_ack:true,model_post:false,projection_event_id:'projection'+n,ack_cursor:'cursor'+n})},ui:{onDelta:async()=>true,upsertTerminal:async()=>true},ackGate,observePreAck:root.NOXB1PreAckObserver.create({container,host})});
  let status;try{await client.reconnect(s)}catch(e){status=e.code}
  const expected=fault==='none'||(baseline&&['reserve-text','begin-hide','begin-replace'].includes(fault))?1:0;
  check(acks===expected,'ack count '+n+' '+fault+' '+acks+' '+status);
  check(posts===0,'no POST');
  check(retained===(fault==='historical'?0:1),'retained '+fault);
  if(!baseline&&fault==='reserve-text')check(begins===0,'reserve mutation before begin');
  if(!baseline&&['reserve-text','begin-hide','begin-replace'].includes(fault))check(status==='HOLD_B1_PREACK_OBSERVATION','stale guard '+status);
  results.push({n,fault,acks,begins,status});
 }
 return results;
}
return await exercise(window,baseline);
}"""
if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            results = []
            for revision, baseline in [("b1-r82", True), ("b1-r84", False)]:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                page.add_script_tag(path=str(ROOT / revision / "b1_browser_bundle.js"))
                cases = page.evaluate(CASE, baseline)
                assert len(cases) == 12
                assert sum(c["acks"] for c in cases) == (8 if baseline else 2)
                assert page.locator("#chat > div").count() == 2
                results.append(cases)
                page.close()
            print("B1_R85_BROWSER", {"before": results[0], "after": results[1], "real_dom": True, "real_webcrypto": True, "authority": "fixture", "native_accepted": False, "live_post": 0, "live_ack": 0}, flush=True)
            browser.close()
    finally:
        server.shutdown()
