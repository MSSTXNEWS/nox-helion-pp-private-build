/* Mini-NOX: короткий вопрос шлюзу с любой страницы (кроме «Резонанса»). Режим Авто/Быстро/Глубоко, честная подпись уровня из ответа шлюза, черновик сохраняется. */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const LS = { g(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } }, s(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* без хранилища */ } }, d(k) { try { localStorage.removeItem(k); } catch (e) { /* без хранилища */ } } };
const MODE_RU = { auto: 'АВТО', fast: 'БЫСТРО', deep: 'ГЛУБОКО' };
export function mountMini() {
  if (document.getElementById('miniFab')) return;
  const fab = document.createElement('button'); fab.type = 'button'; fab.id = 'miniFab'; fab.className = 'mini-fab'; fab.setAttribute('aria-label', 'Mini-NOX: быстрый вопрос'); fab.title = 'Mini-NOX'; fab.innerHTML = '<span class="mono">NOX</span>';
  const pan = document.createElement('section'); pan.id = 'miniPan'; pan.className = 'mini-pan'; pan.hidden = true; pan.setAttribute('aria-label', 'Mini-NOX');
  pan.innerHTML = '<header><b class="mono">MINI-NOX</b><span class="seg"><a href="chat.html" id="miniOpen">В чат</a><button type="button" id="miniX" aria-label="Закрыть"><sl-icon library="tabler" name="x"></sl-icon></button></span></header>'
    + '<div class="seg modes" id="miniModes" role="radiogroup" aria-label="Режим"><button type="button" role="radio" data-m="auto">Авто</button><button type="button" role="radio" data-m="fast">Быстро</button><button type="button" role="radio" data-m="deep">Глубоко</button></div>'
    + '<div class="mini-out" id="miniOut" role="log" aria-live="polite"></div>'
    + '<form id="miniF" autocomplete="off"><textarea id="miniIn" rows="2" maxlength="4000" placeholder="Короткий вопрос NOX…" aria-label="Вопрос Mini-NOX"></textarea><span class="seg"><button type="submit" id="miniSend">Отправить</button><button type="button" id="miniStop" hidden>STOP</button></span></form>';
  document.body.append(fab, pan);
  let mode = LS.g('nox.mini.mode', 'auto'), ctrl = null;
  const syncM = () => pan.querySelectorAll('#miniModes button').forEach((b) => { const on = b.dataset.m === mode; b.setAttribute('aria-checked', String(on)); b.classList.toggle('on', on); });
  syncM(); $('#miniModes').addEventListener('click', (e) => { const b = e.target.closest('button[data-m]'); if (b) { mode = b.dataset.m; LS.s('nox.mini.mode', mode); syncM(); } });
  const inp = $('#miniIn'); inp.value = LS.g('nox.mini.draft', ''); inp.addEventListener('input', () => { if (inp.value.trim()) LS.s('nox.mini.draft', inp.value); else LS.d('nox.mini.draft'); });
  const last = () => { try { return JSON.parse(LS.g('nox.mini.last', 'null')); } catch (e) { return null; } };
  const paint = (q, a, via) => { $('#miniOut').innerHTML = q ? '<div class="mq">' + esc(q) + '</div><div class="ma">' + esc(a || '…') + '</div>' + (via ? '<div class="via mono">' + esc(via) + '</div>' : '') : ''; $('#miniOut').scrollTop = 1e6; };
  const l = last(); if (l) paint(l.q, l.a, l.via);
  const open = (on) => { pan.hidden = !on; fab.setAttribute('aria-expanded', String(on)); if (on) setTimeout(() => inp.focus(), 50); };
  fab.addEventListener('click', () => open(pan.hidden)); $('#miniX').addEventListener('click', () => open(false));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pan.hidden) open(false); });
  $('#miniStop').addEventListener('click', () => ctrl && ctrl.abort());
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('#miniF').requestSubmit(); } });
  $('#miniF').addEventListener('submit', async (e) => {
    e.preventDefault(); const q = inp.value.trim(); if (!q || ctrl) return; ctrl = new AbortController(); $('#miniSend').hidden = true; $('#miniStop').hidden = false;
    let a = '', done = false, seen = new Set(), stages = null, actual = null, local = false, fastSkipped = false, err = null;
    paint(q, '', '');
    try {
      const r = await fetch('/glm/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NOX-Mode': mode }, signal: ctrl.signal, body: JSON.stringify({ messages: [{ role: 'user', content: q }], stream: true, nox_mode: mode }) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) { const { value, done: d } = await rd.read(); if (d) break; buf += dec.decode(value, { stream: true }); let k;
        while ((k = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line.startsWith('data:')) continue; const p = line.slice(5).trim(); if (p === '[DONE]') { done = true; continue; }
          let j; try { j = JSON.parse(p); } catch (x) { continue; } if (j.error) throw new Error(j.error.message || String(j.error));
          if (j.nox) { if (j.nox.stages) stages = j.nox.stages; if (j.nox.actual_s != null) actual = j.nox.actual_s; if (j.nox.skipped_model) local = true; if (j.nox.fast === 'skipped') fastSkipped = true; }
          const c = (j.choices || [{}])[0] || {}; if (c.delta && c.delta.content) { if (c.delta.nox_stage) seen.add(c.delta.nox_stage); a += c.delta.content; paint(q, a.replace(/<think>[\s\S]*?(<\/think>|$)/g, '').trim(), ''); } if (c.finish_reason) done = true; } }
      if (!done) throw new Error('поток оборвался');
    } catch (x) { err = ctrl.signal.aborted ? 'остановлено' : String(x.message || x); }
    const ok = stages ? Object.keys(stages).filter((k) => stages[k] && stages[k].status === 'ok') : [...seen], f = ok.includes('fast'), d = ok.includes('deep');
    const who = local ? 'БЕЗ МОДЕЛИ: ИЗ ПАМЯТИ СЕССИИ' : f && d ? 'ОТВЕТИЛИ: БЫСТРЫЙ УРОВЕНЬ, ЗАТЕМ GLM' : d ? 'ОТВЕТИЛ: GLM (ГЛУБОКИЙ УРОВЕНЬ)' + (fastSkipped ? ' · БЫСТРЫЙ НЕДОСТУПЕН' : '') : f ? 'ОТВЕТИЛ: БЫСТРЫЙ УРОВЕНЬ (НЕ GLM)' : 'УРОВЕНЬ НЕ ПЕРЕДАН';
    const via = who + ' · РЕЖИМ ' + MODE_RU[mode] + (actual != null ? ' · ' + actual + ' С' : '') + (err ? ' · ' + err.toUpperCase() : '');
    a = a.replace(/<think>[\s\S]*?(<\/think>|$)/g, '').trim(); paint(q, a || (err ? '' : '—'), via); LS.s('nox.mini.last', JSON.stringify({ q, a, via })); if (!err) { inp.value = ''; LS.d('nox.mini.draft'); }
    ctrl = null; $('#miniSend').hidden = false; $('#miniStop').hidden = true;
  });
}
