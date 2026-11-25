#!/bin/bash
mask(){ sed -E 's/((KEY|TOKEN|SECRET|PASS|PASSWORD|MASTER)[A-Z_]*[= ]+)[^ ;"'"'"']+/\1***/Ig'; }
echo "#### svc dir"; ls -la /workspace/nox/svc | head -30
for f in /workspace/nox/svc/start_all.sh /workspace/nox/svc/start_extra.sh; do echo "#### $f"; [ -f $f ] && mask < $f | cut -c1-260 | head -80; done
echo "#### meili"; ls /workspace/nox/svc/meili | head; ps -o args= -p $(pgrep -f "meilisearch --http-addr" | head -1) | mask | cut -c1-300
echo "#### glance"; ls /workspace/nox/svc | grep -i glance; which glance; ls /workspace/nox/web/build/src 2>/dev/null | head -20
echo "#### 4K metrics"
cat > /tmp/s3_4k.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':3840,'height':2160}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(3000)
    print(pg.evaluate("""(()=>{const q=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();const c=getComputedStyle(e);return [s,Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height),c.position,c.zoom,c.fontSize]};return [innerWidth,getComputedStyle(document.documentElement).zoom,q('.tb'),q('.tb-l'),q('header'),q('#nxdock'),q('.nxd-cells'),q('.page'),q('.wrap'),q('#nxnavx')]})()"""))
    b.close()
P
/workspace/nox/venv/bin/python -I /tmp/s3_4k.py 2>&1 | cut -c1-900
grep -n "zoom\|--tbh\|--dock" /workspace/nox/web/site/nox-wow.css | head -8 | cut -c1-200
