#!/usr/bin/env python3
"""UI score: Lighthouse (a11y/best-practices/perf) + axe-core + собственные метрики -> U и A (0-10). Формула: UX_SCORES.md.
Запуск: score.py own|lh|all PAGE... ; результаты в /workspace/nox/agent/out/ui_sc/<page>_<vp>.json"""
import sys,os,json,glob,subprocess,time,concurrent.futures as cf
OUT='/workspace/nox/agent/out/ui_sc'; os.makedirs(OUT,exist_ok=True)
TOOLS='/workspace/nox/tools/uiscore'; AXE=TOOLS+'/node_modules/axe-core/axe.min.js'; LH=TOOLS+'/node_modules/.bin/lighthouse'
BASE='http://127.0.0.1:8091/web/'
VPS={'1440':(1440,900,False),'390':(390,844,True)}
def url(pg,vp): return BASE+pg+('.html?home=1' if pg=='index' and vp=='390' else '.html')
JS="""()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&getComputedStyle(e).visibility!=='hidden'};
const el=[...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,sl-button,[role=button],[role=tab]')].filter(e=>vis(e)&&!e.closest('.fc,.leaflet-control-attribution,.leaflet-marker-icon,[aria-hidden=true]'));
const small=el.filter(e=>{const r=e.getBoundingClientRect();return r.height<43.5||r.width<43.5}).length;
const cta=[...document.querySelectorAll('.u-cta,sl-button[variant=primary],button.pri,.k4-btn.pri')].filter(vis).length;
return {small:small,interactive:el.length,hs:document.documentElement.scrollWidth>innerWidth+1,cta:cta>0,theme:document.documentElement.getAttribute('data-nox-theme')==='graphite',
 empty:document.querySelectorAll('.ds-empty').length,skel:document.querySelectorAll('sl-skeleton').length}}"""
def own(pgs):
    from playwright.sync_api import sync_playwright
    res={}
    with sync_playwright() as p:
        b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
        for pg in pgs:
            for vp,(w,h,mob) in VPS.items():
                c=b.new_context(viewport={'width':w,'height':h},is_mobile=mob,has_touch=mob); x=c.new_page(); errs=[]; bad=[]
                x.on('pageerror',lambda e:errs.append(str(e)[:80])); x.on('requestfailed',lambda r:bad.append(r.url[-60:]))
                x.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-50:]) if r.status>=400 and '127.0.0.1' in r.url else None)
                d={'page':pg,'vp':vp}
                try:
                    x.goto(url(pg,vp),wait_until='domcontentloaded',timeout=25000)
                    for _ in range(12):
                        if x.evaluate("document.documentElement.getAttribute('data-nox-theme')"): break
                        x.wait_for_timeout(500)
                    x.wait_for_timeout(2500)
                    d.update(x.evaluate(JS)); d['jserr']=len(set(errs)); d['err404']=len([u for u in bad if u[:3].isdigit()])
                    x.add_script_tag(path=AXE); ax=x.evaluate("async()=>{const r=await axe.run(document,{resultTypes:['violations']});return r.violations.map(v=>({id:v.id,imp:v.impact,n:v.nodes.length}))}")
                    d['axe']=ax
                except Exception as e: d['error']=str(e)[:120]
                json.dump(d,open(f'{OUT}/{pg}_{vp}_own.json','w'),ensure_ascii=False); c.close()
        b.close()
def lh_one(job):
    pg,vp=job; w,h,mob=VPS[vp]
    cp=glob.glob('/workspace/nox/tools/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell')
    out=f'{OUT}/{pg}_{vp}_lh.json'
    cmd=[LH,url(pg,vp),'--only-categories=accessibility,best-practices,performance','--output=json','--output-path='+out,'--quiet','--chrome-flags=--headless --no-sandbox --disable-gpu','--form-factor='+('mobile' if mob else 'desktop')]
    if not mob: cmd+=['--screenEmulation.mobile=false','--screenEmulation.width=1440','--screenEmulation.height=900','--screenEmulation.deviceScaleFactor=1']
    if cp: cmd+=['--chrome-path='+cp[0]]
    try: r=subprocess.run(cmd,capture_output=True,text=True,timeout=150,env={**os.environ,'CHROME_PATH':(cp[0] if cp else ''),'PATH':'/workspace/nox/tools/node/bin:'+os.environ['PATH']})
    except Exception as e: return (pg,vp,'TIMEOUT '+str(e)[:50])
    return (pg,vp,'ok' if os.path.exists(out) else 'FAIL '+(r.stderr or r.stdout)[-150:])
def lh(pgs,par=6):
    jobs=[(pg,vp) for pg in pgs for vp in VPS]
    with cf.ThreadPoolExecutor(par) as ex:
        for r in ex.map(lh_one,jobs): print('LH',*r,flush=True)
if __name__=='__main__':
    mode=sys.argv[1]; pgs=sys.argv[2:]
    t=time.time()
    if mode in('own','all'): own(pgs); print('OWN done',round(time.time()-t),flush=True)
    if mode in('lh','all'): lh(pgs); print('LH done',round(time.time()-t),flush=True)
