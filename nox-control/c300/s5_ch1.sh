cat > /tmp/s5_chain.sh <<'C'
for p in news settings atlas photo chat index; do
  flock /tmp/qaa.lock nice -n 5 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/s5_chain.log 2>&1
done
echo CHAIN_DONE >> /tmp/s5_chain.log
C
: > /tmp/s5_chain.log
setsid nohup bash /tmp/s5_chain.sh >/dev/null 2>&1 < /dev/null &
cat > /tmp/s5_hdr.py <<'P'
import json,time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); 
    for name in ("music","news","studio","creative","cinema"):
        for w in (1440,1280,1920,390):
            ctx=b.new_context(viewport={'width':w,'height':900},service_workers='block'); pg=ctx.new_page()
            url='http://localhost:8091/web/%s.html?v=%d'%(name,int(time.time()))
            pg.goto(url,wait_until='load'); pg.wait_for_timeout(3500)
            r=pg.evaluate("""()=>{const els=[...document.querySelectorAll('header *, .topbar *, [class*=tb] *, nav *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<80});let mn=1e9,mx=-1e9;els.forEach(e=>{const r=e.getBoundingClientRect();mn=Math.min(mn,r.left);mx=Math.max(mx,r.right)});return {minLeft:Math.round(mn),maxRight:Math.round(mx),sw:document.documentElement.scrollWidth,iw:innerWidth,sx:scrollX}}""")
            print("OUT: HDR",name,w,json.dumps(r),url[:60]); ctx.close()
    b.close()
P
/workspace/nox/venv/bin/python /tmp/s5_hdr.py 2>&1 | tail -22 | cut -c1-200
