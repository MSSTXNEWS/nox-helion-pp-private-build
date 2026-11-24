/* NOX · мини-чат на каждой странице: POST /api/chat (NDJSON), контекст = страница, история в localStorage. */
(() => {
  if (window.__noxMini || /(^|\/)chat\.html$/.test(location.pathname)) return; window.__noxMini = 1;
  const KEY = 'nox.minichat.v1', MAX = 40;
  const page = (document.title || '').replace(/^NOX HELION\s*·\s*/i, '').trim() || location.pathname.split('/').pop();
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } };
  const save = (h) => { try { localStorage.setItem(KEY, JSON.stringify(h.slice(-MAX))); } catch (e) {} };
  let hist = load(), busy = null;
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = './nox-minichat.css'; document.head.appendChild(l);
  const fab = document.createElement('button'); fab.type = 'button'; fab.className = 'nmc-fab'; fab.setAttribute('aria-label', 'Диалог с NOX'); fab.title = 'Диалог с NOX';
  fab.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 21 12z"/></svg>';
  const win = document.createElement('section'); win.className = 'nmc'; win.setAttribute('aria-label', 'Диалог с NOX'); win.hidden = true;
  win.innerHTML = '<header><b>NOX</b><span class="nmc-pg"></span><button type="button" class="nmc-clr" title="Очистить историю">ОЧИСТИТЬ</button><button type="button" class="nmc-x" aria-label="Закрыть">×</button></header><div class="nmc-log" aria-live="polite"></div><form><textarea rows="1" placeholder="Сообщение NOX…" enterkeyhint="send"></textarea><button type="submit">→</button></form>';
  document.body.append(fab, win);
  const log = win.querySelector('.nmc-log'), ta = win.querySelector('textarea'), form = win.querySelector('form');
  win.querySelector('.nmc-pg').textContent = page;
  const add = (role, text) => { const d = document.createElement('div'); d.className = 'nmc-m ' + role; d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; };
  const render = () => { log.innerHTML = ''; if (!hist.length) add('sys', 'Спросите что угодно: NOX знает, на какой вы странице.'); hist.forEach((m) => add(m.role === 'user' ? 'u' : 'a', m.content)); };
  const toggle = (on) => { win.hidden = !on; fab.classList.toggle('on', on); if (on) { render(); setTimeout(() => ta.focus(), 50); } };
  fab.onclick = () => toggle(win.hidden);
  win.querySelector('.nmc-x').onclick = () => toggle(false);
  win.querySelector('.nmc-clr').onclick = () => { hist = []; save(hist); render(); };
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && !win.hidden) toggle(false); });
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.onsubmit = async (e) => {
    e.preventDefault(); const q = ta.value.trim(); if (!q || busy) return; ta.value = '';
    hist.push({ role: 'user', content: q }); save(hist);
    if (log.querySelector('.sys')) log.innerHTML = '';
    add('u', q); const out = add('a', '…'); busy = 1; let acc = '';
    const msgs = hist.slice(-12).map((m, i, a) => ({ role: m.role, content: (i === a.length - 1 ? '[Пользователь сейчас на странице «' + page + '»]\n' : '') + m.content }));
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: 'fast', conversation_id: 'minichat', messages: msgs }) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { done, value } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf('\n')) >= 0) { const ln = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (!ln) continue; let o; try { o = JSON.parse(ln); } catch (x) { continue; }
          if (o.error) throw new Error(o.error); const c = o.message && o.message.content; if (c) { acc += c; out.textContent = acc; log.scrollTop = log.scrollHeight; } }
      }
      if (!acc) out.textContent = '(пустой ответ)'; else { hist.push({ role: 'assistant', content: acc }); save(hist); }
    } catch (err) { out.classList.add('err'); out.textContent = 'NOX недоступен: ' + err.message; }
    busy = null;
  };
})();
