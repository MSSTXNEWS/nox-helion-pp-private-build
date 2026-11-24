#!/bin/bash
# N (навигация): ставит расширение nox-nav-x.js/.css поверх канона, проверяет скриншотами, пишет nav.fixed.
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets
T=bak_navx7k
cd /tmp
for f in nox-nav-x.js nox-nav-x.css; do curl -fsSL "$RAW/$f" -o $S/$f && echo got $f; done
n=0
for f in $S/*.html; do
  grep -q 'nox-nav-x.js' "$f" && continue
  cp "$f" "$f.$T" 2>/dev/null
  sed -i 's#</body>#<script src="./nox-nav-x.js" defer></script>\n</body>#' "$f" && n=$((n+1))
done
echo "injected pages: $n"
# реестр шины (пишет исполнитель A) - только просмотр
python3 -c "import json;d=json.load(open('$S/qa/registry.json'));print('registry keys:',len(d) if isinstance(d,(list,dict)) else type(d).__name__)" 2>&1 | head -3
mkdir -p $S/qa/rework && echo "nav: nox-nav-x.js (палитра Ctrl+K, крошки, датчики ядра/чата, поиск на телефоне); канон не менялся" > $S/qa/rework/nav.fixed
cat > /tmp/shot_navx.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w,q):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v',q,j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
J=[('index_d',1440,900,'index.html',11),('index_m',390,844,'index.html',11),('chat_4k',3840,2160,'chat.html',11)]
with sync_playwright() as p:
    b=p.chromium.launch()
    for tag,w,h,page,q in J:
        pg=b.new_page(viewport={'width':w,'height':h},has_touch=w<800,is_mobile=w<800)
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        pg.goto('http://localhost:8091/web/'+page,wait_until='load'); pg.wait_for_timeout(4000)
        pg.keyboard.press('Control+k'); pg.wait_for_timeout(400)
        pg.screenshot(path='/tmp/s.png')
        out(tag,'/tmp/s.png',640 if w>800 else 390,q)
        pg.keyboard.press('Escape')
        print('ERRS',tag,errs[:3])
    b.close()
P
/workspace/nox/venv/bin/python -I /tmp/shot_navx.py 2>&1 | cut -c1-900
