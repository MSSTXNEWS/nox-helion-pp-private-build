#!/bin/bash
# b_empty_overlay.sh: модуль nox-empty-x (герой + ряды на CSS scroll-snap, стекло) для cinema/music/news; бэкап HTML; Readability в vendor; проверка Playwright 390/1440
set -u
W=/workspace/nox; S=$W/web/site; TS=$(date -u +%Y%m%d_%H%M%S); OUT=$S/qa/empty; mkdir -p $OUT
for f in cinema music news; do cp $S/$f.html $S/$f.html.bak_b_empty_$TS; done
cat > $S/nox-empty-x.css <<'CSS'
.nox-hero{margin:12px 0 18px;padding:clamp(18px,4vw,40px);border-radius:18px;border:1px solid rgba(255,255,255,.12);background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.02));backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.nox-hero h2{margin:6px 0 8px;font-size:clamp(22px,3.4vw,40px);line-height:1.15}
.nox-hero p{margin:0 0 14px;max-width:62ch;opacity:.82;font-size:clamp(14px,1.4vw,17px)}
.nox-hero .nox-cta{display:flex;gap:10px;flex-wrap:wrap}
.nox-hero button{min-height:44px;padding:10px 18px;border-radius:12px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:inherit;cursor:pointer;transition:transform .2s,background .2s}
.nox-hero button:hover,.nox-hero button:active{transform:translateY(-1px);background:rgba(255,255,255,.16)}
.nox-row{margin:14px 0}
.nox-row h3{font-size:15px;margin:0 0 8px;opacity:.9}
.nox-scroll{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding:4px 2px 10px;-webkit-overflow-scrolling:touch}
.nox-card{flex:0 0 min(260px,72vw);scroll-snap-align:start;min-height:120px;padding:16px;border-radius:14px;text-align:left;color:inherit;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);cursor:pointer;transition:transform .2s,background .2s,border-color .2s;font:inherit}
.nox-card:hover,.nox-card:focus-visible{transform:translateY(-2px);background:rgba(255,255,255,.11);border-color:rgba(255,255,255,.24)}
.nox-card:active{transform:scale(.985)}
.nox-card b{display:block;font-size:16px;margin-bottom:6px}
.nox-card span{font-size:13px;opacity:.7}
@media (max-width:420px){.nox-hero{border-radius:14px}.nox-card{flex-basis:78vw}}
@media (min-width:1600px){.nox-hero h2{font-size:48px}.nox-card{flex-basis:320px;min-height:150px}}
CSS
cat > $S/nox-empty-x.js <<'JS'
(function(){
  var page = document.body && document.body.dataset.page;
  var C = {
    cinema: {kick:'Кинозал · локальный плеер', title:'Смотрите свои файлы здесь', text:'Файл не уходит на сервер. Позиции запоминаются в этом браузере.',
      cta:[['Открыть файл','#pickV'],['Субтитры','#pickS']],
      rows:[{h:'Действия', items:[['Открыть видео или аудио','Выберите файл на устройстве','#pickV'],['Добавить субтитры','Файлы .vtt или .srt','#pickS'],['Забыть позиции','Очистить память просмотра','#clearP']]}]},
    music: {kick:'Музыка · служба :8102', title:'Создайте трек описанием', text:'Генерация идёт через сервис музыки. Если служба не запущена, статус покажется здесь честно.',
      cta:[['Создать трек','#mPrompt']],
      rows:[{h:'Разделы', items:[['Описание звука','Напишите, что нужно услышать','#mPrompt'],['Плеер','Проигрывание созданного трека','#mAud'],['Луп','Повтор фрагмента','#mLoop']]}]},
    news: {kick:'Новости · FreshRSS', title:'Лента новостей', text:'Лента FreshRSS пока не подключена: входа в сервис нет, поэтому новости не показываются. Это состояние подключения, а не ошибка сайта.',
      cta:[], rows:[]}
  };
  var cfg = C[page]; if (!cfg) return;
  var wrap = document.querySelector('#page .wrap'); if (!wrap) return;
  var hero = document.createElement('section'); hero.className = 'nox-hero card';
  hero.innerHTML = '<span class="kick mono"></span><h2></h2><p></p><div class="nox-cta"></div>';
  hero.querySelector('.kick').textContent = cfg.kick;
  hero.querySelector('h2').textContent = cfg.title;
  hero.querySelector('p').textContent = cfg.text;
  var cta = hero.querySelector('.nox-cta');
  cfg.cta.forEach(function(b){ var btn = document.createElement('button'); btn.type='button'; btn.textContent = b[0]; btn.onclick = function(){ act(b[1]); }; cta.appendChild(btn); });
  if (!cfg.cta.length) cta.remove();
  var ph = wrap.querySelector('.ph');
  wrap.insertBefore(hero, ph ? ph.nextSibling : wrap.firstChild);
  cfg.rows.forEach(function(r){
    var sec = document.createElement('section'); sec.className = 'nox-row';
    sec.innerHTML = '<h3></h3><div class="nox-scroll"></div>';
    sec.querySelector('h3').textContent = r.h;
    var sc = sec.querySelector('.nox-scroll');
    r.items.forEach(function(it){
      var card = document.createElement('button'); card.type='button'; card.className='nox-card';
      card.innerHTML = '<b></b><span></span>';
      card.querySelector('b').textContent = it[0]; card.querySelector('span').textContent = it[1];
      card.onclick = function(){ act(it[2]); };
      sc.appendChild(card);
    });
    hero.insertAdjacentElement('afterend', sec);
  });
  function act(sel){
    var el = document.querySelector(sel); if (!el) return;
    if (el.tagName === 'INPUT' && el.type !== 'checkbox') { el.focus(); el.scrollIntoView({behavior:'smooth', block:'center'}); }
    else if (el.tagName === 'INPUT' || el.tagName === 'AUDIO' || el.tagName === 'VIDEO') { if (el.type === 'checkbox') el.click(); else el.focus(); }
    else el.click();
  }
})();
JS
python3 - "$S" <<'PY'
import sys,os
S=sys.argv[1]
for f in ("cinema.html","music.html","news.html"):
    p=os.path.join(S,f); s=open(p,encoding='utf-8').read()
    if "nox-empty-x" in s: print("skip",f); continue
    s=s.replace("</head>",'<link rel="stylesheet" href="./nox-empty-x.css?v=1">\n</head>',1)
    s=s.replace("</body>",'<script src="./nox-empty-x.js?v=1" defer></script>\n</body>',1)
    open(p,'w',encoding='utf-8').write(s); print("tagged",f)
PY
mkdir -p $S/vendor/nox-lib/readability && curl -fsSL --max-time 60 https://raw.githubusercontent.com/mozilla/readability/main/Readability.js -o $S/vendor/nox-lib/readability/Readability.js && echo "readability ok $(wc -c < $S/vendor/nox-lib/readability/Readability.js) bytes" || echo "readability download failed"
cd $S && (python3 -m http.server 8778 --bind 127.0.0.1 >/tmp/b_http5.log 2>&1 &); sleep 2
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
            try:
                pg.goto("http://127.0.0.1:8778/%s.html"%name, wait_until="load", timeout=40000); pg.wait_for_timeout(1200)
                n=pg.evaluate("document.querySelectorAll('.nox-card').length")
                pg.screenshot(path=f"{out}/{name}_{tag}.png")
                print(name,tag,"cards=",n,"pageerrors=",len(errs),errs[:2], "overflowX=", pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"))
            except Exception as e: print(name,tag,"FAIL",str(e)[:120])
            ctx.close()
    b.close()
PY
pkill -f "http.server 8778" 2>/dev/null; true
