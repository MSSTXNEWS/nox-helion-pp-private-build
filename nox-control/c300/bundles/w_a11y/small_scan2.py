import sys,json
from playwright.sync_api import sync_playwright
JS="""()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&getComputedStyle(e).visibility!=='hidden'};
return [...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,sl-button,[role=button],[role=tab]')].filter(e=>vis(e)&&!e.closest('.fc,.leaflet-control-attribution,.leaflet-marker-icon,[aria-hidden=true]')).filter(e=>{const r=e.getBoundingClientRect();return r.height<43.5||r.width<43.5}).map(e=>{const r=e.getBoundingClientRect();return e.tagName+'#'+e.id+'.'+String(e.className).slice(0,40)+' '+Math.round(r.width)+'x'+Math.round(r.height)})}"""
n=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h,m,q in [(1440,900,0,''),(390,844,1,'?home=1')]:
        c=b.new_context(viewport={'width':w,'height':h},is_mobile=bool(m),has_touch=bool(m));pg=c.new_page()
        pg.goto('http://127.0.0.1:8091/web/%s.html%s'%(n,q),wait_until='load',timeout=60000);pg.wait_for_timeout(4000)
        print(n,w,json.dumps(pg.evaluate(JS),ensure_ascii=False)[:1500],flush=True);c.close()
