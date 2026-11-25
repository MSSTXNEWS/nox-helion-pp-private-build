echo "C300: k6_probe_4"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 200 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{const o={};for(const [g,f] of [['NOX_blocknote','blocknote/blocknote.iife.js'],['NOX_codemirror','codemirror/codemirror.iife.js'],['NOX_orama_orama','orama-orama/orama-orama.iife.js']]){await new Promise(r=>{const s=document.createElement('script');s.src='./vendor/'+f;s.onload=r;s.onerror=r;document.head.appendChild(s)});const m=window[g];o[g]=m?Object.keys(m).filter(k=>/^(BlockNote|create|Code|fromText|search|insert|default|mount)/i.test(k)).slice(0,14).concat(['n='+Object.keys(m).length]):'NONE'}
try{const B=window.NOX_blocknote.BlockNoteEditor;const e=B.create();const d=document.createElement('div');document.body.appendChild(d);e.mount(d);o.bn='mounted '+(d.innerHTML.length)}catch(x){o.bn='ERR '+String(x).slice(0,120)}
try{const cm=window.NOX_codemirror;const C=cm.default||cm.CodeMirror||cm;o.cm=typeof C+' '+(C.fromTextArea?'v5':'?')}catch(x){o.cm='ERR'}
return JSON.stringify(o)})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[]);pg=await b.new_page();errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
    await pg.goto('http://127.0.0.1:8091/web/studio.html',wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(2000)
    try: print('QA',await asyncio.wait_for(pg.evaluate(JS),60))
    except Exception as e: print('QA EXC',str(e)[:300])
    print('errs',errs[:3]);await b.close()
asyncio.run(m())
QAEOF
echo "K6 probe4 done"
