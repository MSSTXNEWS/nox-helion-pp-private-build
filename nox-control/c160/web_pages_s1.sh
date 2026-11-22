#!/bin/bash
# c160: единый кинематографичный веб NOX (Главная, Проекты, Память, Обучение, Ядро, Система, Настройки + общие nox-pages.css / nox-nav.js).
# Файлы берутся с raw.githubusercontent.com (main). Ничего не удаляется: прежние версии сохраняются как *.bak-160.
# chat.html и nox-wow.js НЕ перезаписываются (там идут чужие правки режимов чата): в них вносится только подключение общего меню и уведомлений (точечно, с копией *.bak-160).
W=${NOX_WEB:-/root/nox/web}; N=160; B=${NOX_B:-http://127.0.0.1:8091/web}
R=${NOX_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/s1web/wow}
cd $W || exit 1; FAIL=0; PUT=0
bak(){ [ -f "$1" ] && [ ! -f "$1.bak-$N" ] && cp -p "$1" "$1.bak-$N"; }
put(){ # $1 путь в репозитории, $2 путь назначения
  bak "$2"; if curl -fsSL "$R/$1" -o "$2.new" && [ -s "$2.new" ]; then mv "$2.new" "$2"; PUT=$((PUT+1)); else rm -f "$2.new"; echo "FAIL get $1"; FAIL=$((FAIL+1)); fi; }
for f in index projects memory training models system settings; do put pages/$f.html $W/$f.html; done
for f in nox-pages.css nox-nav.js nox-api.js nox-p-home.js nox-p-projects.js nox-p-memory.js nox-p-memory-extra.js nox-p-training.js nox-p-models.js nox-p-system.js nox-p-settings.js; do put pages/$f $W/$f; done
for f in nox-theme.js nox-notify.js sw.js nox-wow-data.js; do put $f $W/$f; done
# общие стили/фон: во всех копиях (как в c138/c146), кроме classic
for f in nox-wow.css nox-wow-bg.js; do for T in $(find $W -name $f -not -path '*/classic/*' -not -name '*.bak*'); do put $f $T; done; done
[ -f $W/nox-wow.css ] || put nox-wow.css $W/nox-wow.css
# vendor: split.js и dexie (нужны Памяти и Проектам); если нет - ставим из npm как в npm1.sh
if [ ! -s $W/vendor/split.js/split.min.js ] || [ ! -s $W/vendor/dexie/dexie.min.js ]; then
  T=/tmp/npmw160; rm -rf $T; mkdir -p $T; (cd $T && npm init -y >/dev/null 2>&1 && npm i --no-audit --no-fund --silent split.js dexie 2>&1 | tail -2)
  mkdir -p $W/vendor/split.js $W/vendor/dexie; cp $T/node_modules/split.js/dist/split.min.js $W/vendor/split.js/ 2>/dev/null; cp $T/node_modules/dexie/dist/dexie.min.js $W/vendor/dexie/ 2>/dev/null; rm -rf $T; echo "vendor split/dexie: $(ls $W/vendor/split.js $W/vendor/dexie 2>&1 | tr '\n' ' ')"; fi
# чат: точечное подключение общего меню (Резонанс отдельной кнопкой сверху на телефоне, Настройки в нижнем меню), уведомлений и темы
python3 -I - $W <<'PY'
import os,sys,shutil
W=sys.argv[1]
def patch(path,pairs):
    if not os.path.isfile(path): print('нет файла',path); return
    s=open(path,encoding='utf-8').read(); o=s
    for name,fn in pairs:
        r=fn(s)
        if r is None: print('SKIP',os.path.basename(path),name,'(шаблон не найден или уже применено)')
        else: s=r; print('OK',os.path.basename(path),name)
    if s!=o:
        if not os.path.exists(path+'.bak-160'): shutil.copy2(path,path+'.bak-160')
        open(path,'w',encoding='utf-8').write(s)
def ins_before(tag,add,mark):
    return lambda s: None if (mark in s or tag not in s) else s.replace(tag,add+tag,1)
def rep(a,b,mark=None):
    return lambda s: None if (a not in s or (mark and mark in s)) else s.replace(a,b,1)
patch(W+'/chat.html',[
 ('тема',ins_before('</head>','<script src="./nox-theme.js"></script>\n','nox-theme.js')),
 ('кнопка Резонанс сверху',ins_before('<span class="seg icons">','<span class="seg toplink"><a href="chat.html" aria-current="page">Резонанс</a></span>\n      ','toplink')),
 ('слайдер без Резонанса',rep('<a class="swiper-slide" href="chat.html" aria-current="page">Резонанс</a>\n','')),
 ('Настройки в слайдере',rep('<a class="swiper-slide" href="install.html">Установка</a>','<a class="swiper-slide" href="settings.html">Настройки</a>')),
 ('уведомления',ins_before('<script type="module" src="./nox-wow.js">','<script type="module" src="./nox-notify.js"></script>\n','nox-notify.js'))])
def reply_hook(s):
    a="  if (say) { speaker.push(vis.slice(spoken), true); }\n"
    if 'nox:reply-done' in s or a not in s: return None
    return s.replace(a,a+"  if (!failed && !stopped && vis) { try { document.dispatchEvent(new CustomEvent('nox:reply-done', { detail: { text: vis.slice(0, 140) } })); } catch (e) { /* без уведомления */ } }\n",1)
patch(W+'/nox-wow.js',[('слайдер с нуля',rep("initialSlide: 1 }); s.slideTo(1, 0);","initialSlide: 0 }); s.slideTo(0, 0);")),('уведомление «NOX закончил ответ»',reply_hook)])
PY
# проверка: каждая страница и каждый ресурс, на которые они ссылаются
python3 -I - $B $W <<'PY'
import re,sys,urllib.request,urllib.error,os
B=sys.argv[1]; W=sys.argv[2]
pages='index projects memory training models system settings chat'.split()
res=set(); 
for p in pages:
    s=open('%s/%s.html'%(W,p),encoding='utf-8').read()
    for m in re.findall(r'(?:src|href)="(\./[^"]+)"',s): res.add(m[2:])
res|={'nox-wow.css','nox-pages.css','nox-nav.js','nox-api.js','nox-notify.js','nox-theme.js','sw.js','nox-wow-bg.js','nox-wow-data.js','nox-wow-shaders.js','nox-v14-real.js','nox-v14-planet.js','favicon.svg','wow/lottie-ok.json',
 'nox-p-home.js','nox-p-projects.js','nox-p-memory.js','nox-p-memory-extra.js','nox-p-training.js','nox-p-models.js','nox-p-system.js','nox-p-settings.js',
 'vendor/shoelace/cdn/shoelace-autoloader.js','vendor/shoelace/cdn/utilities/base-path.js','vendor/shoelace/cdn/utilities/icon-library.js','vendor/swiper/swiper-bundle.min.mjs','vendor/motion/dist/motion.js','vendor/tsparticles/tsparticles.bundle.min.js',
 'vendor/postprocessing/build/index.js','vendor/nox-planets/manifest.json','vendor/nox-extra/pdf.mjs','vendor/nox-extra/pdf.worker.mjs','vendor/nox-extra/photoswipe.esm.js','vendor/nox-extra/photoswipe-lightbox.esm.js'}
icons=set()
for p in pages+[]:
    s=open('%s/%s.html'%(W,p),encoding='utf-8').read(); icons|=set(re.findall(r'<sl-icon[^>]*name="([a-z0-9-]+)"',s))
for f in os.listdir(W):
    if re.match(r'nox-(p-.*|nav)\.js$',f): icons|=set(re.findall(r'name="([a-z0-9-]+)"',open(W+'/'+f,encoding='utf-8').read()))
icons|={'settings','command','history','paperclip','microphone','volume','arrow-up','player-stop','plus','x','check'}
res|={'vendor/tabler-icons/icons/outline/%s.svg'%i for i in icons}
bad=[]; n=0
def chk(u):
    global n; n+=1
    try: c=urllib.request.urlopen(B+'/'+u,timeout=15).status
    except urllib.error.HTTPError as e: c=e.code
    except Exception as e: c=str(e)[:30]
    if c!=200: bad.append((u,c))
for p in pages: chk(p+'.html')
for u in sorted(res): chk(u)
print('curl: проверено %d, не 200: %d'%(n,len(bad)))
for u,c in bad: print('  ',c,u)
# маркер против повторной вставки nox-web-extras в новые страницы
mk=[p for p in pages[:-1] if 'nox-web-extras' not in open('%s/%s.html'%(W,p),encoding='utf-8').read()]
print('без маркера nox-web-extras:',mk or 'нет')
PY
echo "put=$PUT fail=$FAIL"; for p in index chat projects memory training models system settings; do echo -n "$p=$(curl -s -o /dev/null -w %{http_code} $B/$p.html) "; done; echo
