import sys,json,time
from playwright.sync_api import sync_playwright
n=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h,m,q in [(1440,900,0,''),(390,844,1,'?home=1'),(390,844,1,'')]:
        c=b.new_context(viewport={'width':w,'height':h},is_mobile=bool(m),has_touch=bool(m));pg=c.new_page();errs=[];bad=[];cons=[]
        pg.on('pageerror',lambda e:errs.append((str(e)[:120],(e.stack or '')[:300].replace('\n',' ; '))))
        pg.on('requestfailed',lambda r:bad.append('FAIL '+r.url[-70:]))
        pg.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-70:]) if r.status>=400 else None)
        pg.on('console',lambda m_:cons.append(m_.text[:140]) if m_.type=='error' else None)
        t=time.time()
        try: pg.goto('http://127.0.0.1:8091/web/%s.html%s'%(n,q),wait_until='load',timeout=60000);st='load %.1fs'%(time.time()-t)
        except Exception as e: st='GOTO '+str(e)[:100]
        pg.wait_for_timeout(4000)
        print(n,w,q,st,'ERR',json.dumps(errs,ensure_ascii=False)[:900],'BAD',bad[:8],'CON',cons[:4],flush=True)
        c.close()
