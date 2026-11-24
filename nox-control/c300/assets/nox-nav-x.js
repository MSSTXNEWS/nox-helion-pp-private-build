/* NOX · навигация+ (расширение поверх канона, канон не меняет):
   хлебная крошка раздела (группа / страница), последние разделы, датчики ядра и чата
   (раскрываются по наведению). Поиск и Ctrl+K остаются за существующей палитрой канона (ninja-keys). */
(() => {
  if (window.__noxNavX) return; window.__noxNavX = 1;
  const here = location.pathname.split('/').pop() || 'index.html';
  const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = './nox-nav-x.css'; document.head.appendChild(css);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const nm = (t) => String(t || '').replace(/^NOX HELION\s*·\s*/i, '').trim();

  /* последние разделы (для связей между разделами; показ появится в шторке, пока только запись) */
  try {
    const r = JSON.parse(localStorage.getItem('nox.nav.recent') || '[]').filter((x) => x !== here);
    r.unshift(here); localStorage.setItem('nox.nav.recent', JSON.stringify(r.slice(0, 8)));
  } catch (e) { /* хранилище недоступно: не критично */ }

  /* ---------- нижний правый блок: крошка и датчики ---------- */
  const box = document.createElement('div');
  box.id = 'nxnavx'; box.setAttribute('aria-label', 'Контекст раздела и датчики');
  box.innerHTML = '<span class="nxx-crumb" id="nxx-crumb"></span>'
    + '<span class="nxx-sens" tabindex="0" aria-label="Датчики">'
    + '<i class="nxx-dot" data-k="core"></i><span class="nxx-lab" data-k="core">ядро</span>'
    + '<i class="nxx-dot" data-k="chat"></i><span class="nxx-lab" data-k="chat">чат</span></span>';
  const mount = () => document.body && document.body.appendChild(box);
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);

  /* группа раздела из nav.json */
  fetch('./nav.json', { cache: 'no-cache' }).then((r) => r.json()).then((d) => {
    for (const g of d.groups || []) {
      const it = (g.items || []).find((i) => i.file === here);
      if (it) { const el = document.getElementById('nxx-crumb'); if (el) el.innerHTML = '<b>' + esc(nm(g.group)) + '</b> / ' + esc(nm(it.title)); return; }
    }
  }).catch(() => {});

  /* ---------- датчики: ядро и чат, раз в 15 с ---------- */
  const setDot = (k, state, text) => {
    const d = box.querySelector('.nxx-dot[data-k="' + k + '"]'), l = box.querySelector('.nxx-lab[data-k="' + k + '"]');
    if (d) d.dataset.state = state;
    if (l) l.textContent = text;
  };
  const probe = async (k, url, label) => {
    const t0 = performance.now();
    try {
      const r = await fetch(url, { cache: 'no-store' });
      const ms = Math.round(performance.now() - t0);
      setDot(k, r.ok ? (ms > 1500 ? 'warn' : 'ok') : 'warn', label + ' ' + ms + ' мс');
    } catch (e) { setDot(k, 'bad', label + ' нет связи'); }
  };
  const sense = () => { probe('core', './glm/v1/nox/stats', 'ядро'); probe('chat', './api/chat/health', 'чат'); };
  sense(); setInterval(sense, 15000);
})();
