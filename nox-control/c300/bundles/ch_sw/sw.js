/* NOX · service worker v s1-4 (CH): network-first для HTML и nox-*.js/css (кэш только офлайн-запас), skipWaiting+claim, старые кэши удаляются, открытые вкладки один раз перезагружаются при обновлении SW. */
const V = 'nox-s1-v4-ch';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil((async () => {
  let fresh = false;
  try { const mk = 'nox-ver:' + V; fresh = !(await caches.has(mk)); for (const k of await caches.keys()) if (k !== V && k !== mk) await caches.delete(k); await caches.open(mk); } catch (x) { fresh = true; }
  await self.clients.claim();
  if (fresh) { try { const cs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true }); for (const c of cs) { try { c.navigate(c.url).catch(() => { }); } catch (x) { /* вкладка не даёт навигацию (не ждём: активация не должна зависеть от навигации) */ } } } catch (x) { /* нет клиентов */ } }
})()); });
const OWN = (u) => { try { const p = new URL(u); return p.origin === location.origin && (/\.html?$|\/$/.test(p.pathname) || /\/nox-[^/]*\.(js|css)$/.test(p.pathname) || /\/(vendor\/nox-chat-ui)\//.test(p.pathname)); } catch (x) { return false; } };
self.addEventListener('fetch', (e) => {
  const r = e.request;
  if (r.method !== 'GET' || !(r.mode === 'navigate' || OWN(r.url))) return; /* остальное - напрямую в сеть */
  e.respondWith((async () => {
    const key = r.url.split('?')[0];
    try {
      const res = await fetch(r.mode === 'navigate' ? r : new Request(r, { cache: 'no-cache' }));
      if (res && res.ok) { try { const c = await caches.open(V); c.put(r.mode === 'navigate' ? key : r.url, res.clone()); } catch (x) { /* не критично */ } }
      return res;
    } catch (err) {
      try { const c = await caches.open(V); const hit = (await c.match(r.mode === 'navigate' ? key : r.url)) || (await c.match(key)); if (hit) return hit; } catch (x) { /* нет */ }
      if (r.mode !== 'navigate') return Response.error();
      return new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body style="background:#05060d;color:#f3e9e4;font:16px system-ui;padding:40px"><h2>NOX HELION</h2><p>Сервер не ответил. Обновите страницу через несколько секунд.</p><p><a style="color:#ffb38a" href="">Обновить</a></p>', { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }
  })());
});
self.addEventListener('notificationclick', (e) => { e.notification.close(); e.waitUntil(self.clients.matchAll({ type: 'window' }).then((cs) => { for (const c of cs) { if ('focus' in c) return c.focus(); } return self.clients.openWindow('./chat.html'); })); });
self.addEventListener('push', (e) => { let d = {}; try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data && e.data.text() }; } e.waitUntil(self.registration.showNotification(d.title || 'NOX HELION', { body: d.body || d.message || '', icon: './icons/icon-192.png', badge: './icons/icon-192.png', tag: d.tag })); });

