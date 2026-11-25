S=/workspace/nox/web/site
cd $S
[ -f sw.js.bak_s1_1 ] || cp -p sw.js sw.js.bak_s1_1
echo OLDSW_TAIL; tail -c 1200 sw.js.bak_s1_1; echo; grep -o "push\|notificationclick\|precacheAndRoute\|NavigationRoute" sw.js.bak_s1_1 | sort | uniq -c
cat > sw.js <<'P'
/* NOX · service worker v s1-3: навигация всегда идёт в сеть (откат на кэш, затем на заглушку), ошибок не отдаёт; старые кэши Workbox удаляются. */
const V = 'nox-s1-v3';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil((async () => { try { for (const k of await caches.keys()) if (k !== V) await caches.delete(k); } catch (x) { /* нет кэша */ } await self.clients.claim(); })()); });
self.addEventListener('fetch', (e) => {
  const r = e.request;
  if (r.method !== 'GET' || r.mode !== 'navigate') return; /* остальное - напрямую в сеть, SW не вмешивается */
  e.respondWith((async () => {
    try {
      const res = await fetch(r);
      if (res && res.ok) { try { const c = await caches.open(V); c.put(r.url.split('?')[0], res.clone()); } catch (x) { /* не критично */ } }
      return res;
    } catch (err) {
      try { const c = await caches.open(V); const hit = await c.match(r.url.split('?')[0]); if (hit) return hit; } catch (x) { /* нет */ }
      return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body style="background:#05060d;color:#f3e9e4;font:16px system-ui;padding:40px"><h2>NOX HELION</h2><p>Сервер не ответил. Обновите страницу через несколько секунд.</p><p><a style="color:#ffb38a" href="">Обновить</a></p>', { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }
  })());
});
self.addEventListener('notificationclick', (e) => { e.notification.close(); e.waitUntil(self.clients.matchAll({ type: 'window' }).then((cs) => { for (const c of cs) { if ('focus' in c) return c.focus(); } return self.clients.openWindow('./chat.html'); })); });
P
for f in nox-pult.js nox-nav-x.js; do [ -f $f.bak_s1_1 ] || cp -p $f $f.bak_s1_1; sed -i "s#'\./glm/v1/nox/stats'#'/glm/v1/nox/stats'#g; s#'\./api/chat/health'#'/api/chat/health'#g" $f; done
[ -f chat.html.bak_s1_1 ] || cp -p chat.html chat.html.bak_s1_1
sed -i 's#<form class="dock" id="form" autocomplete="off">#<form class="dock" id="form" autocomplete="off" method="post" action="javascript:void(0)" onsubmit="event.preventDefault();return false">#' chat.html
grep -c 'onsubmit="event.preventDefault' chat.html; grep -n "glm/v1/nox/stats\|api/chat/health" nox-pult.js nox-nav-x.js | cut -c1-120
grep -rn "'\.\?/\?sw\.js\|sw\.js" --include=*.js --include=*.html . 2>/dev/null | grep -v "bak_\|vendor\|^./sw.js" | cut -c1-140 | head -5
cat > /tmp/s1_swtest.py <<'P'
from playwright.sync_api import sync_playwright
import json
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900}); pg=ctx.new_page()
    errs=[]; bad=[]; navs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
    pg.on('response',lambda r:bad.append('%d %s'%(r.status,r.url[-80:])) if r.status>=400 else None)
    pg.on('framenavigated',lambda f:navs.append(f.url[-60:]) if f==pg.main_frame else None)
    pg.goto('http://localhost:8091/web/chat.html',wait_until='load'); pg.wait_for_timeout(5000)
    print('SW ctrl',pg.evaluate("navigator.serviceWorker.getRegistration().then(r=>r&&r.active&&r.active.scriptURL)"))
    def ask(t):
        pg.fill('#input',t); pg.keyboard.press('Enter')
        for i in range(45):
            pg.wait_for_timeout(2000)
            if not pg.evaluate("document.body.classList.contains('nox-busy')") and i>0: break
        r=pg.evaluate("(()=>{const a=[...document.querySelectorAll('#msgs .m.a .txt')].pop();return a?a.innerText:''})()")
        print('REPLY',json.dumps(r,ensure_ascii=False)[:200],'ERRBUBBLE',pg.evaluate("!!document.querySelector('.bubble.err')"),'URL',pg.url[-40:])
    ask('привет')
    # кнопка отправки
    pg.fill('#input','как дела'); pg.click('#btnSend'); pg.wait_for_timeout(1500); print('after click url',pg.url[-40:])
    pg.wait_for_timeout(20000)
    pg.reload(wait_until='load'); pg.wait_for_timeout(4000)
    print('controlled',pg.evaluate("!!navigator.serviceWorker.controller"))
    ask('ещё раз привет')
    # отправка формы без JS-обработчика: имитация GET
    pg.evaluate("document.getElementById('form').requestSubmit()"); pg.wait_for_timeout(800); print('requestSubmit url',pg.url[-40:])
    print('ERRS',errs[:4]); print('NAVS',navs); print('BAD',bad[:10])
    b.close()
P
cd /tmp; timeout 280 /workspace/nox/venv/bin/python /tmp/s1_swtest.py 2>&1 | cut -c1-400
