#!/bin/bash
# b_swiper.sh: (1) test10: печатать все SSML-предложения (бэкап); (2) Swiper в рядах cinema/music через vendor/swiper (откат на CSS-ряды без Swiper); проверка Playwright
set -u
W=/workspace/nox; S=$W/web/site; TS=$(date -u +%Y%m%d_%H%M%S); OUT=$S/qa/empty; mkdir -p $OUT
cp $W/c300_voice/voice2/test10.py $W/c300_voice/voice2/test10.py.bak_b_$TS
python3 - "$W/c300_voice/voice2/test10.py" <<'PY'
import sys
f=sys.argv[1]; s=open(f,encoding='utf-8').read()
old='a["ssml"][0][:300] if a["ssml"] else ""'
if old in s: s=s.replace(old,'" | ".join(a["ssml"])[:600] if a["ssml"] else ""'); open(f,'w',encoding='utf-8').write(s); print("test10 patched")
else: print("test10 pattern not found")
PY
python3 -m py_compile $W/c300_voice/voice2/test10.py && echo "test10 compile ok"
cp $S/nox-empty-x.js $S/nox-empty-x.js.bak_b_$TS; cp $S/nox-empty-x.css $S/nox-empty-x.css.bak_b_$TS
python3 - "$S/nox-empty-x.js" <<'PY'
import sys
f=sys.argv[1]; s=open(f,encoding='utf-8').read()
old="    hero.insertAdjacentElement('afterend', sec);\n  });"
new="    hero.insertAdjacentElement('afterend', sec);\n    initSwiper(sec);\n  });"
assert s.count(old)==1, "anchor"
s=s.replace(old,new)
fn="""  function initSwiper(sec){
    if (!window.Swiper) return;
    var sc = sec.querySelector('.nox-scroll'); sc.classList.add('swiper');
    var wr = document.createElement('div'); wr.className = 'swiper-wrapper';
    Array.prototype.slice.call(sc.children).forEach(function(c){ var sl = document.createElement('div'); sl.className = 'swiper-slide'; sl.appendChild(c); wr.appendChild(sl); });
    sc.appendChild(wr);
    new window.Swiper(sc, {slidesPerView: 'auto', spaceBetween: 12, freeMode: true, grabCursor: true});
  }
  function act(sel){"""
assert s.count("  function act(sel){")==1
s=s.replace("  function act(sel){",fn,1)
open(f,'w',encoding='utf-8').write(s); print("js patched")
PY
cat >> $S/nox-empty-x.css <<'CSS'
.nox-scroll.swiper{overflow:visible}
.nox-scroll.swiper .swiper-slide{width:min(260px,72vw);height:auto}
.nox-scroll.swiper .nox-card{flex:none;width:100%;height:100%}
CSS
for f in cinema music news; do
  python3 - "$S/$f.html" <<'PY'
import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
if 'swiper-bundle.umd.min.js' not in s:
    s=s.replace('<script src="./nox-empty-x.js?v=1" defer></script>','<script src="./vendor/swiper/swiper-bundle.umd.min.js" defer></script>\n<script src="./nox-empty-x.js?v=2" defer></script>',1)
    open(p,'w',encoding='utf-8').write(s); print("tagged",p)
PY
done
cd $S && (python3 -m http.server 8780 --bind 127.0.0.1 >/tmp/b_http7.log 2>&1 &); sleep 2
PY=$W/invoke/bin/python; export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 400 $PY - "$OUT" <<'PY' 2>&1 | tail -20
import sys
from playwright.sync_api import sync_playwright
out=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch(args=["--no-sandbox"])
    for name in ["cinema","music","news"]:
        for tag,w,h,mob in (("pc",1440,900,False),("mob",390,844,True)):
            ctx=b.new_context(viewport={"width":w,"height":h},is_mobile=mob); pg=ctx.new_page(); errs=[]
            pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
            pg.goto("http://127.0.0.1:8780/%s.html"%name, wait_until="load", timeout=40000); pg.wait_for_timeout(1500)
            info=pg.evaluate("({swiper: document.querySelectorAll('.swiper-initialized').length, cards: document.querySelectorAll('.nox-card').length})")
            pg.screenshot(path=f"{out}/{name}_swiper_{tag}.png")
            print(name,tag,info,"err=",len(errs),errs[:1],"overflowX=",pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            ctx.close()
    b.close()
PY
pkill -f "http.server 8780" 2>/dev/null; true
