#!/usr/bin/env python3
r"""NOX WEB: read-only localhost browser acceptance. Not EXE, not fake PASS.
Use: py WEB_BROWSER_QA.py --url http://127.0.0.1:18775 --out C:\NOX_HELION\QA_WEB
Requires existing Playwright/Chromium installation; never downloads anything.
"""
import argparse, asyncio, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

VIEWPORTS=[(320,720),(390,844),(800,480),(1920,1080)]
REQUIRED=(r"CHAT|ЧАТ|QWEN",r"MEMORY|ПАМЯТ|SQLITE",r"MODEL|МОДЕЛ|OLLAMA",r"TRAINING|ОБУЧЕНИЕ|LEARN|FORGE")
def local_url(url):
    u=urlsplit(url)
    if u.scheme!="http" or u.hostname not in ("127.0.0.1","localhost") or not u.port or u.query or u.fragment or u.username or u.password:
        raise RuntimeError("WEB_NON_LOCAL_URL_HOLD")
    return url.rstrip("/")
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
async def run(url,out):
    from playwright.async_api import async_playwright
    if out.exists() and any(out.iterdir()):raise RuntimeError("WEB_QA_TARGET_NOT_EMPTY_HOLD")
    out.mkdir(parents=True,exist_ok=True)
    receipt=dict(schema="NOX_WEB_8_SCREENSHOTS_V1",url=url,
       utc=datetime.now(timezone.utc).isoformat(),releaseAccepted=False,
       browserScope="NOT_TESTED",ollamaStreamStop="NOT_TESTED",sqliteRestart="NOT_TESTED",
       gpuWorker="NOT_TESTED",voiceRU_ES="NOT_TESTED",autonomy="NOT_TESTED",screenshots=[])
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        try:
            for w,h in VIEWPORTS:
                ctx=await browser.new_context(viewport={"width":w,"height":h},service_workers="block")
                page=await ctx.new_page()
                try:
                    response=await page.goto(url,wait_until="domcontentloaded",timeout=15000)
                    if response is None or response.status!=200:raise RuntimeError("WEB_HTTP_ERROR_HOLD")
                    text=(await page.title())+" "+await page.locator("body").inner_text(timeout=4000)
                    if not re.search(r"NOX[\s._-]*HELION",text,re.I):raise RuntimeError("NOT_NOX_HELION_OR_OLD_SITE_HOLD")
                    for keyword in REQUIRED:
                        if not re.search(keyword,text,re.I):raise RuntimeError("WEB_NAV_MISSING_HOLD:"+keyword)
                    if re.search(r"NOX_STATIC_DEMO_ONLY|NOX_MOCK_MODE|NOX_FAKE_BACKEND",text,re.I):
                        raise RuntimeError("WEB_FAKE_MODE_HOLD")
                    for mode in ("no-preference","reduce"):
                        await page.emulate_media(reduced_motion=mode)
                        matching=await page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
                        if matching!=(mode=="reduce"):raise RuntimeError("WEB_MOTION_MEDIA_QUERY_HOLD")
                        filename=f"nox_web_{w}x{h}_{mode}.png"
                        target=out/filename
                        await page.screenshot(path=str(target),full_page=False,animations="disabled")
                        if target.stat().st_size<1000:raise RuntimeError("WEB_SCREENSHOT_EMPTY_HOLD")
                        receipt["screenshots"].append(dict(path=filename,sha256=sha(target),width=w,height=h,motion=mode))
                finally:
                    await ctx.close()
        finally:
            await browser.close()
    if len(receipt["screenshots"])!=8:raise RuntimeError("WEB_SCREENSHOT_COUNT_HOLD")
    receipt["browserScope"]="PASS"
    receipt["status"]="UI_ONLY_PASS_RELEASE_HOLD"
    (out/"WEB_QA_RECEIPT.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
    return receipt
def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--url",default="http://127.0.0.1:18775")
    pa.add_argument("--out",required=True,type=Path)
    args=pa.parse_args()
    try:
        r=asyncio.run(run(local_url(args.url),args.out))
        print(json.dumps({"status":r["status"],"screenshots":len(r["screenshots"]),"releaseAccepted":False}))
        return 0
    except Exception as ex:
        print("NOX_WEB_QA_HOLD:",type(ex).__name__,str(ex))
        return 2
if __name__=="__main__":raise SystemExit(main())
