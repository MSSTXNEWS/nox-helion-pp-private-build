import { registerRoute } from 'workbox-routing';
import { StaleWhileRevalidate, NetworkFirst } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
self.skipWaiting(); self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
registerRoute(({ url }) => /\/vendor\/|\.(?:css|woff2?|png|jpe?g|svg|webp)$/.test(url.pathname) && !url.pathname.startsWith('/svc/'), new StaleWhileRevalidate({ cacheName: 'nox-static', plugins: [new ExpirationPlugin({ maxEntries: 300, maxAgeSeconds: 7 * 86400 })] }));
registerRoute(({ request, url }) => request.mode === 'navigate' && !url.pathname.startsWith('/svc/'), new NetworkFirst({ cacheName: 'nox-pages', networkTimeoutSeconds: 4, plugins: [new ExpirationPlugin({ maxEntries: 60 })] }));
self.addEventListener('push', (e) => { let d = {}; try { d = e.data.json(); } catch (x) { d = { body: e.data && e.data.text() }; } e.waitUntil(self.registration.showNotification(d.title || 'NOX HELION', { body: d.body || d.message || '', icon: 'icons/icon-192.png' })); });
self.addEventListener('notificationclick', (e) => { e.notification.close(); e.waitUntil(self.clients.matchAll({ type: 'window' }).then((l) => (l[0] ? l[0].focus() : self.clients.openWindow('./index.html')))); });
