/* NOX · service worker: уведомления (напоминания по задачам, «NOX закончил ответ»). Кэша и перехвата запросов нет. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || 'chat.html', self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const c of list) { if (c.url === url && 'focus' in c) return c.focus(); }
    for (const c of list) { if ('navigate' in c && 'focus' in c) return c.navigate(url).then((x) => x && x.focus()); }
    return self.clients.openWindow(url);
  }));
});
