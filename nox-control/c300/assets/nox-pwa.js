/* NOX · PWA и уведомления: регистрация service worker (Workbox), подписка на ntfy (SSE), показ через SW. */
(() => {
  if (window.__noxPwa) return; window.__noxPwa = 1;
  if (!('serviceWorker' in navigator)) return;
  const base = location.pathname.replace(/[^/]*$/, '');
  navigator.serviceWorker.register(base + 'sw.js', { scope: base }).then((reg) => {
    window.NOXPush = { reg, enable: async () => { const p = await Notification.requestPermission(); if (p === 'granted') sub(reg); return p; } };
    if (Notification.permission === 'granted') sub(reg);
  }).catch((e) => console.warn('sw:', e.message));
  let es = null;
  function sub(reg) {
    if (es) return;
    es = new EventSource('/svc/ntfy/nox-helion/sse'); const seen = new Set();
    es.onmessage = (e) => { try { const m = JSON.parse(e.data); if (m.event !== 'message' || seen.has(m.id)) return; seen.add(m.id); reg.showNotification(m.title || 'NOX HELION', { body: m.message, icon: base + 'icons/icon-192.png', badge: base + 'icons/icon-192.png', tag: m.id }); } catch (x) {} };
  }
})();
