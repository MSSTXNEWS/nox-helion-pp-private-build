#!/usr/bin/env python3
"""Offline NOX WEB29 Chromium geometry regression; NEVER a native OneHost test.

Usage: python test_short_landscape_threecol_v06.py --archive ORIGINAL_WEB29.zip
       --css path/to/nox-cinematic-accessibility-3d.css
Requires Playwright and locally installed Chromium. The archive supplies the
unchanged original WEB29 HTML and vendor styles. No HTTP login, SSE or S03.
"""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

LOCKED = {
 "site/nox-engines/nox-world-shaders.mjs":"124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952",
 "site/nox-orbit-14.js":"3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38",
 "site/pc/nox-engines/nox-world-shaders.mjs":"124a5d341059eb1070adcf58640657aa471ea4888e4409101503ecaa9337f952",
 "site/pc/nox-orbit-14.js":"3aced1774354b6212b665ef40514e78fb7660a3319fd346c4b12bbf277a39d38",
}
CASES=[(w,h) for w in (761,800,960,1024,1199) for h in (360,400,419,420,480,540)]
GUARDS=[(390,900),(760,900),(320,480),(390,667),(1200,400),(1400,480),(1920,900)]
JS="""() => {const b=s=>{const r=document.querySelector(s)?.getBoundingClientRect();
return r?{h:r.height,bottom:r.bottom}:null};
return {docW:document.documentElement.scrollWidth,msg:b('#messages'),
composer:b('#prompt'),history:b('.chat-history-panel'),tele:b('.chat-telemetry-panel')};}"""

def run(archive,css):
 with zipfile.ZipFile(archive) as z:
  if z.testzip() is not None:raise AssertionError('ZIP_CRC')
  for name,digest in LOCKED.items():
   assert hashlib.sha256(z.read(name)).hexdigest()==digest, 'D02_ORBIT_SOURCE_LOCK '+name
  html=z.read('site/chat.html').decode('utf-8')
  def inline(m):
   rel=m.group(1).removeprefix('./')
   data=css.read_text() if rel=='nox-cinematic-accessibility-3d.css' else z.read('site/'+rel).decode()
   return '<style>'+data+'</style>'
  html=re.sub(r'<link(?=[^>]*rel="stylesheet")[^>]*href="([^"]+)"[^>]*>',inline,html)
 exe=shutil.which('chromium') or shutil.which('chromium-browser')
 if not exe:raise RuntimeError('HOLD_NO_CHROMIUM')
 metrics=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=exe,headless=True,args=['--no-sandbox','--disable-gpu'])
  page=browser.new_page(java_script_enabled=False,reduced_motion='reduce')
  page.set_content(html,wait_until='domcontentloaded')
  for w,h in CASES+GUARDS:
   page.set_viewport_size({'width':w,'height':h})
   data=page.evaluate(JS)
   page.focus('#prompt')
   assert page.evaluate("document.activeElement?.id")=='prompt', ('KEYBOARD',w,h)
   assert data['docW']<=w+1,('OVERFLOW_X',w,h)
   if (w,h) in CASES:
    assert data['msg']['h']>=54,('TOKEN_PANE',w,h,data)
    assert data['composer']['bottom']<=h+1,('COMPOSER_HIDDEN',w,h,data)
    assert data['history']['h']>0 and data['tele']['h']>0,('PANEL_LOSS',w,h)
   metrics.append([w,h,round(data['msg']['h'],1),round(data['composer']['bottom'],1)])
  browser.close()
 return {'status':'SOURCE_OFFLINE_CHROMIUM_PASS','cases':len(metrics),
         'compact_cases':len(CASES),'protected_sha256_locks':len(LOCKED),
         'native_sse_stop_s03':'NOT_TESTED','measurements':metrics}

if __name__=='__main__':
 ap=argparse.ArgumentParser()
 ap.add_argument('--archive',required=True,type=Path)
 ap.add_argument('--css',required=True,type=Path)
 a=ap.parse_args()
 print(json.dumps(run(a.archive,a.css),ensure_ascii=False))
