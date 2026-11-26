echo "C300: ui_ix2 (эталон V29.3 как index.html, текущая -> index-legacy.html)"
S=/workspace/nox/web/site; Fz=/workspace/nox/web/v29src/V29_3_FROZEN/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
BK=/workspace/nox/web/ix_bak_$TS; mkdir -p $BK; cp -p index.html $BK/index.html
[ -f index-legacy.html ] || cp -p index.html index-legacy.html
# 1) недостающие файлы эталона (без перезаписи существующих)
n0=$(find $S -type f | wc -l)
for f in $(cd $Fz && ls | grep -E '\.(js|mjs|css|svg|json|webmanifest)$'); do [ -e $S/$f ] || cp -p $Fz/$f $S/$f; done
for d in vendor nox-engines assets fonts img; do [ -d $Fz/$d ] && cp -an $Fz/$d/. $S/$d/ 2>/dev/null || { [ -d $Fz/$d ] && mkdir -p $S/$d && cp -an $Fz/$d/. $S/$d/; }; done
echo "files added: $(( $(find $S -type f | wc -l) - n0 ))"
# 2) эталонная главная + редирект ?legacy=1
python3 - <<'P'
import re
S='/workspace/nox/web/site'; Fz='/workspace/nox/web/v29src/V29_3_FROZEN/site'
s=open(Fz+'/index.html',encoding='utf-8').read()
hook='<script>if(/[?&]legacy=1/.test(location.search))location.replace("index-legacy.html"+location.search)</script>'
s=s.replace('<head>','<head>'+hook,1) if '<head>' in s else hook+s
open(S+'/index.html','w',encoding='utf-8').write(s)
P
grep -c "legacy=1" index.html
# 3) проверка: ошибки, 404, текст, скрины
cat > /tmp/ui_ix2.py <<'PEOF'
import base64,sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w,h in((1440,900),(390,844)):
        c=b.new_context(viewport={'width':w,'height':h},is_mobile=(w<500)); x=c.new_page(); errs=[];bad=[]
        x.on('pageerror',lambda e:errs.append(str(e)[:100]))
        x.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-60:]) if r.status>=400 and '127.0.0.1' in r.url else None)
        x.goto('http://127.0.0.1:8091/web/index.html',wait_until='domcontentloaded'); x.wait_for_timeout(7000)
        t=x.evaluate("document.body.innerText.length")
        print('IX',w,'text',t,'errs',errs[:4],'404',bad[:8],flush=True)
        x.screenshot(path=f'/tmp/ix_{w}.jpg',type='jpeg',quality=45)
        print('B64 ix_%d'%w, base64.b64encode(open(f'/tmp/ix_{w}.jpg','rb').read()).decode(),flush=True)
        c.close()
    b.close()
PEOF
timeout 120 $PY /tmp/ui_ix2.py
echo "ROLLBACK_HINT cp -p $BK/index.html $S/index.html"
