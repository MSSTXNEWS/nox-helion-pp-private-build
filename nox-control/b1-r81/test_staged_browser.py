"""Exact B0 R72 staged wire -> R79 real browser DOM; synthetic provider only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

stage = Path(sys.argv[1]).resolve()
manifest = json.loads((stage / "manifest.json").read_text())
assert manifest["schema"] == "NOX_B0_R72_PROXY_STAGING_V1"
assert manifest["native_accepted"] is False and manifest["next_post_allowed"] is False
for f in manifest["files"]:
    raw = (stage / f["name"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == f["sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == f["git_blob"]
assert next(f for f in manifest["files"] if f["name"] == "b1_browser_bundle.js")["git_blob"] == "b42f00e572ad000b87d7e9e5bf210aba0362494a"
frames = [
    {"type":"delta","event_id":"existing:2:1","text":"Привет 🌞 "},
    {"type":"delta","event_id":"existing:2:2","text":"¡Hola!"},
    {"type":"delta","event_id":"existing:3:1","text":"Продолжаем. Sí."}
]
def wire(frame):
    return list(subprocess.check_output([sys.executable, "-B", "-c",
        "import json,sys\nfrom b0_proxy_stream_iter import ProxyDeltaBody\n"
        "def source(): yield json.load(sys.stdin)\nbody=ProxyDeltaBody(source())\n"
        "try:\n for data in body: sys.stdout.buffer.write(data)\nfinally: body.close()\n"],
        input=json.dumps(frame).encode(), cwd=stage))
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.route("https://fixture.invalid/", lambda route: route.fulfill(body="<main id='chat'><div id='prior'>existing turn 1</div></main>", content_type="text/html"))
    page.goto("https://fixture.invalid/")
    page.add_script_tag(path=str(Path(__file__).with_name("b1_browser_bundle.js")))
    result = page.evaluate(r"""async ({frames,wire}) => {
      const check=(ok,label)=>{if(!ok)throw Error(label)};
      const container=document.querySelector('#chat');
      const s2={conversation_id:'existing',exchange_id:'turn-2'};
      const s3={conversation_id:'existing',exchange_id:'turn-3'};
      const row=s=>container.querySelector('[data-nox-b1-exchange="'+s.exchange_id+'"]');
      let entered,release,delta2=0,posts=[],gets=[],acks=[],cancel=0,mode='deny';
      const sha=async t=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(t))),x=>x.toString(16).padStart(2,'0')).join('');
      const canonical=s=>s.exchange_id==='turn-2'?frames[0].text+frames[1].text:frames[2].text;
      const proofFor=async s=>({schema:'NOX_B5_CANONICAL_ASSISTANT_TEXT_V1',...s,
        sequence:s.exchange_id==='turn-2'?2:3,physical_dialog_id:'physical',request_id:s.exchange_id+':request',
        attempt_id:s.exchange_id+':attempt',s03_dialog_id:'d',s03_session_id:'session',
        s03_event_id:s.exchange_id+':event',s03_turn_id:s.exchange_id+':turn',
        assistant_message_id:s.exchange_id+':assistant',assistant_text:canonical(s),
        answer_sha256:await sha(mode==='wrong-digest'?'wrong':canonical(s)),
        served_sha256:await sha('build'),writer_sha256:await sha('writer'),readback_sha256:await sha('reader'),
        link_sha256:await sha('link'),authentication_verified:false,native_accepted:false,ack_allowed:false});
      const waiting=new Promise(r=>entered=r),gate=new Promise(r=>release=r);
      const ui=NOXB1AbortSafeUI.createUiAdapter({container,beforeCommit(kind,s){
        if(kind==='delta'&&s.exchange_id==='turn-2'&&++delta2===2){entered();return gate}
      }});
      const transport={
        async post(s){posts.push(s.exchange_id);let i=0;
          const chunks=s.exchange_id==='turn-2'?[wire[0],wire[1]]:[wire[2]];
          return {ok:true,body:new ReadableStream({pull(c){
            if(i<chunks.length)c.enqueue(Uint8Array.from(chunks[i++]));
            else if(s.exchange_id==='turn-3')c.close();
          },cancel(){cancel++}},{highWaterMark:0})};
        },
        async readback(s){gets.push(s.exchange_id);return {...s,canonical_assistant_text:await proofFor(s)}},
        async ack(s){acks.push(s.exchange_id);return true}
      };
      const client=NOXB1StreamReconnect.createClient({transport,ui,host:{readCommitted:async()=>null,
        verifyCanonicalText:async(proof,s,witness)=>mode!=='deny'&&proof.exchange_id===s.exchange_id&&
          witness.projection_event_id===s.exchange_id+':terminal'&&proof.assistant_text===canonical(s)},
        bridge:{acceptTerminal:async(packet,s)=>({...packet,safe_to_ack:true,model_post:false,
          projection_event_id:s.exchange_id+':terminal',ack_cursor:s.exchange_id+':cursor'})},
        strictAckNoReplay:true,timeoutMs:10000});
      const begun=client.begin(s2);
      await Promise.race([waiting,new Promise((_,r)=>setTimeout(()=>r(Error('delta gate not reached')),3000))]);
      check(row(s2).textContent===frames[0].text,'first projected');
      check(client.stop(s2)===true,'stop dispatched');
      check(await begun==='STOPPED','stop settled');
      release();await new Promise(r=>setTimeout(r,30));
      check(row(s2).textContent===frames[0].text,'late delta fenced');
      check(cancel===1,'cancel once');
      async function rejects(fn,code){try{await fn();throw Error('unexpected success')}catch(e){check(e.code===code,code+': '+e.code)}}
      await rejects(()=>client.begin(s2),'HOLD_STREAM_NO_REPOST');
      const original=row(s2);
      await rejects(()=>client.reconnect(s2),'HOLD_STREAM_CANONICAL_TEXT');
      check(acks.length===0&&row(s2).dataset.noxB1State!=='terminal','unverified text no ACK');
      mode='wrong-digest';
      await rejects(()=>client.reconnect(s2),'HOLD_STREAM_UI_PROJECTION');
      check(acks.length===0&&row(s2).textContent===frames[0].text,'digest mismatch no ACK');
      mode='allow';
      const w=await client.reconnect(s2);
      check(row(s2)===original&&row(s2).textContent===canonical(s2),'same row exact canonical text');
      check(row(s2).dataset.noxB1State==='terminal'&&
        row(s2).dataset.noxB1AnswerSha256===await sha(row(s2).textContent)&&
        w.canonical_assistant_text.answer_sha256===await sha(row(s2).textContent),'terminal DOM digest');
      await rejects(()=>client.reconnect(s2),'HOLD_STREAM_ACK_UNCERTAIN_GET_ONLY');
      check(await client.begin(s3)==='STREAM_ENDED_READBACK_REQUIRED','third EOF');
      await client.reconnect(s3);
      check(row(s3).textContent===frames[2].text,'third full text');
      check(container.children.length===3&&document.querySelector('#prior').textContent==='existing turn 1','one DOM row per exchange');
      check(JSON.stringify(posts)===JSON.stringify(['turn-2','turn-3']),'exactly two fixture posts');
      check(JSON.stringify(gets)===JSON.stringify(['turn-2','turn-2','turn-2','turn-2','turn-3']),'GET-only recovery');
      check(JSON.stringify(acks)===JSON.stringify(['turn-2','turn-3']),'one mock ack per exchange');
      return {posts,gets,acks,cancel,dom_rows:container.children.length,stop_fence:true,
        canonical_text_recovery:true,native_accepted:false,independent_native_verifier:false};
    }""", {"frames":frames,"wire":[wire(f) for f in frames]})
    print("B1_R81_BROWSER", json.dumps(result,ensure_ascii=False))
    browser.close()
