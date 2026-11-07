#!/usr/bin/env python3
r"""NOX WEB · actual localhost browser + API receipt (source v0.0.6).

Uses only the existing NOX LIVE browser server. No mock service, no Windows EXE.
No training or S03 mutations; optional --real-chat generates a short Qwen reply.
Example:
  py VERIFY_NOX_WEB.py --url http://127.0.0.1:18775 --out C:\NOX_HELION\QA_WEB_11_22
"""
import argparse
import asyncio
import hashlib
import json
import re
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

PAGES=("index.html","chat.html","training.html","models.html","memory.html",
       "system.html","install.html","projects.html","settings.html")
VIEWPORTS=((320,720),(390,844),(800,480),(1920,1080))
API=("/api/mega/health","/api/status","/api/s03/status",
     "/api/training/status","/api/pc-metrics")

def url_ok(raw):
    u=urlsplit(raw)
    if u.scheme!="http" or u.hostname not in ("127.0.0.1","localhost") or not u.port:
        raise ValueError("NOX_WEB_LOCAL_URL_ONLY_HOLD")
    if u.username or u.password or u.query or u.fragment:
        raise ValueError("NOX_WEB_URL_SUFFIX_HOLD")
    return raw.rstrip("/")

def digest(file):
    h=hashlib.sha256()
    with file.open("rb") as src:
        for block in iter(lambda:src.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def json_get(url):
    with urllib.request.urlopen(url,timeout=7) as r:
        if r.status!=200:raise ValueError("API_HTTP_"+str(r.status))
        return json.load(r)

def probe_api(base):
    data={}
    for path in API:data[path]=json_get(base+path)
    health=data["/api/mega/health"]
    if health.get("identity")!="NOX_LOCAL_LIVE_V1" or health.get("status")!="READY" or health.get("releaseAccepted") is not False:
        raise RuntimeError("NOX_WEB_IDENTITY_NOT_CURRENT_SOURCE_HOLD")
    return data

def probe_pages(base):
    records=[]
    for name in PAGES:
        with urllib.request.urlopen(base+"/"+name,timeout=7) as r:
            body=r.read(2_000_000).decode("utf-8-sig")
            if r.status!=200 or "NOX" not in body.upper() or "<html" not in body.lower():
                raise RuntimeError("NOX_WEB_PAGE_NOT_REAL_HOLD:"+name)
            records.append({"page":name,"http":r.status,"html_sha256":hashlib.sha256(body.encode("utf-8")).hexdigest()})
    return records

def chat_smoke(base,models):
    names=[m.get("name") for m in models if isinstance(m,dict)]
    model=next((m for m in names if isinstance(m,str) and re.search("qwen|nox",m,re.I)),None)
    if not model:raise RuntimeError("NOX_LOCAL_MODEL_NOT_FOUND_HOLD")
    request_id=str(uuid.uuid4())
    payload=json.dumps({"request_id":request_id,"model":model,
      "messages":[{"role":"user","content":"Ответь одним русским словом: привет"}]}).encode("utf-8")
    req=urllib.request.Request(base+"/api/chat",data=payload,
      headers={"Content-Type":"application/json","Origin":base},method="POST")
    chunks=[];completed=False
    with urllib.request.urlopen(req,timeout=75) as res:
        if res.status!=200 or "ndjson" not in res.headers.get("Content-Type",""):
            raise RuntimeError("NOX_CHAT_NOT_STREAMING_HOLD")
        for raw in res:
            obj=json.loads(raw)
            if obj.get("error"):raise RuntimeError("NOX_CHAT_UPSTREAM_HOLD:"+str(obj["error"]))
            text=obj.get("message",{}).get("content","")
            if isinstance(text,str):chunks.append(text)
            if obj.get("done") is True:completed=True;break
    answer="".join(chunks).strip()
    if not completed or not answer:raise RuntimeError("NOX_CHAT_NO_COMPLETE_TEXT_HOLD")
    return {"status":"LIVE_OLLAMA_STREAM_PASS","model":model,"requestId":request_id,
            "answer_length":len(answer),"sample":answer[:100],"memoryPersisted":"NOT_TESTED"}

async def screenshot_check(base,out):
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("PLAYWRIGHT_NOT_INSTALLED_HOLD") from e
    captures=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        try:
            for w,h in VIEWPORTS:
                context=await browser.new_context(viewport={"width":w,"height":h},
                                                 service_workers="block")
                page=await context.new_page()
                try:
                    errors=[]
                    page.on("pageerror",lambda e:errors.append(str(e)))
                    response=await page.goto(base+"/",wait_until="domcontentloaded",timeout=15000)
                    if not response or response.status!=200:raise RuntimeError("WEB_BROWSER_HTTP_HOLD")
                    title=await page.title()
                    if "NOX HELION" not in title:raise RuntimeError("WEB_BROWSER_TITLE_HOLD")
                    await page.locator("#openCoreChat").click(timeout=7000)
                    await page.wait_for_url("**/chat.html",timeout=7000)
                    if await page.locator("#chatForm").count()!=1:
                        raise RuntimeError("WEB_CHAT_DOM_MISSING_HOLD")
                    await page.get_by_role("button",name="Дописать").click(timeout=5000)
                    if not (await page.locator("#prompt").input_value()).startswith("Дописать:"):
                        raise RuntimeError("WEB_CHAT_BUTTON_NOT_REAL_HOLD")
                    if not await page.locator("#stop").is_disabled():
                        raise RuntimeError("WEB_IDLE_STOP_NOT_DISABLED_HOLD")
                    if errors:raise RuntimeError("WEB_BROWSER_JS_ERRORS_HOLD:"+errors[0][:120])
                    for mode in ("reduce","no-preference"):
                        await page.emulate_media(reduced_motion=mode)
                        flag=await page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
                        if flag!=(mode=="reduce"):raise RuntimeError("WEB_REDUCED_MOTION_HOLD")
                        shot=out/f"NOX_CHAT_{w}x{h}_{mode}.png"
                        await page.screenshot(path=str(shot),animations="disabled",full_page=False)
                        if shot.stat().st_size<1000:raise RuntimeError("NOX_BROWSER_SCREENSHOT_EMPTY_HOLD")
                        captures.append({"width":w,"height":h,"mode":mode,
                                         "name":shot.name,"sha256":digest(shot)})
                finally:
                    await context.close()
        finally:
            await browser.close()
    if len(captures)!=8:raise RuntimeError("WEB_BROWSER_EXPECTED_EIGHT_SCREENSHOTS_HOLD")
    return captures

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="http://127.0.0.1:18775")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--real-chat",action="store_true")
    a=p.parse_args()
    receipt={"schema":"NOX_WEB_OWNER_11_22_PHYSICAL_QA_V1",
        "created_at":datetime.now(timezone.utc).isoformat(),"releaseAccepted":False,
        "gpuTraining":"NOT_TESTED","safe70":"NOT_OVERRIDDEN",
        "s03Persistence":"NOT_TESTED","projectsWrites":"NOT_TESTED",
        "voiceRuEs":"NOT_TESTED","autonomousWorker":"NOT_TESTED",
        "browser":"HOLD","liveChat":"NOT_TESTED"}
    try:
        base=url_ok(a.url)
        if a.out.exists() and any(a.out.iterdir()):
            raise RuntimeError("QA_DESTINATION_NOT_EMPTY_HOLD")
        a.out.mkdir(parents=True,exist_ok=True)
        api=probe_api(base)
        receipt["api"]=api
        receipt["pages"]=probe_pages(base)
        if a.real_chat:
            receipt["liveChat"]=chat_smoke(base,api["/api/status"].get("models",[]))
        receipt["screenshots"]=asyncio.run(screenshot_check(base,a.out))
        receipt["browser"]="UI_PHYSICAL_PASS"
        receipt["status"]="WEB_SCOPE_PASS_REST_HOLD"
        print("NOX WEB browser and API checks passed; no complete release claim.")
        code=0
    except Exception as exc:
        receipt["status"]="WEB_QA_HOLD"
        receipt["firstFail"]=type(exc).__name__+":"+str(exc)
        print("NOX WEB QA HOLD:",receipt["firstFail"],file=sys.stderr)
        code=2
    # The receipt is a truthful test trace, not proof of untested functionality.
    if a.out.is_dir():
        (a.out/"NOX_WEB_OWNER_QA_RECEIPT.json").write_text(
            json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    return code
if __name__=="__main__":raise SystemExit(main())
