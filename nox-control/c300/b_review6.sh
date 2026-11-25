#!/bin/bash
# b_review6.sh: (а) T7: число SSML-предложений в JSON-ответе и строка print в test10; (б) файлы vendor/swiper; (в) Playwright 3840x2160 и 390x844: ошибки JS, переполнение, низкое разрешение картинок
set -u
W=/workspace/nox; S=$W/web/site; OUT=$S/qa/final; mkdir -p $OUT
echo "== a) T7 json"
curl -s --max-time 120 -X POST http://127.0.0.1:8095/synth -H 'Content-Type: application/json' -d '{"text":"В XX веке музыка изменилась. Что дальше? Не знаю!","voice":"aidar","format":"json"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('keys',list(d)[:12]); print('ssml_count',len(d.get('ssml',[]))); [print(' ',x[:160]) for x in d.get('ssml',[])]" 2>&1 | head -20
echo "== a2) test10 print line"; grep -n "SSML\|ssml" $W/c300_voice/voice2/test10.py | head -5
echo "== b) vendor/swiper"; ls $S/vendor/swiper | head -20
echo "== c) playwright"
cd $S && (python3 -m http.server 8779 --bind 127.0.0.1 >/tmp/b_http6.log 2>&1 &); sleep 2
PY=$W/invoke/bin/python; export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 900 $PY - "$OUT" <<'PY' 2>&1 | tail -60
import sys
from playwright.sync_api import sync_playwright
out=sys.argv[1]
pages=["chat","consciousness","organism","training","voice","music","cinema","news","studio","photo"]
JS_LOWRES="""()=>{const r=[];document.querySelectorAll('img').forEach(i=>{const w=i.getBoundingClientRect().width*devicePixelRatio; if(i.naturalWidth && w>0 && i.naturalWidth<w*0.9) r.push((i.getAttribute('src')||'').slice(0,60)+' '+i.naturalWidth+'<'+Math.round(w));});return r.slice(0,4);}"""
with sync_playwright() as p:
    b=p.chromium.launch(args=["--no-sandbox"])
    for n in pages:
        for tag,w,h,mob,dpr in (("4k",3840,2160,False,1),("mob",390,844,True,3)):
            ctx=b.new_context(viewport={"width":w,"height":h},is_mobile=mob,device_scale_factor=dpr); pg=ctx.new_page(); errs=[]
            pg.on("pageerror", lambda e: errs.append(str(e)[:100]))
            try:
                pg.goto("http://127.0.0.1:8779/%s.html"%n, wait_until="load", timeout=40000); pg.wait_for_timeout(1000)
                pg.screenshot(path=f"{out}/{n}_{tag}.png")
                print(n,tag,"err=",len(errs),errs[:1],"overflowX=",pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"),"lowres=",pg.evaluate(JS_LOWRES))
            except Exception as e: print(n,tag,"FAIL",str(e)[:100])
            ctx.close()
    b.close()
PY
pkill -f "http.server 8779" 2>/dev/null; true
