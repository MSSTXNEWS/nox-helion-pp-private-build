/* C: «вау»-слой чата: стадии «NOX думает», курсор стрима, стадии проверки после ответа, мгновенный отклик Enter. Без правки сервера; читает копию SSE через fetch. */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const reduce = matchMedia('(prefers-reduced-motion:reduce)').matches;
  let live = false, t0 = 0, tmr = 0, caret = null, obs = null;
  /* 1. стадии над голограммой «NOX думает» */
  function stageText(t) { return t < 1.5 ? 'вспоминаю…' : t < 8 ? 'думаю…' : t < 40 ? 'модель отвечает дольше обычного…' : 'модель просыпается, это до 2 минут…'; }
  function tick() { const sp = $('.cx-hl span'); if (sp && live) sp.textContent = 'NOX · ' + stageText((performance.now() - t0) / 1000); }
  /* 2. курсор стрима */
  function lastA() { const a = document.querySelectorAll('#feed .m.a'); return a[a.length - 1]; }
  function moveCaret() {
    const a = lastA(); if (!a) return; if (!caret) { caret = document.createElement('span'); caret.className = 'cw-caret'; caret.setAttribute('aria-hidden', 'true'); }
    const w = document.createTreeWalker(a, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.nodeValue.trim() && !n.parentElement.closest('.rq-meta,.rq-think,.acts,time,button,sl-button,.lab,.rq-act,.cx-lvl')) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
    let n, last = null; while ((n = w.nextNode())) last = n; if (last && last.parentElement && last.parentElement.lastChild !== caret) last.parentElement.appendChild(caret);
  }
  function startLive() { live = true; t0 = performance.now(); clearInterval(tmr); tmr = setInterval(tick, 250); }
  function streamStart() { const a = lastA(); if (a) a.classList.add('cw-live'); if (obs) obs.disconnect(); const f = $('#feed'); if (f) { obs = new MutationObserver(moveCaret); obs.observe(f, { childList: true, subtree: true, characterData: true }); } moveCaret(); }
  function streamEnd() { live = false; clearInterval(tmr); if (obs) obs.disconnect(); caret && caret.remove(); document.querySelectorAll('.cw-live').forEach((x) => x.classList.remove('cw-live')); }
  /* 3. стадии проверки после ответа: судьи → сеть → советник */
  let pst = 0;
  function pendingStages() { clearInterval(pst); const t = performance.now(); pst = setInterval(() => { const e = $('.rq-pending'); if (!e) { clearInterval(pst); return; } const s = (performance.now() - t) / 1000; e.textContent = (s < 4 ? 'судьи' : s < 10 ? 'судьи → сеть' : 'судьи → сеть → советник') + ' · проверяется…'; }, 400); }
  /* fetch-тап: читаем копию потока */
  const of = window.fetch;
  window.fetch = function (u, o) {
    const url = typeof u === 'string' ? u : (u && u.url) || ''; const chat = /\/api\/(chat|turn)(\?|$)/.test(url) && o && o.method === 'POST';
    if (chat) startLive();
    const p = of.apply(this, arguments);
    if (chat) p.then((r) => { try { tap(r.clone()); } catch (e) { } }).catch(() => { });
    return p;
  };
  async function tap(r) {
    if (!r.body) return; const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', started = false;
    for (;;) { const { done, value } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true }); let i;
      while ((i = buf.indexOf('\n')) >= 0) { const ln = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!ln) continue; let o; try { o = JSON.parse(ln); } catch (e) { continue; }
        if (o.t === 'delta' && !started) { started = true; streamStart(); }
        if (o.t === 'done') { streamEnd(); }
        if (o.t === 'meta2' && o.meta && o.meta.pending) pendingStages(); } }
    streamEnd();
  }
  /* 4. мгновенный отклик на Enter */
  document.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { const f = $('#form'); if (f && e.target.closest && e.target.closest('#form')) { f.classList.add('cw-send'); setTimeout(() => f.classList.remove('cw-send'), 320); } } }, true);
})();
