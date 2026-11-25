S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
cp $S/nox-ds.js $S/nox-ds.js.bak_s3_27
grep -q "S3 vt-reject" $S/nox-ds.js || cat >> $S/nox-ds.js <<'C'

/* S3 vt-reject: пропущенный межстраничный переход (навигация прервана) не считается ошибкой страницы */
addEventListener('unhandledrejection', (e) => { const m = String((e.reason && e.reason.message) || e.reason || ''); if (/Transition was skipped|Navigation aborted/i.test(m)) e.preventDefault(); });
addEventListener('error', (e) => { if (/Transition was skipped|Navigation aborted/i.test(String(e.message || ''))) e.preventDefault(); });
C
sed -i 's#nox-ds\.js?v=s3d#nox-ds.js?v=s3e#g' $S/*.html $S/nox-dock-pop.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_pu1.py <<'P'
from playwright.sync_api import sync_playwright
OBS="""()=>{window.__m=0;window.__mo&&window.__mo.disconnect();window.__mo=new MutationObserver(l=>{window.__m+=l.length});window.__mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true})}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('index','news'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block',permissions=[]); pg=ctx.new_page(); errs=[]; reqs=[]
        pg.on('pageerror',lambda e: errs.append(str(e)[:80])); pg.on('request',lambda r: reqs.append(r.method+' '+r.url.split('localhost:8091')[-1][:30]) if '/api/' in r.url else None)
        pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(3500)
        print('R:',pgn,'pageerrors after nav-test fix:',errs[:2])
        pg.click('.nxpu-tog'); pg.wait_for_timeout(700)
        n=pg.evaluate("()=>document.querySelectorAll('#nxpult button').length"); print('R:',pgn,'pult buttons',n)
        for i in range(n):
            info=pg.evaluate("(i)=>{const b=document.querySelectorAll('#nxpult button')[i];return [(b.textContent||b.getAttribute('aria-label')||'').trim().slice(0,22),b.disabled,getComputedStyle(b).display]}",i)
            if info[2]=='none': print('R:  hidden',info); continue
            pg.evaluate(OBS); reqs.clear(); e0=len(errs)
            try: pg.evaluate("(i)=>document.querySelectorAll('#nxpult button')[i].click()",i)
            except Exception as e: print('R:  click err',info,str(e)[:60]); continue
            pg.wait_for_timeout(900)
            m=pg.evaluate("()=>window.__m"); st=pg.evaluate("()=>[document.fullscreenElement?'fs':'',localStorage.length,document.documentElement.className.length]")
            dead = (m==0 and not reqs and len(errs)==e0)
            print('R: ',pgn,info[0].ljust(22),'dis' if info[1] else '   ','mut',m,'req',reqs[:2],'err',errs[e0:][:1],'DEAD' if dead else '')
            if pg.evaluate("()=>document.fullscreenElement")!=None: pg.keyboard.press('Escape')
            if not pg.evaluate("()=>!!document.querySelector('#nxpult .nxpu-stop')&&getComputedStyle(document.querySelector('#nxpult .nxpu-stop')).display!='none'"): pg.click('.nxpu-tog'); pg.wait_for_timeout(500)
        ctx.close()
    b.close()
P
timeout 270 $PY -I /tmp/s3_pu1.py 2>&1 | cut -c1-300
