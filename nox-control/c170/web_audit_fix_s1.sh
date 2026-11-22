#!/bin/bash
# c170: исправления по аудиту веба (N01-N25): фото-текстуры планет, режимы чата и подпись уровня, общая шапка, страницы Календарь/Кинозал/Виджеты/Диспетчер/Интеграции/Лицензии,
# стеклянные поля, лазерные надписи, ось времени, /api/pc-metrics (GPU/VRAM/ЦП/ОЗУ). Файлы с raw.githubusercontent.com (main). Ничего не удаляется: прежние версии -> *.bak-170.
W=${NOX_WEB:-/root/nox/web}; N=170; B=${NOX_B:-http://127.0.0.1:8091}
R=${NOX_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control}
S=$R/s1web/wow; cd $W || exit 1; FAIL=0; PUT=0
bak(){ [ -f "$1" ] && [ ! -f "$1.bak-$N" ] && cp -p "$1" "$1.bak-$N"; }
put(){ bak "$2"; if curl -fsSL "$S/$1" -o "$2.new" && [ -s "$2.new" ]; then mv "$2.new" "$2"; PUT=$((PUT+1)); else rm -f "$2.new"; echo "FAIL $1"; FAIL=$((FAIL+1)); fi; }
for f in index projects memory training models system settings calendar cinema widgets dispatcher integrations about; do put pages/$f.html $W/$f.html; done
for f in nox-pages.css nox-nav.js nox-shell.js nox-glass.js nox-registry.js nox-api.js nox-p-home.js nox-p-projects.js nox-p-memory.js nox-p-memory-extra.js nox-p-training.js nox-p-models.js nox-p-system.js nox-p-settings.js nox-p-calendar.js nox-p-cinema.js nox-p-widgets.js nox-p-dispatcher.js nox-p-integrations.js nox-p-about.js; do put pages/$f $W/$f; done
put chat.html $W/chat.html
for f in nox-wow.js nox-wow-data.js nox-v14-planet.js nox-notify.js nox-theme.js sw.js; do put $f $W/$f; done
for f in nox-wow.css nox-wow-bg.js; do for T in $(find $W -name $f -not -path '*/classic/*' -not -name '*.bak*'); do put $f $T; done; done
# текстуры планет (Solar System Scope, CC BY 4.0): nox-<тело>.jpg 2048x1024, ~1.8 МБ всего; manifest.json пересобирается по факту
mkdir -p $W/vendor/nox-planets; for f in nox-mercury nox-venus nox-earth nox-mars nox-jupiter nox-saturn nox-uranus nox-neptune; do
  if [ ! -s $W/vendor/nox-planets/$f.jpg ]; then curl -fsSL $S/planets/$f.jpg -o $W/vendor/nox-planets/$f.jpg.new && [ -s $W/vendor/nox-planets/$f.jpg.new ] && mv $W/vendor/nox-planets/$f.jpg.new $W/vendor/nox-planets/$f.jpg || { rm -f $W/vendor/nox-planets/$f.jpg.new; echo "FAIL planet $f"; FAIL=$((FAIL+1)); }; fi; done
for f in README.md ATTRIBUTION.txt; do [ -f $W/vendor/nox-planets/$f ] && [ ! -f $W/vendor/nox-planets/$f.bak-$N ] && cp -p $W/vendor/nox-planets/$f $W/vendor/nox-planets/$f.bak-$N; curl -fsSL $S/planets/$f -o $W/vendor/nox-planets/$f; done
python3 -I - $W/vendor/nox-planets <<'PY'
import os,sys,json
d=sys.argv[1]; json.dump({'files':sorted(f for f in os.listdir(d) if f.lower().endswith(('.jpg','.png'))),'source':'Solar System Scope, CC BY 4.0'},open(d+'/manifest.json','w'))
print('planets manifest:',len(json.load(open(d+'/manifest.json'))['files']),'файлов')
PY
# библиотеки ответов чата и Кинозала (marked, DOMPurify, KaTeX, Mermaid, Plyr)
curl -fsSL $R/c170/vendor_libs.sh -o /tmp/vl170.sh && NOX_VENDOR=$W/vendor bash /tmp/vl170.sh 2>&1 | tail -3
# веб-сервер: /api/pc-metrics, /api/health, nox_mode и подпись уровня в старом протоколе
[ -f /root/nox/web_server.py ] && [ ! -f /root/nox/web_server.py.bak-$N ] && cp -p /root/nox/web_server.py /root/nox/web_server.py.bak-$N
curl -fsSL $R/s1web/web_server.py -o /root/nox/web_server.py.new && [ -s /root/nox/web_server.py.new ] && python3 -c "import ast;ast.parse(open('/root/nox/web_server.py.new').read())" && mv /root/nox/web_server.py.new /root/nox/web_server.py || { echo "FAIL web_server.py"; FAIL=$((FAIL+1)); }
pkill -f "/root/nox/web_server.py"; sleep 1
nohup setsid python3 /root/nox/web_server.py > /root/nox/logs/web_server.log 2>&1 < /dev/null &
sleep 3
echo "put=$PUT fail=$FAIL"
echo "pc-metrics: $(curl -s -m8 $B/api/pc-metrics | head -c 700)"
# проверка: страницы и ресурсы
python3 -I - $B $W <<'PY'
import re,sys,urllib.request,urllib.error
B,W=sys.argv[1],sys.argv[2]
pages='index chat projects memory training models system settings calendar cinema widgets dispatcher integrations about'.split()
res=set()
for p in pages:
    s=open('%s/%s.html'%(W,p),encoding='utf-8').read()
    for m in re.findall(r'(?:src|href)="(\./[^"]+)"',s): res.add(m[2:])
res|={'nox-wow.css','nox-pages.css','nox-nav.js','nox-shell.js','nox-glass.js','nox-registry.js','nox-api.js','nox-notify.js','nox-theme.js','sw.js','nox-wow-bg.js','nox-wow-data.js','nox-wow-shaders.js','nox-v14-planet.js','favicon.svg','wow/lottie-ok.json','wow/lottie-orbit.json',
 'vendor/shoelace/cdn/shoelace-autoloader.js','vendor/swiper/swiper-bundle.min.mjs','vendor/motion/dist/motion.js','vendor/tsparticles/tsparticles.bundle.min.js','vendor/postprocessing/build/index.js','vendor/three/build/three.module.js','vendor/nox-stars/stars.json','vendor/nox-planets/manifest.json','vendor/nox-planets/2k_moon.jpg',
 'vendor/nox-lib/marked/marked.min.js','vendor/nox-lib/dompurify/purify.min.js','vendor/nox-lib/katex/katex.min.js','vendor/nox-lib/katex/katex.min.css','vendor/nox-lib/mermaid/mermaid.min.js','vendor/nox-lib/plyr/plyr.min.js','vendor/nox-lib/plyr/plyr.css','vendor/nox-lib/plyr/plyr.svg',
 'vendor/nox-extra/leaflet.js','vendor/nox-extra/leaflet.css','vendor/nox-extra/images/marker-icon.png','vendor/nox-extra/fullcalendar.global.min.js','vendor/nox-extra/echarts.min.js','vendor/fx/uPlot.iife.min.js','vendor/driver.js/dist/driver.js.mjs','vendor/lottie-web/build/player/lottie.min.js','vendor/wavesurfer.js/dist/wavesurfer.esm.js'}
res|={'vendor/nox-planets/nox-%s.jpg'%n for n in 'mercury venus earth mars jupiter saturn uranus neptune'.split()}
for p in pages:
    for f in re.findall(r'<sl-icon[^>]*name="([a-z0-9-]+)"',open('%s/%s.html'%(W,p),encoding='utf-8').read()): res.add('vendor/tabler-icons/icons/outline/%s.svg'%f)
res|={'vendor/tabler-icons/icons/outline/%s.svg'%i for i in 'settings command history adjustments-horizontal paperclip microphone volume arrow-up player-stop plus x check search copy refresh chevron-down chevron-left chevron-right calendar clock movie badge-cc trash download upload calendar-down layout-kanban bell'.split()}
bad=[];n=0
def chk(u):
    global n;n+=1
    try: c=urllib.request.urlopen(B+'/web/'+u,timeout=15).status
    except urllib.error.HTTPError as e: c=e.code
    except Exception as e: c=str(e)[:30]
    if c!=200: bad.append((u,c))
for p in pages: chk(p+'.html')
for u in sorted(res): chk(u)
for u in ['/api/pc-metrics','/api/health','/glm/v1/models','/glm/v1/nox/stats']:
    n+=1
    try: c=urllib.request.urlopen(B+u,timeout=10).status
    except urllib.error.HTTPError as e: c=e.code
    except Exception as e: c=str(e)[:30]
    if c!=200: bad.append((u,c))
print('curl: проверено %d, не 200: %d'%(n,len(bad)),bad[:20])
PY
