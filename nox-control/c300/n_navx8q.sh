#!/bin/bash
# N (навигация), этап 2: палитра ninja-keys не открывается при загрузке, пульт, вкладки настроек, проверка скриншотами.
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets
T=bak_navx8q
cd /tmp
for f in nox-ninja.js nox-pult.js nox-pult.css nox-settings-tabs.js nox-nav-x.js nox-nav-x.css; do curl -fsSL "$RAW/$f" -o /tmp/navx8q_$f && echo got $f; done
# ninja-keys: бэкап и замена на версию с тихим стартом
[ -f $S/nox-ninja.js.$T ] || cp $S/nox-ninja.js $S/nox-ninja.js.$T
cp /tmp/navx8q_nox-ninja.js $S/nox-ninja.js && echo ninja replaced
cp /tmp/navx8q_nox-pult.js $S/nox-pult.js; cp /tmp/navx8q_nox-pult.css $S/nox-pult.css
cp /tmp/navx8q_nox-settings-tabs.js $S/nox-settings-tabs.js; cp /tmp/navx8q_nox-nav-x.js $S/nox-nav-x.js; cp /tmp/navx8q_nox-nav-x.css $S/nox-nav-x.css
# инъекция пульта на все страницы, вкладок — на settings.html
np=0
for f in $S/*.html; do
  grep -q 'nox-pult.js' "$f" || { cp "$f" "$f.$T" 2>/dev/null; sed -i 's#</body>#<script src="./nox-pult.js" defer></script>\n</body>#' "$f" && np=$((np+1)); }
done
grep -q 'nox-settings-tabs.js' $S/settings.html || sed -i 's#</body>#<script src="./nox-settings-tabs.js" defer></script>\n</body>#' $S/settings.html
echo "pult injected: $np"
mkdir -p $S/qa/rework && echo "nav: nox-nav-x.js (крошка, датчики), nox-pult.js (пульт: STOP, глубина, голос, датчики), вкладки настроек, ninja-keys без самооткрытия; канон не менялся" > $S/qa/rework/nav.fixed
cat > /tmp/shot_navx8q.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run([str(x) for x in ['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j]])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
ST="()=>{const e=document.querySelector('ninja-keys');return {ninja: !!e, open: e?e.hasAttribute('open'):null, isOpen: e?e.isOpen:null, crumb: (document.getElementById('nxx-crumb')||{}).textContent||'', pult: !!document.getElementById('nxpult'), tabs: document.querySelectorAll('.nxt-tabs [role=tab]').length}}"
J=[('index_d',1440,900,'index.html',0),('index_m',390,844,'index.html',1),('chat_d',1440,900,'chat.html',0),('chat_m',390,844,'chat.html',1),('set_d',1440,900,'settings.html',0)]
with sync_playwright() as p:
    b=p.chromium.launch()
    for tag,w,h,page,mob in J:
        pg=b.new_page(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob))
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        pg.goto('http://localhost:8091/web/'+page,wait_until='load'); pg.wait_for_timeout(4000)
        print('STATE',tag,pg.evaluate(ST))
        if tag=='set_d':
            pg.click('.nxt-tabs [data-tab="models"]'); pg.wait_for_timeout(400)
        pg.screenshot(path='/tmp/s.png')
        out(tag,'/tmp/s.png',640 if w>800 else 390)
        print('ERRS',tag,errs[:3])
    b.close()
P
/workspace/nox/venv/bin/python -I /tmp/shot_navx8q.py 2>&1 | cut -c1-900
