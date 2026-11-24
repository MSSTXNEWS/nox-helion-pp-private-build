#!/usr/bin/env python3
"""R62: run exact R61 bytes in Chromium; no network or native acceptance."""
import json
import hashlib
import pathlib
import b3_r59_chromium_fixture as old
from playwright.sync_api import sync_playwright

ROOT=pathlib.Path("coordination/onepass")
OUT=pathlib.Path("b3-r62-browser-evidence")
PIN="9cd1cd1ab96a01b295418b59d53669b742d804520af15e3da648716b02427ef3"

def overlap(browser, src):
    ctx=browser.new_context(service_workers="block")
    blocked=[]
    def fence(route):
        if route.request.url==old.URL and route.request.method=="GET":
            route.fulfill(status=200,content_type="text/html; charset=utf-8",body=old.HTML)
        else:
            blocked.append(route.request.method)
            route.abort()
    ctx.route("**/*",fence)
    try:
        page=ctx.new_page()
        page.goto(old.URL)
        # Delay the first history readback; wait until it is pending before the overlap.
        boot=old.BOOT.replace("const phases=[];", "const phases=[]; let releaseRead, notifyRead; const pendingRead=new Promise(r=>notifyRead=r);")
        boot=boot.replace("reads++;return json", "reads++; if(reads===1){await new Promise(r=>{releaseRead=r;notifyRead();});} return json")
        assert boot != old.BOOT and "notifyRead();" in boot
        boot=boot.replace("window.runFixture=async()=>{", """window.overlap=async()=>{
          const first=turn();
          await pendingRead;
          const second=await turn();
          const whilePending={posts,stops,reads};
          releaseRead();
          const completed=await first;
          const third=await turn();
          return {second,whilePending,completed,third,answer,counts:{posts,stops,reads}};
        };
        window.runFixture=async()=>{""")
        page.evaluate(boot)
        page.add_script_tag(content=src.decode("utf-8"))
        d=page.evaluate("window.overlap()")
        assert d["whilePending"]=={"posts":1,"stops":0,"reads":1}
        assert d["second"]["text"]==""
        assert [e["error"] for e in d["second"]["events"] if e["type"]=="error"]==["HOLD_DIALOG_IDENTITY_IN_FLIGHT"]
        assert not [e for e in d["second"]["events"] if e["type"]=="done"]
        for t in (d["completed"],d["third"]):
            assert t["text"]==d["answer"]
            assert len([e for e in t["events"] if e["type"]=="done"])==1
        assert d["counts"]=={"posts":2,"stops":0,"reads":2}
        assert not blocked
        return {"while_pending":d["whilePending"],"final_counts":d["counts"],"overlap_rejected_before_post":True}
    finally:
        ctx.close()

def main():
    before=(ROOT/"b3_r56_combined_candidate.js").read_bytes()
    after=(ROOT/"b3_r61_release_candidate.js").read_bytes()
    assert old.digest(before)==old.BASE_SHA and old.digest(after)==PIN and len(after)==24786
    manifest=json.loads((ROOT/"b3_r61_release_input.json").read_text())
    assert manifest["candidate"]["sha256"]==PIN and manifest["candidate"]["admitted"] is False
    OUT.mkdir(exist_ok=True)
    old.OUT=OUT
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            for w,h in [(320,720),(390,844),(1440,900)]:
                for motion in ("no-preference","reduce"):
                    a=old.measure(browser,before,"before",w,h,motion)
                    b=old.measure(browser,after,"r61",w,h,motion)
                    assert a["turns"]==b["turns"]
                    assert b["phases"]==["waiting","speaking","idle"]*2
                    assert a["phase_events"]>b["phase_events"]
                    for row in (a,b):
                        del row["turns"],row["phases"]
                    results.append({"before":a,"after":b,"p95_delta_ms":round(b["frame_time"]["p95_ms"]-a["frame_time"]["p95_ms"],3)})
            race=overlap(browser,after)
            report={"schema":"NOX_B3_R62_EXACT_RELEASE_CHROMIUM_V1","chromium":browser.version,"candidate_sha256":PIN,"synthetic_fixture":True,"native_accepted":False,"real_nox_ui":False,"results":results,"overlap":race}
        finally:
            browser.close()
    (OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps(report))
if __name__=="__main__":
    main()
