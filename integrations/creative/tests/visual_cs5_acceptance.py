"""NOX B01–B05 visual preflight using exact original web code and SHA-locked HOME.
NOT a standalone UI or independent artistic approval.
Usage: python tests/visual_cs5_acceptance.py --approved-home /path/to/HOME.png
"""
import argparse
import functools
import hashlib
import http.server
import json
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

HOME_SHA = "382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a"
VIEWPORTS = [(320,680),(390,844),(800,480),(1024,768),(1440,900),(1920,1080)]
BLOCKS = ["B01","B02","B03","B04","B05"]

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(home,web,out,browser_path=None):
    home,web,out=Path(home).resolve(),Path(web).resolve(),Path(out).resolve()
    if not home.is_file() or home.is_symlink() or digest(home)!=HOME_SHA:
        raise RuntimeError("OWNER_HOME_SHA_HOLD")
    required=["studio.html","studio.css","studio.js","five_blocks.js","five_blocks_art.css"]
    if any(not (web/f).is_file() or (web/f).is_symlink() for f in required):
        raise RuntimeError("STUDIO_SOURCE_HOLD")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("PLAYWRIGHT_NOT_INSTALLED_HOLD") from exc
    out.mkdir(parents=True,exist_ok=True)
    receipt={"schema":"NOX_CS5_ART_PREFLIGHT_V1","owner_home_sha256":HOME_SHA,
             "source_sha256":{f:digest(web/f) for f in required},
             "screens":[],"errors":[],"art_independent_accepted":False,
             "native_e07_accepted":False,
             "created_utc":datetime.now(timezone.utc).isoformat()}
    with tempfile.TemporaryDirectory(prefix="nox-art-") as tmp:
        root=Path(tmp)
        shutil.copytree(web,root/"creative")
        shutil.copy2(home,root/"home.png")
        if digest(root/"home.png")!=HOME_SHA:
            raise RuntimeError("HOME_COPY_SHA_HOLD")
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*a):pass
        httpd=http.server.ThreadingHTTPServer(("127.0.0.1",0),
            functools.partial(Handler,directory=str(root)))
        thread=threading.Thread(target=httpd.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                opts={"headless":True}
                if browser_path:opts["executable_path"]=browser_path
                browser=pw.chromium.launch(**opts)
                try:
                    for w,h in VIEWPORTS:
                        page=browser.new_page(viewport={"width":w,"height":h},
                            device_scale_factor=1,reduced_motion="reduce")
                        try:
                            runtime_errors=[]
                            page.on("pageerror",lambda err: runtime_errors.append(str(err)[:280]))
                            page.goto(f"http://127.0.0.1:{httpd.server_port}/creative/studio.html",
                                      wait_until="domcontentloaded",timeout=25000)
                            page.locator('nav.nav [data-nav="five"]').wait_for(state="visible",timeout=12000)
                            page.locator('nav.nav [data-nav="five"]').click(timeout=15000)
                            for block in BLOCKS:
                                page.locator(f'#cs5-segments [data-cs5-segment="{block}"]').click()
                                values=page.evaluate("""() => ({
                                    active:document.querySelector('#cs5-cinema')?.dataset.cs5Scene,
                                    overflow:document.documentElement.scrollWidth > innerWidth+1,
                                    buttons:document.querySelectorAll('#cs5-segments button').length,
                                    touch:Math.min(...Array.from(
                                      document.querySelectorAll('#cs5-segments button'))
                                      .map(el=>el.getBoundingClientRect().height)),
                                    reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
                                    titleVisible:(()=>{
                                      const el=document.querySelector('#cs5-cinema-title');
                                      if(!el)return false;
                                      const r=el.getBoundingClientRect();
                                      const style=getComputedStyle(el);
                                      return r.width>60 && r.height>20 && style.visibility==='visible' &&
                                        style.display!=='none' && parseFloat(style.opacity)>0 &&
                                        !!el.textContent.trim();
                                    })(),
                                    heroSource:(()=>{
                                      const el=document.querySelector('.hero');
                                      return el ? getComputedStyle(el).backgroundImage.includes('home.png') : false;
                                    })()
                                })""")
                                filename=f"CS5_{block}_{w}x{h}.jpg"
                                page.screenshot(path=str(out/filename),type="jpeg",quality=84,
                                                full_page=False)
                                valid=(values["active"]==block and
                                       not values["overflow"] and values["buttons"]==5 and
                                       values["touch"]>=44 and values["reduced"]
                                       and values["titleVisible"] and values["heroSource"]
                                       and not runtime_errors)
                                receipt["screens"].append({"block":block,"viewport":f"{w}x{h}",
                                    "screenshot":filename,"layout_pass":valid,
                                    "browser_errors":list(runtime_errors),"metrics":values})
                                if not valid:receipt["errors"].append(f"LAYOUT_{block}_{w}x{h}")
                        finally:page.close()
                finally:browser.close()
        finally:httpd.shutdown();httpd.server_close()
    if len(receipt["screens"])!=len(VIEWPORTS)*len(BLOCKS):
        receipt["errors"].append("CS5_30_FRAME_COUNT_HOLD")
    receipt["status"]=("BROWSER_PREFLIGHT_PASS_ART_REVIEW_HOLD" if not receipt["errors"]
                       else "BROWSER_PREFLIGHT_FAIL_ART_REVIEW_HOLD")
    (out/"CS5_ART_RECEIPT.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",
                                         encoding="utf-8")
    return receipt

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--approved-home",required=True)
    p.add_argument("--web",default=str(Path(__file__).resolve().parents[1]/"web"))
    p.add_argument("--out",default="CS5_ART_SCREENSHOTS")
    p.add_argument("--browser-path")
    a=p.parse_args()
    result=run(a.approved_home,a.web,a.out,a.browser_path)
    print(result["status"],"screens=",len(result["screens"]))
    raise SystemExit(0 if not result["errors"] else 1)
