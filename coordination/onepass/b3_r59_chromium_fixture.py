#!/usr/bin/env python3
"""B3 R59: exact bridge A/B in a real, network-fenced Chromium fixture.
NOT live NOX rendering, GPU, installed model or S03 evidence.
"""
import hashlib
import json
import pathlib
import statistics
import subprocess
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path("coordination/onepass")
OUT = pathlib.Path("b3-r59-browser-evidence")
BASE_SHA = "1a9d46ea35042efe05d081e0d89642609c127a7fdc18c44b8235e03b21bbdce4"
NEXT_SHA = "779f308a18cb652fe7dbe5b555750068ee121fbfe4ec4ea6a8d0a9e9f58581a0"
URL = "https://fixture.invalid/nox-web-v29/pc/resonance.html"
HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{font:16px system-ui;background:#171920;color:#eee;margin:16px}
#phase{padding:12px;background:#333;border-radius:8px}
#answer{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;border:1px solid #777}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body><h1>B3 streaming fixture</h1><div id="phase">idle</div><div id="answer"></div></body></html>"""
BOOT = r"""() => {
 window.NOX_NATIVE_OWNER=true;
 const id='a'.repeat(32), rows=[];
 const tokens=Array.from({length:128},(_,i)=>['Привет ','¿sí? ','👩‍💻 ','NOX '][i%4]);
 const answer=tokens.join('');
 let label='GLM-5.3-Flash',posts=0,stops=0,reads=0;
 const phases=[];
 const phase=document.querySelector('#phase'), output=document.querySelector('#answer');
 window.addEventListener('nox:native-phase', e=>{
   phases.push(e.detail.phase); phase.textContent=e.detail.phase;
 });
 const json=x=>new Response(JSON.stringify(x),{headers:{'Content-Type':'application/json'}});
 window.fetch=async(path,init={})=>{
   const u=new URL(String(path),location.href);
   if(u.origin!==location.origin)throw Error('unexpected origin');
   if(u.pathname==='/api/nox/stop'){stops++;return json({status:'STOP_REQUESTED',stream_cancellation_signalled:true});}
   if(u.pathname==='/api/ui/memory/dialogs/history'){
     reads++;return json({status:'READY',dialog_id:id,messages:rows});
   }
   if(u.pathname!=='/api/nox/chat/stream')throw Error('unexpected path '+u.pathname);
   const data=JSON.parse(init.body);
   if(data.dialog_id!==id)throw Error('wrong dialog');
   const ex='fixture-exchange-'+(++posts);
   const frames=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM',dialog_id:id},
     {type:'start',model:label,dialog_id:id},
     ...tokens.map(text=>({type:'delta',text,dialog_id:id})),
     {type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:ex}];
   rows.push({role:'user',content:data.message,exchange_id:ex},{role:'assistant',content:answer,exchange_id:ex});
   let pos=0,timer;
   const encoder=new TextEncoder();
   return new Response(new ReadableStream({
      start(c){timer=setInterval(()=>{if(pos===frames.length){clearInterval(timer);c.close();return;}c.enqueue(encoder.encode(JSON.stringify(frames[pos++])+'\n'));},4);},
      cancel(){clearInterval(timer);}
   }));
 };
 async function turn(){
   const r=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({dialog_id:id,request_id:'fixture-'+(posts+1),message:'Вопрос ¿sí?'})});
   const reader=r.body.getReader(),decoder=new TextDecoder();let pending='',text='',events=[];
   for(;;){
     const x=await reader.read(); if(x.done)break;
     pending+=decoder.decode(x.value,{stream:true});
     let end;
     while((end=pending.indexOf('\n\n'))!==-1){
       const e=JSON.parse(pending.slice(6,end));pending=pending.slice(end+2);events.push(e);
       if(e.type==='token'){text+=e.t;output.textContent=text;}
     }
   }
   if(pending+decoder.decode())throw Error('incomplete SSE');
   return {text,events};
 }
 window.runFixture=async()=>{
   let last,frames=[];
   const sample=(async()=>{for(let i=0;i<91;i++){const t=await new Promise(requestAnimationFrame);if(last!==undefined)frames.push(t-last);last=t;}})();
   const turns=[await turn(),await turn()];
   await sample;
   const phaseSnapshot=phases.slice();
   const prior={posts,stops,reads};
   label='Qwen-drift';
   const drift=await turn();
   return {answer,turns,frames,phases:phaseSnapshot,prior,drift,counts:{posts,stops,reads},
     reduced:matchMedia('(prefers-reduced-motion: reduce)').matches};
 };
}"""

def digest(payload):
    return hashlib.sha256(payload).hexdigest()

def summarize(frames):
    assert len(frames) == 90 and all(0 < x < 120000 for x in frames)
    ordered = sorted(frames)
    return {"frames": 90, "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[85], 3), "over_50ms": sum(x > 50 for x in ordered)}

def normalized(events):
    return [{k:v for k,v in e.items() if k not in ("seconds","first_visible_token_ms")} for e in events]

def measure(browser, src, variant, w, h, motion):
    ctx = browser.new_context(viewport={"width":w,"height":h}, device_scale_factor=1,
                              reduced_motion=motion, service_workers="block")
    blocked=[]
    def fence(route):
        if route.request.url == URL and route.request.method == "GET":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=HTML)
        else:
            blocked.append(route.request.method)
            route.abort()
    ctx.route("**/*", fence)
    try:
        page=ctx.new_page()
        page.goto(URL)
        page.evaluate(BOOT)
        page.add_script_tag(content=src.decode("utf-8"))
        assert page.evaluate("window.__NOX_V135_OWNER_RESONANCE") == "OWNER_NATIVE_ONLY"
        data=page.evaluate("window.runFixture()")
        assert data["reduced"] == (motion=="reduce")
        assert data["prior"] == {"posts":2,"stops":0,"reads":2}
        assert data["counts"] == {"posts":3,"stops":1,"reads":2}
        for turn in data["turns"]:
            assert turn["text"] == data["answer"]
            done=[e for e in turn["events"] if e["type"]=="done"]
            assert len(done)==1 and done[0]["model_label"]=="GLM-5.3-Flash"
            assert done[0]["model_identity_verified"] is False
            assert not [e for e in turn["events"] if e["type"]=="error"]
        assert data["drift"]["text"] == ""
        assert [e["error"] for e in data["drift"]["events"] if e["type"]=="error"] == ["HOLD_DIALOG_MODEL_DRIFT"]
        assert not [e for e in data["drift"]["events"] if e["type"]=="done"]
        assert not blocked
        name=f"{variant}_{w}x{h}_{motion}.png"
        png=page.screenshot(path=OUT/name, animations="disabled")
        assert int.from_bytes(png[16:20],"big")==w and int.from_bytes(png[20:24],"big")==h
        return {"variant":variant,"width":w,"height":h,"motion":motion,
                "frame_time":summarize(data["frames"]), "phase_events":len(data["phases"]),
                "screenshot":name,"screenshot_sha256":digest(png),"bridge_sha256":digest(src),
                "turns":[normalized(t["events"]) for t in data["turns"]],
                "phases":data["phases"]}
    finally:
        ctx.close()

def main():
    before=(ROOT/"b3_r56_combined_candidate.js").read_bytes()
    after=subprocess.check_output(["node",str(ROOT/"b3_r57_phase_transition_port.cjs"),"--emit"])
    assert digest(before)==BASE_SHA and digest(after)==NEXT_SHA
    OUT.mkdir(exist_ok=True)
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        version=browser.version
        try:
            for w,h in [(320,720),(390,844),(1440,900)]:
                for motion in ("no-preference","reduce"):
                    a=measure(browser,before,"before",w,h,motion)
                    b=measure(browser,after,"after",w,h,motion)
                    assert a["turns"]==b["turns"]
                    assert b["phases"]==["waiting","speaking","idle"]*2
                    assert a["phase_events"]>b["phase_events"]
                    for r in (a,b):
                        del r["turns"],r["phases"]
                    results.append({"before":a,"after":b,
                                    "p95_delta_ms":round(b["frame_time"]["p95_ms"]-a["frame_time"]["p95_ms"],3)})
        finally:
            browser.close()
    report={"schema":"NOX_B3_R59_CHROMIUM_FIXTURE_V1","chromium":version,
            "synthetic_fixture":True,"native_accepted":False,"real_nox_ui":False,
            "fixture_html_sha256":digest(HTML.encode()),"results":results}
    (OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps(report))
if __name__=="__main__":
    main()
