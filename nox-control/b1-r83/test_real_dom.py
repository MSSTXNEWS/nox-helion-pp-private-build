"""Real DOM test, derived from exact R82 fixture. No real authority or live calls."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Thread
from playwright.sync_api import sync_playwright
BUNDLE = Path(__file__).resolve().parents[1] / "b1-r82/b1_browser_bundle.js"
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<!doctype html><meta charset=utf-8><main id=chat></main>")
    def log_message(self, *args):
        pass
CASE = r"""async () => {
const assert={equal:(a,b)=>{if(a!==b)throw Error('assert '+a+' !== '+b)},rejects:async fn=>{let err;try{await fn()}catch(e){err=e}if(!err||err.code!=='HOLD_B1_PREACK_OBSERVATION')throw Error('expected HOLD, got '+String(err))}};
const sha=async s=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),b=>b.toString(16).padStart(2,'0')).join('');
const container=document.querySelector('#chat'),cases=[];
assert.equal(isSecureContext,true);
const sc={conversation_id:'conv',physical_dialog_id:'physical',s03_dialog_id:'dialog',session_id:'session',served_sha256:'ab'.repeat(32),server_sha256:'cd'.repeat(32),owner_admission_receipt_sha256:'ef'.repeat(32)};
for(const n of [2,3]){
const text=n===2?'Привет 🌞 ¡Hola!':'¿Qué tal? — отлично';
const hash=await sha(text),s={conversation_id:'conv',exchange_id:'ex'+n};
const proof={physical_dialog_id:'physical',s03_dialog_id:'dialog',s03_session_id:'session',served_sha256:sc.served_sha256,sequence:n,request_id:'req'+n,attempt_id:'att'+n,s03_event_id:'evt'+n,s03_turn_id:'turn'+n,assistant_message_id:'assistant'+n,answer_sha256:hash};
const t={turn:n,exchange_id:s.exchange_id,request_id:proof.request_id,attempt_id:proof.attempt_id,event_id:proof.s03_event_id,turn_id:proof.s03_turn_id,user_message_id:'user'+n,assistant_message_id:proof.assistant_message_id,answer_sha256:hash,state:'TERMINAL_SAVED',eof:true};
const el=document.createElement('div'); Object.assign(el.dataset,{noxB1Conversation:'conv',noxB1Exchange:s.exchange_id,noxB1EventId:'projection'+n,noxB1State:'terminal'});el.textContent=text;container.append(el);
const context={scope:sc,terminal:t,browser_sha256:'12'.repeat(32),terminal_receipt_sha256:'34'.repeat(32),ack_state:'NOT_SENT'};
let retained=[],mutate=null;
const host={readPreAckContext:async()=>context,retainPreAckObservation:async pair=>{retained.push(pair);if(mutate)mutate();return true;}};
const observe=NOXB1PreAckObserver.create({container,host,crypto});
const w={projection_event_id:'projection'+n};
const run=()=>observe(s,proof,w,new AbortController().signal);
assert.equal(await run(),true);const pair=retained.pop(),doc=JSON.parse(pair.bytes);assert.equal(pair.sha256,await sha(pair.bytes));assert.equal(doc.visible_text_sha256,hash);assert.equal(doc.turn,n);assert.equal(Object.keys(doc).length,23);cases.push('turn'+n);
el.hidden=true;await assert.rejects(run);el.hidden=false;
const dup=el.cloneNode(true);container.append(dup);await assert.rejects(run);dup.remove();
container.style.opacity='0';await assert.rejects(run);container.style.opacity='';
el.style.visibility='hidden';await assert.rejects(run);el.style.visibility='';
el.setAttribute('aria-hidden','true');await assert.rejects(run);el.removeAttribute('aria-hidden');
el.textContent+='!';await assert.rejects(run);el.textContent=text;
t.attempt_id='foreign';await assert.rejects(run);t.attempt_id=proof.attempt_id;
context.ack_state='SENDING';assert.equal(await run(),false);context.ack_state='NOT_SENT';
const stop=new AbortController();stop.abort();await assert.rejects(()=>observe(s,proof,w,stop.signal));
assert.equal(retained.length,0);
const during=new AbortController();mutate=()=>during.abort();await assert.rejects(()=>observe(s,proof,w,during.signal));assert.equal(retained.length,1);retained.pop();
mutate=()=>{el.textContent='changed'};await assert.rejects(run);retained.pop();el.textContent=text;cases.push('negative'+n);
}

assert.equal(container.children.length,2);
return {cases,rows:container.children.length,real_dom:true,real_webcrypto:true,native_accepted:false,authority:'fixture',live_post:0,live_ack:0};
}"""
if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            page.add_script_tag(content=BUNDLE.read_text(encoding="utf-8"))
            result = page.evaluate(CASE)
            assert result["cases"] == ["turn2", "negative2", "turn3", "negative3"]
            print("B1_R83_BROWSER", result, flush=True)
            browser.close()
    finally:
        server.shutdown()
