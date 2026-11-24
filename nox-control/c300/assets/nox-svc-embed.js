/* NOX · встроенные сервисы на страницах разделов: честный статус (/svc/_status) + рамка с сервисом. */
(() => {
  const MAP = { cinema: ['jellyfin'], music: ['navidrome'], board: ['freshrss'], dispatcher: ['kuma'], memory: ['memos'], down: ['filebrowser', 'metube'], studio: ['invoke'] };
  const page = document.body.dataset.page; const list = MAP[page]; if (!list) return;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const go = async () => {
    const wrap = document.querySelector('.page .wrap') || document.querySelector('main'); if (!wrap || wrap.querySelector('.nsv')) return;
    let st = {}; try { st = (await (await fetch('/svc/_status', { cache: 'no-store' })).json()).services || {}; } catch (e) { st = {}; }
    const sec = document.createElement('section'); sec.className = 'card nsv';
    sec.innerHTML = '<h2>Сервис <span class="r mono" id="nsvT">…</span></h2><div class="nsv-tabs"></div><div class="nsv-st"></div><div class="nsv-box"></div>';
    wrap.appendChild(sec);
    const tabs = sec.querySelector('.nsv-tabs'), stEl = sec.querySelector('.nsv-st'), box = sec.querySelector('.nsv-box');
    let cur = null;
    const pick = (k) => {
      cur = k; const v = st[k]; tabs.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.k === k));
      const t = (v && v.title) || k; sec.querySelector('#nsvT').textContent = t.toUpperCase();
      if (!v) { stEl.innerHTML = '<i class="led warn"></i> ' + esc(t) + ': не установлен на сервере. Кнопок-заглушек нет.'; box.innerHTML = ''; return; }
      if (!v.up) { stEl.innerHTML = '<i class="led warn"></i> ' + esc(t) + ': установлен, но не отвечает (порт ' + v.port + '). ' + (v.note ? esc(v.note) : ''); box.innerHTML = ''; return; }
      stEl.innerHTML = '<i class="led ok"></i> ' + esc(t) + ': работает (127.0.0.1:' + v.port + ' через /svc/' + esc(k) + '/) <a class="tag" target="_blank" href="/svc/' + esc(k) + '/">В НОВОЙ ВКЛАДКЕ</a>' + (v.note ? ' <span class="mono">' + esc(v.note) + '</span>' : '');
      box.innerHTML = '<iframe src="/svc/' + esc(k) + '/" loading="lazy" allow="autoplay; fullscreen; clipboard-write" title="' + esc(t) + '"></iframe>';
    };
    list.forEach((k) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'tag'; b.dataset.k = k; b.textContent = ((st[k] && st[k].title) || k).toUpperCase(); b.onclick = () => pick(k); tabs.appendChild(b); });
    pick(list.find((k) => st[k] && st[k].up) || list[0]);
  };
  const css = document.createElement('style');
  css.textContent = '.nsv-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}.nsv-tabs .tag.on{background:linear-gradient(90deg,rgba(176,44,32,.85),rgba(110,26,20,.6));color:#fff}.nsv-st{font-size:12px;letter-spacing:.06em;margin:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap}.nsv-box iframe{width:100%;height:72vh;min-height:420px;border:1px solid rgba(255,225,200,.1);border-radius:14px;background:rgba(8,7,8,.6)}@media(max-width:600px){.nsv-box iframe{height:68vh}}';
  document.head.appendChild(css);
  let busy = 0, cache = null;
  const ensure = async () => { if (busy || document.querySelector('.nsv')) return; busy = 1; try { await go(); } finally { busy = 0; } };
  (window.requestIdleCallback || setTimeout)(() => setTimeout(ensure, 900));
  let tm = 0; new MutationObserver(() => { clearTimeout(tm); tm = setTimeout(() => { if (!document.querySelector('.nsv') && document.querySelector('.page .wrap')) ensure(); }, 400); }).observe(document.body, { childList: true, subtree: true });
})();
