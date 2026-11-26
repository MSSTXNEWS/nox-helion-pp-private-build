import sys,json
from playwright.sync_api import sync_playwright
B='http://127.0.0.1:8094/web/'
pages=sys.argv[2:] or ['index','chat','settings','system','memory','writer','studio','tv','live','photo']
q=sys.argv[1] if len(sys.argv)>1 else ''
q='' if q=='-' else q
out={}
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for n in pages:
        ctx=b.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        pg=ctx.new_page();cd=ctx.new_cdp_session(pg);cd.send('Emulation.setCPUThrottlingRate',{'rate':4})
        tot={'b':0,'js':0,'n':0,'jsn':0}
        def on(r):
            try:
                l=int(r.headers.get('content-length') or 0)
            except: l=0
            tot['b']+=l;tot['n']+=1
            if r.url.split('?')[0].endswith('.js') or r.url.split('?')[0].endswith('.mjs'): tot['js']+=l;tot['jsn']+=1
        pg.on('response',on)
        pg.add_init_script("window.__lt=0;new PerformanceObserver(l=>{for(const e of l.getEntries())window.__lt+=Math.max(0,e.duration-50)}).observe({type:'longtask',buffered:true})")
        try: pg.goto(B+n+'.html'+q,wait_until='load',timeout=60000)
        except Exception as e: out[n]='ERR';continue
        pg.wait_for_timeout(3000)
        m=pg.evaluate("({fcp:(performance.getEntriesByName('first-contentful-paint')[0]||{}).startTime,tbt:window.__lt,load:performance.timing.loadEventEnd-performance.timing.navigationStart})")
        out[n]={'fcp':round(m['fcp'] or 0),'tbt':round(m['tbt']),'load':m['load'],'KB':round(tot['b']/1024),'jsKB':round(tot['js']/1024),'req':tot['n'],'js':tot['jsn']}
        ctx.close()
    b.close()
for k,v in out.items(): print(k,v)
