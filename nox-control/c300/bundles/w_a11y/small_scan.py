import sys,json
from playwright.sync_api import sync_playwright
JS="""()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&getComputedStyle(e).visibility!=='hidden'};
return [...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,sl-button,[role=button],[role=tab]')].filter(e=>vis(e)&&!e.closest('.fc,.leaflet-control-attribution,.leaflet-marker-icon,[aria-hidden=true]')).filter(e=>{const r=e.getBoundingClientRect();return r.height<43.5||r.width<43.5}).map(e=>{const r=e.getBoundingClientRect();return e.tagName+'#'+e.id+'.'+String(e.className).slice(0,30)+' '+Math.round(r.width)+'x'+Math.round(r.height)+' in:'+(e.closest('[id]')||{}).id})}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for n,w,h in [('advisors',1440,900),('money',1440,900),('chat-dc',1440,900),('atlas',1440,900)]:
        pg=b.new_page(viewport={'width':w,'height':h});pg.goto('http://127.0.0.1:8091/web/%s.html'%n,wait_until='load');pg.wait_for_timeout(3500)
        print(n,json.dumps(pg.evaluate(JS),ensure_ascii=False)[:1100],flush=True);pg.close()
