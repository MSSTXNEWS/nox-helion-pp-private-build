echo S4RUN:s6_p18
cd /workspace/nox/web/site
python3 - <<'PY'
f='nox-s2-music.js'; t=open(f).read()
if 'S6CV' in t: print('already')
else:
    open(f+'.bak_s6_3','w').write(t)
    old="function cvStyle(u){return u?'background-image:url('+esc(u)+')':''}"
    assert old in t
    new="""function cvStyle(u){return u?'--cv:url('+esc(u)+')':''}
/*S6CV lazy covers*/
(function(){var st=document.createElement('style');st.textContent='[style*="--cv:"]:not(.vis){background-image:none!important}[style*="--cv:"].vis{background-image:var(--cv)}';document.head.appendChild(st);
var io='IntersectionObserver' in window?new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('vis');io.unobserve(e.target)}})},{rootMargin:'200px'}):null;
function scan(r){(r.querySelectorAll?r.querySelectorAll('[style*="--cv:"]:not(.vis)'):[]).forEach(function(n){if(n.__s6)return;n.__s6=1;io?io.observe(n):n.classList.add('vis')})}
new MutationObserver(function(m){m.forEach(function(x){x.addedNodes.forEach(function(n){if(n.nodeType===1){if(n.matches&&n.matches('[style*="--cv:"]')&&!n.__s6){n.__s6=1;io?io.observe(n):n.classList.add('vis')}scan(n)}});if(x.type==='attributes'&&x.target.matches('[style*="--cv:"]:not(.vis)')){x.target.__s6=0;scan(x.target.parentNode||document)}})}).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['style']});
scan(document)})();"""
    open(f,'w').write(t.replace(old,new)); print('patched')
PY
grep -c "S6CV" nox-s2-music.js
cat > /tmp/m.py <<'PY'
import time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch();
    for i in range(3):
        pg=b.new_page(viewport={'width':1440,'height':900});errs=[]
        pg.on('pageerror',lambda e:errs.append(str(e)))
        t=time.time();pg.goto('http://127.0.0.1:8091/web/music.html',wait_until='load');
        print('load',round(time.time()-t,2),'errs',errs[:2],'vis',pg.evaluate("document.querySelectorAll('[style*=\"--cv:\"].vis').length"),'all',pg.evaluate("document.querySelectorAll('[style*=\"--cv:\"]').length"))
    b.close()
PY
python3 /tmp/m.py 2>&1 | tail -8
