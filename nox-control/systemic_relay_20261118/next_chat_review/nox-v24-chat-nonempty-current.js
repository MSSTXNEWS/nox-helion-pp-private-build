/* NOX CHAT V24 — glass resonance: one NOX, SSE stream, typing dots, S03, STOP. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const act = k => document.querySelector('[data-action="' + k + '"]');
  const body = document.body, root = document.documentElement;
  const LS = 'nox_v24_dialog', LS_ARC = 'nox_v24_archived', LS_RAIL = 'nox_v24_rail';
  const state = { dialog: null, active: null, status: null, address: 'auto', memPrev: null, archived: [] };
  try { state.archived = JSON.parse(localStorage.getItem(LS_ARC) || '[]'); if (!Array.isArray(state.archived)) state.archived = []; } catch { state.archived = []; }
  const say = t => { const n = $('chatHold'); if (n) n.textContent = t || ''; };
  const thought = t => { const n = $('noxV22Thought'); if (n) n.textContent = t || ''; };
  const LABEL = { thinking: 'NOX · думает', speaking: 'NOX · говорит', stopped: 'NOX · STOP', error: 'NOX · пауза', done: 'NOX · ответил', idle: 'NOX' };
  const phase = p => { body.dataset.noxPhase = p; const n = $('noxV22Phase'); if (n) n.textContent = LABEL[p] || 'NOX'; window.dispatchEvent(new CustomEvent('nox-core-state', { detail: { phase: p, at: Date.now() } })); };
  const reduced = () => root.dataset.reducedMotion === 'reduce' || matchMedia('(prefers-reduced-motion: reduce)').matches || body.dataset.noxGfx === 'ECO' || body.dataset.noxFx === 'stop';
  async function getJSON(url, data) {
    const r = await fetch(url, { method: data ? 'POST' : 'GET', cache: 'no-store', headers: data ? { 'Content-Type': 'application/json' } : {}, body: data ? JSON.stringify(data) : undefined });
    if (!r.ok) throw Error('HTTP ' + r.status);
    return r.json();
  }
  function md(text) {
    if (window.marked?.parse && window.DOMPurify?.sanitize) {
      try {
        const html = window.DOMPurify.sanitize(window.marked.parse(text || '', { breaks: true, gfm: true }), { USE_PROFILES: { html: true } });
        return html;
      } catch { }
    }
    return null;
  }
  function highlight(node) {
    if (!window.hljs || !node) return;
    node.querySelectorAll('pre code').forEach(c => { try { window.hljs.highlightElement(c); } catch { } });
  }

  /* ---- cursor-reactive light (one layer, rAF, skipped in ECO/STOP/reduced) ---- */
  let mx = innerWidth / 2, my = innerHeight / 2, rafC = 0;
  function paintCursor() {
    rafC = 0;
    if (reduced()) return;
    root.style.setProperty('--v24-mx', mx + 'px');
    root.style.setProperty('--v24-my', my + 'px');
  }
  addEventListener('pointermove', e => { mx = e.clientX; my = e.clientY; if (!rafC && !reduced()) rafC = requestAnimationFrame(paintCursor); }, { passive: true });

  /* ---- rail / menus ---- */
  function setRail(collapsed) {
    const rail = $('v24Rail'); if (!rail) return;
    rail.dataset.collapsed = String(collapsed);
    try { localStorage.setItem(LS_RAIL, collapsed ? '1' : '0'); } catch { }
    if (window.gsap && !reduced()) window.gsap.to(rail, { width: collapsed ? 0 : 'var(--v24-rail)', opacity: collapsed ? 0 : 1, duration: 0.28, ease: 'power2.out' });
  }
  function setSystem(open) {
    const d = $('v24System'); if (!d) return;
    d.hidden = !open; d.dataset.open = String(open);
    if (window.gsap && !reduced() && open) window.gsap.fromTo(d, { x: 24, opacity: 0 }, { x: 0, opacity: 1, duration: 0.28, ease: 'power2.out' });
  }
  function setMenu(open) {
    const m = $('v24Menu'); if (!m) return;
    m.hidden = !open; m.dataset.open = String(open);
    const b = act('open-menu'); if (b) b.setAttribute('aria-expanded', String(open));
  }

  /* ---- messages: letter avatars only, no name labels ---- */
  function message(role, text, meta, opts = {}) {
    const mine = role === 'user';
    const box = el('article', undefined, 'v24-msg v24-glass ' + (mine ? 'me' : 'nox'));
    const ava = el('span', mine ? 'V' : 'N', 'v24-ava');
    ava.setAttribute('aria-hidden', 'true');
    ava.title = mine ? 'Создатель' : 'NOX';
    const main = el('div', undefined, 'v24-msg-main');
    const b = el('div', undefined, 'body');
    if (!mine && opts.markdown !== false) {
      const h = md(text || ''); if (h !== null) { b.innerHTML = h; highlight(b); } else b.textContent = text;
      if (window.NOX?.ux?.renderMarkdown) { void window.NOX.ux.renderMarkdown(b, text || ''); }
    }
    else b.textContent = text || '';
    const m = el('small', meta || '', 'meta');
    main.append(b, m);
    if (opts.thinking) {
      const dots = el('span', undefined, 'v24-dots'); dots.setAttribute('aria-label', 'NOX печатает');
      dots.append(el('i'), el('i'), el('i')); b.append(dots); box.classList.add('thinking');
    }
    box.append(ava, main);
    if (opts.status === 'stopped') box.classList.add('stopped');
    if (opts.source) box.dataset.source = opts.source;
    $('messages').append(box); scroll();
    return { box, body: b, meta: m };
  }
  const scroll = () => { const m = $('messages'); m.scrollTop = m.scrollHeight; };
  function emptyHint() {
    if ($('messages').children.length) return;
    const p = el('div', undefined, 'v24-empty'); p.append(el('b', 'NOX СЛУШАЕТ'), el('span', 'Напишите — каждое слово сохранится в памяти навсегда.'));
    $('messages').append(p);
  }
  function controls() {
    const busy = Boolean(state.active);
    const stop = act('stop'), send = act('send'), neu = act('new-chat');
    if (stop) stop.disabled = !busy;
    if (send) send.disabled = busy || !state.status?.model;
    if (neu) neu.disabled = busy;
    $('quickCommands')?.querySelectorAll('button').forEach(b => { b.disabled = busy || (!state.status?.model && b.dataset.cmd !== '/продолжить'); });
  }

  /* ---- status / metrics (drawer only; no red HOLD on the main stage) ---- */
  async function refreshStatus() {
    const banner = $('noxV22Model');
    try {
      const s = await getJSON('/api/nox/status'); state.status = s;
      if (banner) { banner.textContent = (s.model ? '● ' : '') + s.model_label; banner.dataset.kind = s.model_kind; }
      const src = $('noxV22Source');
      if (src) { src.dataset.source = s.answer_source || 'NONE'; src.textContent = s.answer_source_label || ''; }
      body.dataset.answerSource = s.answer_source || 'NONE';
      if (s.stop_flag) say('STOP создателя активен. Напишите «/продолжить».');
      showSafe(s.safe70); if (!state.active) phase('idle');
    } catch { if (banner) banner.textContent = 'Хост чата не отвечает'; state.status = null; }
    controls();
  }
  function showSafe(s) {
    if (!s) return;
    window.dispatchEvent(new CustomEvent('nox-core-safe70', { detail: s }));
    const n = $('noxV22Safe70'); if (!n) return;
    const t = s.gpu_temp_c, note = s.paused ? ('пауза ' + (t != null ? Math.round(t) + '°C' : '')) : (t != null ? Math.round(t) + '°C' : 'нет датчика');
    n.textContent = note; n.dataset.paused = String(Boolean(s.paused)); n.dataset.known = String(t != null);
  }
  const fmt = (v, u) => (typeof v === 'number' && Number.isFinite(v)) ? v.toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + u : '—';
  async function refreshMetrics() {
    try {
      const m = await getJSON('/api/pc-metrics'); showSafe(m.safe70);
      const set = (id, t) => { const n = $(id); if (n) n.textContent = t; };
      set('cpuPercent', fmt(m.cpu_percent, '%'));
      set('gpuReadout', fmt(m.gpu_percent, '%'));
      set('ramPercent', fmt(m.ram_percent, '%'));
      set('gpuTemp', fmt(m.gpu_temperature_c, '°'));
      set('gpuVram', (m.vram_used_gb != null && m.vram_total_gb) ? (m.vram_used_gb + ' / ' + m.vram_total_gb + ' ГБ') : '—');
      set('noxV22MetricSrc', 'Источник: ' + (m.source || '—') + (m.gpu_source ? ' · GPU: ' + m.gpu_source : ''));
    } catch { }
  }


  const dash = (v) => (v === null || v === undefined || v === '') ? '—' : v;
  function etaText(sec) {
    const n = Number(sec); if (!Number.isFinite(n) || n < 0) return '—';
    if (n < 60) return Math.round(n) + ' с';
    if (n < 3600) return Math.round(n / 60) + ' мин';
    return (n / 3600).toFixed(1) + ' ч';
  }
  function bar(id, done, total) {
    const n = $(id); if (!n) return;
    const a = Number(done), b = Number(total);
    const pct = (Number.isFinite(a) && Number.isFinite(b) && b > 0) ? Math.max(0, Math.min(100, 100 * a / b)) : 0;
    n.style.width = pct + '%';
  }
  async function refreshLiveBoard() {
    if (window.NOX_V24_LEARN) return;
    let j; try { j = await getJSON('/api/nox/training-live'); } catch { j = null; }
    const tr = j?.trainer || { status: 'HOLD' }, ix = j?.indexer || { status: 'HOLD' };
    const set = (id, t) => { const n = $(id); if (n) n.textContent = t; };
    const rows = (tr.rows_done != null && tr.rows_total != null) ? (tr.rows_done + ' / ' + tr.rows_total) : dash(tr.rows_done);
    set('v24TrStep', dash(tr.step));
    set('v24TrRows', rows);
    bar('v24TrBar', tr.rows_done, tr.rows_total);
    set('v24TrHold', tr.holdout_improvement_pct != null ? (Number(tr.holdout_improvement_pct).toFixed(2) + ' %') : '—');
    set('v24TrTps', tr.tok_s != null ? Number(tr.tok_s).toLocaleString('ru-RU') : '—');
    const hw = [tr.gpu_percent != null ? (Math.round(tr.gpu_percent) + '%') : null,
      (tr.vram_used_gb != null ? (Number(tr.vram_used_gb).toFixed(1) + (tr.vram_total_gb != null ? '/' + Number(tr.vram_total_gb).toFixed(1) : '') + ' ГБ') : null),
      tr.ram_percent != null ? ('RAM ' + Math.round(tr.ram_percent) + '%') : null].filter(Boolean);
    set('v24TrHw', hw.length ? hw.join(' · ') : '—');
    set('v24TrEta', etaText(tr.eta_sec));
    set('v24TrGguf', dash(tr.gguf_status) + (tr.gguf_path ? ' · ' + String(tr.gguf_path).split(/[\\\\/]/).pop() : ''));
    set('v24TrSrc', tr.status === 'READY' ? ('status.json' + (tr.updated_at ? ' · ' + String(tr.updated_at).replace('T', ' ').slice(0, 19) : '')) : (tr.reason || 'ждём C:\\\\NOX\\\\progress\\\\status.json'));
    const ixRows = (ix.chunks_embedded != null && ix.chunks_total != null) ? (ix.chunks_embedded + ' / ' + ix.chunks_total) : '—';
    set('v24IxChunks', ixRows);
    bar('v24IxBar', ix.chunks_embedded, ix.chunks_total);
    set('v24IxRate', ix.rate_per_min != null ? (Number(ix.rate_per_min).toFixed(1) + ' / мин') : '—');
    const safe = ix.safe70 || {};
    set('v24IxSafe', safe.paused ? ('пауза' + (safe.gpu_temp_c != null ? ' ' + Math.round(safe.gpu_temp_c) + '°C' : '')) : (safe.gpu_temp_c != null ? (Math.round(safe.gpu_temp_c) + '°C') : (ix.paused_for_chat ? 'пауза: чат' : (ix.reason || '—'))));
    set('v24IxSrc', ix.status === 'READY' ? ('knowledge.db' + (ix.paused_for_chat ? ' · пауза на время ответа' : '')) : (ix.reason || 'индекс ещё не подключён'));
    const pill = $('v24LivePillText');
    if (pill) {
      if (tr.status === 'READY' && tr.step != null) {
        const pct = (tr.rows_done != null && tr.rows_total) ? Math.round(100 * tr.rows_done / tr.rows_total) + '%' : '';
        pill.textContent = 'шаг ' + tr.step + (pct ? ' · ' + pct : '');
      } else if (ix.status === 'READY' && ix.chunks_embedded != null) {
        pill.textContent = 'индекс ' + ix.chunks_embedded + (ix.chunks_total != null ? '/' + ix.chunks_total : '');
      } else pill.textContent = 'прогресс';
    }
  }

  async function refreshReceipt() {
    let r, b;
    try { r = await getJSON('/api/nox/progress'); } catch { r = { status: 'HOLD', reason: 'HOST_OFFLINE' }; }
    try { b = await getJSON('/api/nox/birth'); } catch { b = { status: 'HOLD' }; }
    const verified = r?.schema === 'nox-progress-receipt-v1' && ['VERIFIED_CHECKPOINT_STEPS', 'VERIFIED_COMPLETE'].includes(r.status) && r.weightUpdateVerified === true;
    const lv = b.local_verification || {}, born = lv.born_at;
    const box = $('noxV22Receipt'); if (box) box.dataset.status = verified ? 'verified' : born ? 'born' : 'hold';
    const st = $('noxV22RStatus');
    if (st) st.textContent = verified ? (r.complete ? 'ПОДТВЕРЖДЕНО' : 'ШАГИ ' + r.completedSteps + '/' + r.targetSteps) : born ? ('Рождён ' + String(born).slice(0, 16).replace('T', ' ')) : (r.reason ? String(r.reason).slice(0, 160) : 'Квитанция ещё не подтверждена');
    const rb = $('noxV22RBody'); if (!rb) return;
    rb.replaceChildren();
    rb.append(el('div', 'Веса ' + (r.weightUpdateVerified ? 'SHA-256 совпал' : 'ещё не сверены') + ' · Windows ' + (r.windowsSyncVerified ? 'да' : 'нет')));
    if (lv.reason && !born) rb.append(el('div', lv.reason));
  }

  const LEVELS = [['M0', 'рабочая', 'M0_working'], ['M1', 'эпизоды', 'M1_episodes'], ['M2', 'знания', 'M2_knowledge'], ['M3', 'время', 'M3_temporal'],
    ['M4', 'навыки', 'M4_skills'], ['M5', 'люди', 'M5_social'], ['M6', 'значимость', 'M6_emotional'], ['M7', 'генезис', 'M7_autobiography']];
  async function refreshMemory() {
    let m; try { m = await getJSON('/api/nox/memory'); } catch { return; }
    const s = m.stats || {}, grid = $('noxV22MGrid'); if (!grid) return;
    grid.replaceChildren();
    for (const [k, d, key] of LEVELS) {
      const v = s[key] ?? 0, b = el('button'); b.type = 'button';
      b.append(el('b', k), el('span', d), el('strong', String(v)));
      b.addEventListener('click', () => openMemory(key)); grid.append(b);
    }
    const note = $('noxV22MemNote');
    if (note) note.textContent = 'Сообщений создателя навсегда: ' + (s.creator_messages ?? 0) + ' · Genesis Ledger: ' + (m.ledger_chain_ok ? 'цела' : 'проверить');
  }
  async function openMemory(focus) {
    const dlg = $('noxV22MemoryDialog'), full = $('noxV22MemoryFull'); if (!dlg || !full) return;
    full.replaceChildren(el('p', 'Чтение S03…', 'v24-mini')); if (!dlg.open) dlg.showModal();
    let m, c; try { [m, c] = await Promise.all([getJSON('/api/nox/memory'), getJSON('/api/nox/creator?limit=12')]); } catch (e) { full.replaceChildren(el('p', 'S03 недоступна: ' + e.message)); return; }
    full.replaceChildren();
    for (const [k, d, key] of LEVELS) {
      const sec = el('section'); const h = el('h3', k + ' · ' + d + ' · ' + (m.stats?.[key] ?? 0));
      sec.append(h); const ol = el('ol');
      for (const x of (m.segments?.[key] || [])) ol.append(el('li', String(x.content).slice(0, 220)));
      if (!ol.children.length) ol.append(el('li', '— пока пусто —'));
      sec.append(ol); full.append(sec);
    }
  }

  /* ---- dialogs: new + list + archive (never delete) ---- */
  function persistArchive() { try { localStorage.setItem(LS_ARC, JSON.stringify(state.archived)); } catch { } }
  function isArchived(id) { return state.archived.includes(id); }
  async function refreshDialogs() {
    let d; try { d = await getJSON('/api/nox/history'); } catch { return []; }
    const list = $('nativeChats'), arc = $('v24ArchiveList');
    if (list) list.replaceChildren();
    if (arc) arc.replaceChildren();
    const all = d.dialogs || [];
    for (const x of all) {
      const row = el('div', undefined, 'v24-chat-item');
      const b = el('button'); b.type = 'button'; b.setAttribute('role', 'listitem');
      b.append(el('span', x.title || 'Диалог', 't'), el('small', String(x.messages)));
      b.setAttribute('aria-current', String(x.id === state.dialog));
      b.addEventListener('click', () => { if (!state.active) loadDialog(x.id); });
      b.addEventListener('dblclick', () => startRename(x.id, x.title));
      const hide = el('button', '⌘', 'v24-archive'); hide.type = 'button';
      hide.title = isArchived(x.id) ? 'Вернуть из архива' : 'Скрыть в архив (сообщения не удаляются)';
      hide.setAttribute('aria-label', hide.title);
      hide.addEventListener('click', ev => {
        ev.stopPropagation();
        if (isArchived(x.id)) state.archived = state.archived.filter(i => i !== x.id);
        else state.archived = [...state.archived, x.id];
        persistArchive(); refreshDialogs();
      });
      row.append(b, hide);
      if (isArchived(x.id)) arc?.append(row); else list?.append(row);
    }
    const hs = $('historyState');
    if (hs) hs.textContent = 'S03 · диалогов ' + all.length + ' · в архиве окна ' + state.archived.length + ' · сообщений создателя навсегда: ' + d.creator_messages_total;
    return all;
  }
  async function loadDialog(id) {
    state.dialog = id; try { localStorage.setItem(LS, id || ''); } catch { }
    $('messages').replaceChildren();
    if (id) {
      const h = await getJSON('/api/nox/history?dialog_id=' + encodeURIComponent(id) + '&limit=200');
      for (const m of h.messages || []) {
        message(m.role === 'user' ? 'user' : 'assistant', m.content,
          m.role === 'user' ? String(m.created_at || '').slice(11, 16) : (m.status === 'stopped' ? 'остановлено STOP' : (m.status || '')) + ' · ' + String(m.created_at || '').slice(11, 16),
          { status: m.status, source: /\[(MOCK|HARNESS)\]/.exec(m.model || '')?.[1] || (/^nox(-prime)?/.test(m.model || '') ? 'LIVE_NOX' : '') });
      }
    }
    emptyHint(); refreshDialogs();
  }
  function startRename(id, title) {
    const rn = $('noxV22Rename'), rni = $('noxV22RenameInput');
    if (!rn || !rni) return;
    state.renameId = id || state.dialog;
    if (!state.renameId) { say('Сначала начните диалог.'); return; }
    rn.hidden = false; rni.value = title || ''; rni.focus(); rni.select();
  }

  /* ---- stream + live typing dots until the first token ---- */
  function streamFailureText(error) {
    const code = String(error?.message || error || '').trim();
    if (code === 'HOLD_CHAT_EMPTY_RESPONSE') return 'Поток NOX завершился без текста ответа. Выполнение задачи не подтверждено.';
    if (code === 'HOLD_CHAT_TERMINAL_MISSING' || code === 'HOLD_CHAT_STREAM_TRUNCATED') return 'Связь с NOX оборвалась до подтверждённого завершения ответа.';
    const publicCode = /^(?:HOLD_[A-Z0-9_]{1,110}|HTTP [1-5][0-9]{2}|STREAM_STOP_REQUESTED)$/.test(code) ? code : '';
    return 'Не удалось получить законченный ответ NOX.' + (publicCode ? ' Код: ' + publicCode + '.' : '');
  }
  const THINK = ['NOX вслушивается…', 'NOX собирает память…', 'NOX взвешивает ответ…'];
  async function send(text) {
    text = (text || '').trim(); if (!text || state.active) return;
    $('messages').querySelector('.v24-empty')?.remove();
    const rid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
    const controller = new AbortController();
    const run = { rid, controller, stopped: false }; state.active = run; controls();
    $('prompt').value = ''; autosize(); window.dispatchEvent(new CustomEvent('nox-typing', { detail: false }));
    message('user', text, '');
    const out = message('assistant', '', '', { markdown: false, thinking: true });
    out.box.classList.add('streaming');
    phase('thinking'); thought(THINK[0]);
    window.dispatchEvent(new CustomEvent('nox-core-speaking', { detail: { active: true } }));
    let result = '', done = null, tokens = 0, t0 = performance.now();
    const thinkTimer = setInterval(() => { if (!tokens) thought(THINK[Math.min(THINK.length - 1, Math.floor((performance.now() - t0) / 1800))]); }, 600);
    try {
      const r = await fetch('/api/nox/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ message: text, dialog_id: state.dialog, request_id: rid, address: state.address }) });
      if (!r.ok || !r.body) throw Error((await r.json().catch(() => ({}))).error || 'HTTP ' + r.status);
      const reader = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) {
        const { value, done: end } = await reader.read(); if (end) break;
        buf += dec.decode(value, { stream: true }); let i;
        while ((i = buf.indexOf('\n\n')) !== -1) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          const line = chunk.split('\n').find(l => l.startsWith('data: ')); if (!line) continue;
          const f = JSON.parse(line.slice(6));
          if (done) throw Error('HOLD_CHAT_FRAME_AFTER_DONE');
          if (f.type === 'meta') {
            if (!state.dialog) { state.dialog = f.dialog_id; try { localStorage.setItem(LS, f.dialog_id); } catch { } }
            out.box.dataset.source = f.answer_source || 'NONE';
          } else if (f.type === 'context') {
            thought(f.memory_hits ? 'Память: ' + f.memory_hits : 'NOX думает…');
          } else if (f.type === 'token') {
            if (typeof f.t !== 'string') throw Error('HOLD_CHAT_TOKEN_TYPE');
            if (!tokens) { phase('speaking'); thought(''); out.box.classList.remove('thinking'); out.body.replaceChildren(); }
            tokens++; result += f.t;
            if (reduced()) out.body.textContent = result;
            else { const s = el('span', f.t, 'tok'); out.body.append(s); if (out.body.childNodes.length > 400) out.body.textContent = result; }
            scroll();
          } else if (f.type === 'replace') {
            if (typeof f.content !== 'string') throw Error('HOLD_CHAT_REPLACE_TYPE');
            result = f.content; out.body.textContent = result; say(f.reason);
          }
          else if (f.type === 'error') throw Error(f.error);
          else if (f.type === 'done') { done = f; if (f.note) say(f.note); }
        }
      }
      buf += dec.decode();
      if (!run.stopped && buf.trim()) throw Error('HOLD_CHAT_STREAM_TRUNCATED');
      if (!run.stopped && !done) throw Error('HOLD_CHAT_TERMINAL_MISSING');
      if (!run.stopped && done?.status === 'done' && !result.trim()) throw Error('HOLD_CHAT_EMPTY_RESPONSE');
      out.box.classList.remove('streaming', 'thinking');
      if (done?.status === 'stopped' || run.stopped) {
        out.box.classList.add('stopped'); out.body.textContent = result || '(остановлено до первого слова)';
        out.meta.textContent = 'остановлено STOP · частичный ответ сохранён'; phase('stopped');
      } else if (done) {
        const h = result && md(result); if (h) { out.body.innerHTML = h; highlight(out.body); } else if (!result.trim()) out.body.textContent = done.status === 'STOP_FLAG' ? 'STOP активен. Запрос не выполнен.' : 'Ответ NOX не завершён. Выполнение задачи не подтверждено.';
        out.meta.textContent = (done.seconds ? done.seconds + ' с' : '') + (done.corrected ? ' · уточнено' : '');
        phase(done.status === 'done' ? 'done' : 'stopped');
      }
    } catch (e) {
      out.box.classList.remove('streaming', 'thinking');
      if (run.stopped) { out.body.textContent = result || '(остановлено до первого слова)'; out.meta.textContent = 'остановлено STOP'; phase('stopped'); }
      else {
        const notice = streamFailureText(e);
        if (!result.trim()) { out.body.textContent = notice; out.box.dataset.source = 'SYSTEM_NOTICE'; }
        out.box.classList.add('error');
        out.meta.textContent = result.trim() ? 'Частичный ответ · ' + notice : 'Ответ не подтверждён';
        phase('error'); say(notice);
      }
    } finally {
      clearInterval(thinkTimer); thought(''); state.active = null; controls();
      window.dispatchEvent(new CustomEvent('nox-core-speaking', { detail: { active: false } }));
      setTimeout(() => { if (!state.active && ['done', 'stopped', 'error'].includes(body.dataset.noxPhase)) phase('idle'); }, 2200);
      refreshDialogs(); refreshMemory(); refreshStatus();
    }
  }
  async function stop() {
    const run = state.active; if (!run || run.stopped) return;
    run.stopped = true; window.dispatchEvent(new CustomEvent('nox-stop-requested')); phase('stopped');
    body.dataset.noxFx = 'stop';
    run.controller.abort();
    setTimeout(() => { if (body.dataset.noxFx === 'stop') body.dataset.noxFx = ''; }, 1200);
  }

  const prompt = $('prompt');
  function autosize() { prompt.style.height = 'auto'; prompt.style.height = Math.min(140, prompt.scrollHeight) + 'px'; }
  prompt.addEventListener('input', () => { autosize(); if (!state.active) { window.dispatchEvent(new CustomEvent('nox-typing', { detail: true })); } });
  prompt.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(prompt.value); } });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.active) { e.preventDefault(); stop(); } });
  $('chatForm').addEventListener('submit', e => { e.preventDefault(); send(prompt.value); });
  act('stop')?.addEventListener('click', stop);
  act('speak')?.addEventListener('click', () => { void speakLast(); });
  act('new-chat')?.addEventListener('click', async () => { if (state.active) return; const d = await getJSON('/api/nox/dialogs/new', { title: 'Новый диалог' }); await loadDialog(d.dialog_id); });
  act('toggle-rail')?.addEventListener('click', () => setRail($('v24Rail').dataset.collapsed !== 'true'));
  act('open-system')?.addEventListener('click', () => { setMenu(false); setSystem($('v24System').dataset.open !== 'true'); });
  act('open-live')?.addEventListener('click', () => { setMenu(false); setSystem(true); $('v24LiveBoard')?.scrollIntoView({ block: 'nearest' }); });
  act('close-system')?.addEventListener('click', () => setSystem(false));
  act('open-menu')?.addEventListener('click', e => { e.stopPropagation(); setSystem(false); setMenu($('v24Menu').dataset.open !== 'true'); });
  act('open-archive')?.addEventListener('click', () => { setMenu(false); setSystem(true); $('v24ArchiveBlock')?.scrollIntoView({ block: 'nearest' }); });
  act('memory-open')?.addEventListener('click', () => openMemory(null));
  act('memory-close')?.addEventListener('click', () => $('noxV22MemoryDialog')?.close());
  document.addEventListener('click', e => { if (!$('v24Menu')?.contains(e.target) && e.target !== act('open-menu') && !act('open-menu')?.contains(e.target)) setMenu(false); });

  const QUICK = [['Кто ты?', 'Привет, кто ты?'], ['Первый вдох', 'Что ты помнишь о своём первом вдохе?'], ['Как ты ко мне обращаешься?', 'Как ты ко мне обращаешься?'],
    ['Что я говорил?', 'Вспомни, что я тебе говорил.'], ['Состояние', 'Какое у тебя состояние?'], ['/продолжить', '/продолжить']];
  for (const [label, text] of QUICK) { const b = el('button', label); b.type = 'button'; b.dataset.cmd = text; b.addEventListener('click', () => send(text)); $('quickCommands')?.append(b); }

  for (const b of document.querySelectorAll('[data-address]')) b.addEventListener('click', async () => {
    state.address = b.dataset.address;
    document.querySelectorAll('[data-address]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.address === state.address)));
    try {
      const tok = (await getJSON('/api/nox/session')).token;
      await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NOX-Session': tok }, body: JSON.stringify({ address: state.address }) });
    } catch { }
    say('Обращение: ' + (state.address === 'auto' ? 'живо, чередуя формы' : '«' + state.address + '»'));
  });

  const rn = $('noxV22Rename'), rni = $('noxV22RenameInput');
  act('rename-cancel')?.addEventListener('click', () => { if (rn) rn.hidden = true; });
  rn?.addEventListener('submit', async e => {
    e.preventDefault(); const title = rni.value.trim(); if (!title || !state.renameId && !state.dialog) return;
    try {
      const r = await fetch('/api/nox/dialog/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dialog_id: state.renameId || state.dialog, title }) });
      const j = await r.json(); if (j.status !== 'READY') throw new Error(j.reason || 'не удалось');
      rn.hidden = true; refreshDialogs();
    } catch (err) { say('Не удалось переименовать: ' + err.message); }
  });

  function applyMood(m) {
    if (!m) return;
    const root = document.documentElement;
    if (m.glow) root.style.setProperty('--nox-mood-glow', m.glow);
    if (m.mood) root.dataset.mood = m.mood;
  }
  async function refreshMood() {
    try { applyMood(await getJSON('/api/nox/mood')); } catch { }
  }
  async function whisperReminders() {
    let data; try { data = await getJSON('/api/nox/reminders/due'); } catch { return; }
    const items = (data && data.items) || [];
    if (!items.length) return;
    const stream = $('v24Stream') || document.querySelector('.v24-stream');
    if (!stream || stream.querySelector('.v24-whisper')) return;
    const texts = items.slice(0, 3).map(it => it.text || it.due_at).join(' · ');
    const msg = 'Напоминание только в этом чате (внешних писем и уведомлений нет): ' + texts;
    const box = message('assistant', msg, 'напоминание', { markdown: false });
    box.classList.add('v24-whisper');
    box.dataset.ephemeral = '1';
  }
  async function speakLast() {
    const last = document.querySelector('.v24-msg.nox:not(.v24-whisper) .body');
    const text = last ? last.innerText || last.textContent : '';
    if (!text) { say('Нет ответа для голоса'); return; }
    try {
      const r = await fetch('/api/nox/voice/speech', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
      const typ = r.headers.get('Content-Type') || '';
      if (!typ.includes('audio')) {
        const j = await r.json().catch(() => ({}));
        say(j.reason || 'Голос HOLD');
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (e) { say('Голос: ' + (e.message || e)); }
  }
  function clock() { const n = $('noxV22Clock'); if (!n) return; const d = new Date(); n.textContent = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow' }); }
  async function wx() {
    let w; try { w = await getJSON('/api/nox/weather'); } catch { w = { status: 'OFFLINE' }; }
    const card = $('noxV22Wx'); if (card) card.dataset.status = w.status;
    if ($('wxTitle')) $('wxTitle').textContent = w.place || 'Мадрид';
    if (w.status === 'READY' || w.status === 'STALE') {
      if ($('noxV22WxTemp')) $('noxV22WxTemp').textContent = Math.round(w.temp_c) + '°';
      if ($('noxV22WxText')) $('noxV22WxText').textContent = w.text || '';
      if ($('noxV22WxMeta')) $('noxV22WxMeta').textContent = (w.note || '') + ' · Open-Meteo';
    } else { if ($('noxV22WxTemp')) $('noxV22WxTemp').textContent = '—'; if ($('noxV22WxText')) $('noxV22WxText').textContent = 'нет данных'; }
  }
  function governor() {
    const st = window.NoxCoreBg?.state?.();
    if (st?.tier) body.dataset.noxGfx = st.tier;
    const g = $('noxV22Gov'); if (g && st) g.textContent = 'Графика: ' + (st.reason || st.tier || 'авто');
  }
  addEventListener('nox-core-gov', governor);
  addEventListener('nox-stop-requested', () => { body.dataset.noxFx = 'stop'; });

  window.NOX_CHAT_V24 = Object.freeze({ send, stop, openMemory, state: () => ({ dialog: state.dialog, active: Boolean(state.active), model: state.status?.model || null, phase: body.dataset.noxPhase, address: state.address }) });

  (async () => {
    try { const s = await getJSON('/api/settings'); state.address = s.settings?.address || 'auto'; } catch { }
    document.querySelectorAll('[data-address]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.address === state.address)));
    try { if (localStorage.getItem(LS_RAIL) === '1' || matchMedia('(max-width:720px)').matches) setRail(true); } catch { }
    await refreshStatus(); refreshReceipt(); refreshMemory(); refreshMetrics(); refreshLiveBoard();
    const list = await refreshDialogs();
    let id = null; try { id = localStorage.getItem(LS) || null; } catch { }
    if (id && isArchived(id)) id = (list.find(d => !isArchived(d.id)) || {}).id || null;
    if (!id || !list.some(d => d.id === id)) id = (list.find(d => !isArchived(d.id)) || list[0] || {}).id || null;
    await loadDialog(id);
    governor(); clock(); wx(); refreshMood(); whisperReminders();
    setInterval(clock, 15000); setInterval(wx, 15 * 60000); setInterval(governor, 3000); setInterval(refreshMood, 4000);
    setInterval(refreshMetrics, 5000); setInterval(refreshStatus, 15000); setInterval(refreshReceipt, 30000); setInterval(refreshLiveBoard, 4000);
    window.lucide?.createIcons?.();
    body.dataset.v24Ready = 'true';
  })();
})();
