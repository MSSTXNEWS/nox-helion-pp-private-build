/* NOX · чат как в Telegram: связка поверх nox-wow.js / nox-chat-x.js (идентификаторы и обработчики не меняются). */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const icon = (n) => '<sl-icon library="tabler" name="' + n + '"></sl-icon>';
  let tries = 0;
  const t = setInterval(() => { if ($('#stage') && $('#composer') && $('#btnThreads') && $('#cxChips') && $('#modes') && $('.cx-side') && $('.cx-right')) { clearInterval(t); init(); } else if (++tries > 300) clearInterval(t); }, 100);
  function init() {
    const B = document.body, stage = $('#stage'), comp = $('#composer'), inp = $('#input'), msgs = $('#msgs'), feed = $('#feed');
    B.classList.add('tg');
    /* ---------- шапка ---------- */
    const head = document.createElement('div'); head.className = 'tg-head';
    head.innerHTML = '<button type="button" id="tgBack" aria-label="К чату">' + icon('arrow-left') + '</button><div class="tg-av" aria-hidden="true">N</div><div class="tg-who"><b>NOX HELION</b><span class="tg-sub"></span></div>';
    const tb2 = $('.tb2'); if (tb2) head.appendChild(tb2);
    const wid = document.createElement('button'); wid.type = 'button'; wid.id = 'tgWid'; wid.title = 'Виджеты: Система, Ядро, События'; wid.setAttribute('aria-label', 'Виджеты'); wid.innerHTML = icon('layout-sidebar-right'); head.appendChild(wid);
    stage.prepend(head);
    $('#tgBack').addEventListener('click', () => B.classList.remove('cx-open'));
    const KR = 'nox.tg.right'; let rs = null; try { rs = localStorage.getItem(KR); } catch (e) { /* */ }
    const setR = (o, keep) => { B.classList.toggle('tg-r-open', o); wid.setAttribute('aria-pressed', o); if (keep) try { localStorage.setItem(KR, o ? '1' : '0'); } catch (e) { /* */ } };
    setR(rs === null ? innerWidth >= 1600 : rs === '1');
    wid.addEventListener('click', () => setR(!B.classList.contains('tg-r-open'), true));
    /* ---------- переключатель глубины и кнопка «/» ---------- */
    const modes = $('#modes'); const MR = { auto: 'Авто', fast: 'Быстро', deep: 'Глубоко' }; const ORD = ['auto', 'fast', 'deep'];
    const dep = document.createElement('button'); dep.type = 'button'; dep.id = 'tgDepth'; dep.title = 'Глубина ответа: Авто / Быстро / Глубоко';
    const curMode = () => { const on = modes.querySelector('[aria-checked=true],.on,[aria-pressed=true]'); return on ? on.dataset.m : 'auto'; };
    const syncDep = () => { const m = curMode(); dep.dataset.m = m; dep.innerHTML = '<i></i>' + MR[m]; };
    dep.addEventListener('click', () => { const n = ORD[(ORD.indexOf(curMode()) + 1) % 3]; const b = modes.querySelector('[data-m=' + n + ']'); b && b.click(); setTimeout(syncDep, 50); });
    new MutationObserver(syncDep).observe(modes, { attributes: true, subtree: true }); syncDep();
    const cmd = document.createElement('button'); cmd.type = 'button'; cmd.id = 'tgCmd'; cmd.title = 'Команды ( / )'; cmd.setAttribute('aria-label', 'Команды'); cmd.textContent = '/';
    comp.appendChild(dep); comp.appendChild(cmd);
    /* ---------- меню «/» ---------- */
    const chips = [...document.querySelectorAll('#cxChips button')];
    const menu = document.createElement('div'); menu.className = 'tg-slash'; menu.hidden = true; menu.setAttribute('role', 'listbox'); $('#form').appendChild(menu);
    $('#form').style.position = 'relative';
    let sel = 0, items = [];
    const slashOn = () => inp.value.startsWith('/') && !/\s/.test(inp.value.slice(1).replace(/^\s+/, '')) ;
    function render() {
      if (!slashOn()) { menu.hidden = true; return; }
      const q = inp.value.slice(1).toLowerCase();
      items = chips.filter((b) => !q || b.textContent.toLowerCase().includes(q));
      sel = Math.min(sel, Math.max(0, items.length - 1));
      menu.innerHTML = items.length ? items.map((b, i) => '<button type="button" role="option" data-i="' + i + '" class="' + (i === sel ? 'on' : '') + '"><span class="c">/</span><span class="n">' + esc(b.textContent) + '</span><span class="d">' + esc((b.title || '').slice(0, 90)) + '</span></button>').join('') : '<div class="e">Команд не найдено</div>';
      menu.hidden = false; const on = menu.querySelector('.on'); on && on.scrollIntoView({ block: 'nearest' });
    }
    function pick(i) { const b = items[i]; if (!b) return; inp.value = ''; menu.hidden = true; b.click(); inp.focus(); upd(); }
    inp.addEventListener('input', () => { sel = 0; render(); });
    inp.addEventListener('keydown', (e) => {
      if (menu.hidden) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); e.stopImmediatePropagation(); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % Math.max(1, items.length); render(); }
      else if (e.key === 'Enter' || e.key === 'Tab') { if (items.length) { e.preventDefault(); e.stopImmediatePropagation(); pick(sel); } }
      else if (e.key === 'Escape') { e.preventDefault(); menu.hidden = true; }
    }, true);
    menu.addEventListener('mousedown', (e) => { const b = e.target.closest('button[data-i]'); if (b) { e.preventDefault(); pick(+b.dataset.i); } });
    cmd.addEventListener('click', () => { if (!menu.hidden) { menu.hidden = true; return; } inp.value = '/'; inp.focus(); inp.dispatchEvent(new Event('input', { bubbles: true })); });
    document.addEventListener('click', (e) => { if (!menu.hidden && !e.target.closest('.tg-slash,#tgCmd,#input')) menu.hidden = true; });
    /* ---------- микрофон превращается в «отправить» ---------- */
    let last = null; const upd = () => { const h = !!inp.value.trim(); if (h !== last) { last = h; comp.classList.toggle('has-text', h); } };
    inp.addEventListener('input', upd); setInterval(upd, 250); upd();
    /* ---------- сообщения: время внутри пузыря, долгий тап ---------- */
    function deco(m) {
      if (m.dataset.tg) return; const b = $('.bubble', m); if (!b) return; m.dataset.tg = '1';
      const lab = $('.lab', m); const sp = lab ? lab.querySelectorAll('span') : []; const tm = sp.length > 1 ? sp[sp.length - 1].textContent : '';
      const s = document.createElement('span'); s.className = 'tg-time'; s.textContent = tm; b.appendChild(s);
    }
    const pass = () => msgs.querySelectorAll('.m').forEach(deco);
    new MutationObserver(pass).observe(msgs, { childList: true }); pass();
    let lp = 0;
    msgs.addEventListener('touchstart', (e) => { const m = e.target.closest('.m'); if (!m) return; clearTimeout(lp); lp = setTimeout(() => { msgs.querySelectorAll('.tg-tap').forEach((x) => x.classList.remove('tg-tap')); m.classList.add('tg-tap'); }, 420); }, { passive: true });
    ['touchend', 'touchmove', 'touchcancel'].forEach((ev) => msgs.addEventListener(ev, () => clearTimeout(lp), { passive: true }));
    document.addEventListener('touchstart', (e) => { if (!e.target.closest('.m')) msgs.querySelectorAll('.tg-tap').forEach((x) => x.classList.remove('tg-tap')); }, { passive: true });
    /* ---------- «NOX пишет первым» одной строкой сверху ---------- */
    new MutationObserver(() => { const f = $('.nox-first'); if (f && f.parentNode !== stage) stage.appendChild(f); }).observe(document.body, { childList: true, subtree: true });
    /* ---------- список чатов: аватар, последняя строка, время ---------- */
    const ul = $('#threadList');
    const store = () => { try { const v = JSON.parse(localStorage.getItem('nox.wow.threads') || 'null'); return Array.isArray(v) ? v : (v && (v.list || v.threads || Object.values(v))) || []; } catch (e) { return []; } };
    let busy = false;
    function decoList() {
      if (busy) return; busy = true; const th = store();
      ul.querySelectorAll(':scope>li').forEach((li) => {
        const tt = $('button.t', li); const name = ((tt && tt.childNodes[0] && tt.childNodes[0].textContent) || li.textContent || '').trim();
        const id = li.dataset.id; const d = th.find((x) => x && x.id === id) || {}; const ms = (d.msgs || []).filter((x) => x && x.content); const lm = ms[ms.length - 1];
        const ini = (name.match(/[A-Za-zА-Яа-яЁё0-9]/) || ['N'])[0].toUpperCase(); let h = 0; for (const ch of id || name) h = (h * 31 + ch.charCodeAt(0)) % 360;
        if (li.dataset.ini !== ini) li.dataset.ini = ini; li.style.setProperty('--h', h);
        let last = li.querySelector('.tg-last'), when = li.querySelector('.tg-when');
        if (!last) { last = document.createElement('span'); last.className = 'tg-last'; li.appendChild(last); when = document.createElement('span'); when.className = 'tg-when'; li.appendChild(when); }
        const lt = lm ? (lm.role === 'user' ? 'Вы: ' : '') + String(lm.content).replace(/\s+/g, ' ').slice(0, 70) : 'Нет сообщений';
        if (last.textContent !== lt) last.textContent = lt;
        const ts = lm && lm.ts || d.ts || d.updated; let w = ''; if (ts) { const dt = new Date(ts); const td = new Date(); w = dt.toDateString() === td.toDateString() ? dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : dt.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' }); }
        if (when.textContent !== w) when.textContent = w;
      });
      busy = false;
    }
    new MutationObserver(() => { if (!busy) setTimeout(decoList, 30); }).observe(ul, { childList: true });
    decoList(); setInterval(decoList, 4000);
    /* ---------- «ошибка: уже идёт ответ» - кнопка «Остановить и отправить заново», черновик жив ---------- */
    const KD = 'nox.tg.draft.last';
    document.addEventListener('submit', () => { try { if (inp.value.trim()) sessionStorage.setItem(KD, inp.value); } catch (e) { /* */ } }, true);
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && inp.value.trim()) try { sessionStorage.setItem(KD, inp.value); } catch (x) { /* */ } }, true);
    new MutationObserver(() => {
      msgs.querySelectorAll('.bubble.err .meta:not([data-fix])').forEach((meta) => {
        meta.dataset.fix = '1';
        let draft = ''; try { draft = sessionStorage.getItem(KD) || ''; } catch (e) { /* */ }
        if (draft && !inp.value) { inp.value = draft; inp.dispatchEvent(new Event('input', { bubbles: true })); }   /* черновик не теряется */
        if (!/уже идёт ответ|идёт ответ|busy/i.test(meta.textContent)) return;
        const b = document.createElement('button'); b.type = 'button'; b.className = 'tg-fix'; b.textContent = 'Остановить и отправить заново'; meta.appendChild(document.createElement('br')); meta.appendChild(b);
        b.addEventListener('click', async () => {
          b.disabled = true; b.textContent = 'Снимаю ход…';
          const text = inp.value.trim() || draft;
          try { await fetch('/api/turn/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ all: true }) }); } catch (e) { /* */ }
          document.dispatchEvent(new CustomEvent('nox:stop', { detail: {} }));
          setTimeout(() => { inp.value = text; inp.dispatchEvent(new Event('input', { bubbles: true })); b.textContent = 'Отправляю…'; try { $('#form').requestSubmit(); } catch (e) { /* */ } }, 700);
        });
      });
    }).observe(msgs, { childList: true, subtree: true });
    try { const dr = sessionStorage.getItem(KD); if (dr && !inp.value) { /* черновик после сбоя возвращается только при ошибке */ } } catch (e) { /* */ }
  }
})();
