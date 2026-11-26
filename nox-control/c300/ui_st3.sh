echo "C300: ui_st3 (studio FASTWOW = конструктор миров, zip удалены)"
S=/workspace/nox/web/site; F=/workspace/nox/web/v29src/FASTWOW/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
BK=/workspace/nox/web/st_bak_$TS; mkdir -p $BK; cp -p studio.html $BK/
[ -f studio-legacy.html ] || cp -p studio.html studio-legacy.html
python3 - <<'P'
S='/workspace/nox/web/site'; F='/workspace/nox/web/v29src/FASTWOW/site'
s=open(F+'/studio.html',encoding='utf-8').read()
hook='<script>if(/[?&]legacy=1/.test(location.search))location.replace("studio-legacy.html"+location.search)</script>'
s=s.replace('<head>','<head>'+hook,1) if '<head>' in s else hook+s
open(S+'/studio.html','w',encoding='utf-8').write(s)
P
rm -f /workspace/nox/web/v29src/*.zip; df -h /workspace | tail -1
cat > /tmp/stt.py <<'PEOF'
import io,base64,sys
from playwright.sync_api import sync_playwright
from PIL import Image
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for W,H in((1440,900),(390,844)):
        c=b.new_context(viewport={'width':W,'height':H},is_mobile=(W<500)); x=c.new_page(); errs=[];bad=[]
        x.on('pageerror',lambda e:errs.append(str(e)[:90])); x.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-50:]) if r.status>=400 and '127.0.0.1' in r.url and '/api/' not in r.url else None)
        x.goto('http://127.0.0.1:8091/web/studio.html',wait_until='domcontentloaded',timeout=60000); x.wait_for_timeout(5000)
        info=x.evaluate("()=>({sel:[...document.querySelectorAll('select')].filter(e=>e.offsetWidth).length,worldTiles:document.querySelectorAll('[data-nox-select-world]').length,palTiles:document.querySelectorAll('[data-nox-select-palette]').length,btnTiles:document.querySelectorAll('[data-nox-button],[data-button],[data-nox-select-button]').length,hs:document.documentElement.scrollWidth>innerWidth+1,len:document.body.innerText.length})")
        print('ST',W,errs[:3],bad[:5],info,flush=True)
        im=Image.open(io.BytesIO(x.screenshot(type='png'))).convert('RGB'); im.thumbnail((900,900)); buf=io.BytesIO(); im.save(buf,'JPEG',quality=55); s=base64.b64encode(buf.getvalue()).decode()
        for i in range(0,len(s),3000): print('B64 st%d %d %s'%(W,i//3000,s[i:i+3000]),flush=True)
        c.close()
    b.close()
PEOF
timeout 150 $PY /tmp/stt.py
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh 2>&1 | tail -2
echo "ROLLBACK_HINT cp -p $BK/studio.html $S/studio.html"
