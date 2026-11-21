/* NOX NEWCHAT: «Новый чат (GLM-5.3)» — клиент шлюза NOX (OpenAI-совместимый POST /v1/chat/completions, профиль G01–G33).
   Отдельная панель рядом со старым чатом; старый чат не меняется. Никаких заглушек: нет шлюза — честная ошибка и кнопка возврата.
   Хранилище: localStorage (всё в try/catch). Размышления показываются свёрнутым блоком и в историю запроса НЕ попадают. */
(function () {
  'use strict';
  if (window.NoxNewChat) return;
  var K_MODE = 'nox.chat.mode', K_CFG = 'nox.newchat.cfg', K_HIST = 'nox.newchat.v1', K_JUDGE = 'nox.judges.on';
  var DEFAULT_API = '/glm/v1/chat/completions';
  var DEPTHS = [['auto', 'Авто'], ['low', 'Low'], ['high', 'High'], ['max', 'Max']];
  var mem = {};
  function lsGet(k, d) { try { var v = localStorage.getItem(k); return v == null ? (k in mem ? mem[k] : d) : v; } catch (e) { return k in mem ? mem[k] : d; } }
  function lsSet(k, v) { mem[k] = v; try { localStorage.setItem(k, v); return true; } catch (e) { return false; } }
  function jget(k, d) { try { var v = JSON.parse(lsGet(k, 'null')); return v == null ? d : v; } catch (e) { return d; } }

  var cfg = Object.assign({ api: DEFAULT_API, depth: 'auto', stream: true, noRetry: false, facts: '', mode: 'auto' }, jget(K_CFG, {}));
  if (typeof window.NOX_GLM_API === 'string' && window.NOX_GLM_API) cfg.api = window.NOX_GLM_API;
  var st = { mode: lsGet(K_MODE, 'old') === 'new' ? 'new' : 'old', msgs: [], busy: false, ctrl: null, gw: 'unknown', gwWhy: '', failed: null };
  var raw = jget(K_HIST, null);
  if (raw && Array.isArray(raw.msgs)) st.msgs = raw.msgs.filter(function (m) { return m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string'; }).slice(-60);

  var BAN = [
    [/(?<![\p{L}\p{N}_])не\s+[^,.;\n]{1,40},\s*а\s+[^,.;\n]{1,40}/iu, 'not_x_but_y'],
    [/(?<![\p{L}\p{N}_])я\s*[—-]?\s*claude(?![\p{L}\p{N}_])|(?<![\p{L}\p{N}_])claude(?![\p{L}\p{N}_])/iu, 'names_self_claude'],
    [/^(отличный|прекрасный|замечательный|великолепный)\s+(вопрос|идея|мысль)/imu, 'flattery_opener'],
    [/(?<![\p{L}\p{N}_])(вы абсолютно правы|совершенно верно, вы правы)(?![\p{L}\p{N}_])/iu, 'sycophancy']
  ];
  var VLABEL = { not_x_but_y: 'оборот «не X, а Y»', names_self_claude: 'самоназвание Claude', flattery_opener: 'лесть в начале', sycophancy: 'поддакивание' };
  function clientViolations(t) { var o = []; BAN.forEach(function (p) { if (p[0].test(t || '')) o.push(p[1]); }); return o; }

  function $(s, r) { return (r || document).querySelector(s); }
  function tidy(s){return String(s==null?'':s).replace(/[ \t]+\n/g,'\n').replace(/\n{2,}/g,'\n').trim();}
  function el(tag, cls, text, attrs) {
    var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text;
    if (attrs) for (var k in attrs) n.setAttribute(k, attrs[k]); return n;
  }
  function splitThink(rawText) {
    var think = '', ans = rawText, i = rawText.indexOf('<think>');
    if (i >= 0) {
      var j = rawText.indexOf('</think>', i);
      if (j < 0) { think = rawText.slice(i + 7); ans = rawText.slice(0, i); }
      else { think = rawText.slice(i + 7, j); ans = rawText.slice(0, i) + rawText.slice(j + 8); }
    } else { var e = rawText.indexOf('</think>'); if (e >= 0) { think = rawText.slice(0, e); ans = rawText.slice(e + 8); } }
    return { think: think.trim(), ans: ans.replace(/^\s+/, '') };
  }
  function modelsUrl() { return String(cfg.api).replace(/\/chat\/completions\/?$/, '/models'); }
  function validApi(u) { return /^(\/(?!\/)[^\s]*|https?:\/\/[^\s]+)$/.test(u); }

  /* ---------- DOM ---------- */
  var D = {};
  function build() {
    var sec = $('.chat-conversation'), board = document.getElementById('messages'), form = document.getElementById('chatForm');
    if (!sec || !board) return false;
    var bar = el('div', null, null, { id: 'nxcBar', role: 'group', 'aria-label': 'Режим чата' });
    var seg = el('div', 'nxc-seg');
    var bOld = el('button', null, 'Старый чат', { type: 'button', id: 'nxcOld', 'data-mode': 'old' });
    var bNew = el('button', null, 'Новый чат (GLM-5.3)', { type: 'button', id: 'nxcNew', 'data-mode': 'new' });
    seg.append(bOld, bNew);
    var depth = el('div', 'nxc-depth', null, { role: 'group', 'aria-label': 'Глубина размышления' });
    DEPTHS.forEach(function (d) { depth.append(el('button', null, d[1], { type: 'button', 'data-depth': d[0], 'aria-pressed': 'false' })); });
    var stat = el('span', 'nxc-stat', 'шлюз: не проверен', { id: 'nxcStat', role: 'status', 'data-state': 'unknown' });
    var gear = el('button', 'nxc-gear', 'Настройки', { type: 'button', id: 'nxcGear', 'aria-expanded': 'false', 'aria-controls': 'nxcSet' });
    bar.append(seg, depth, stat, gear);
    var set = el('div', null, null, { id: 'nxcSet', hidden: '' });
    set.innerHTML = '<label>API шлюза (POST /v1/chat/completions)<input id="nxcApi" type="text" autocomplete="off" spellcheck="false"></label>' +
      '<label>Режим шлюза (nox_mode; Авто — решает роутер шлюза)<select id="nxcMode"><option value="auto">Авто</option><option value="fast">fast — быстрая модель</option><option value="deep">deep — быстрый такт + GLM high</option><option value="max">max — быстрый такт + GLM max</option></select></label>' +
      '<label class="nxc-chk"><input id="nxcStream" type="checkbox"> Потоковый вывод (SSE)</label>' +
      '<label class="nxc-chk"><input id="nxcNoRetry" type="checkbox"> Без автоповтора при нарушениях (nox_no_retry)</label>' +
      '<label>Факты для контекста (nox_facts, по одному в строке)<textarea id="nxcFacts" rows="3" spellcheck="false"></textarea></label>' +
      '<div class="nxc-row"><button type="button" id="nxcSave">Сохранить и проверить</button><button type="button" id="nxcReset">По умолчанию</button><button type="button" id="nxcClear">Очистить историю нового чата</button></div><p class="nxc-msgline" id="nxcSetMsg" role="status"></p>';
    var pane = el('section', null, null, { id: 'nxcPane', hidden: '', 'aria-label': 'Новый чат GLM-5.3' });
    var gwb = el('div', null, null, { id: 'nxcGw', role: 'alert', hidden: '' });
    var list = el('div', null, null, { id: 'nxcList', role: 'log', 'aria-live': 'polite', 'data-qa': 'newchat-messages' });
    var f = el('form', null, null, { id: 'nxcForm' });
    var ta = el('textarea', null, null, { id: 'nxcInput', rows: '1', maxlength: '10000', placeholder: 'Сообщение NOX (GLM-5.3)…', 'aria-label': 'Сообщение для нового чата' });
    var stop = el('button', null, 'STOP', { type: 'button', id: 'nxcStop', disabled: '' });
    var send = el('button', null, 'Отправить', { type: 'submit', id: 'nxcSend' });
    f.append(ta, stop, send);
    pane.append(gwb, list, f);
    sec.insertBefore(set, board); sec.insertBefore(bar, set); sec.insertBefore(pane, board);
    D = { bar: bar, bOld: bOld, bNew: bNew, depth: depth, stat: stat, gear: gear, set: set, pane: pane, gw: gwb, list: list, form: f, ta: ta, stop: stop, send: send, board: board, oldForm: form };
    return true;
  }

  function applyMode(focus) {
    var on = st.mode === 'new';
    document.documentElement.classList.toggle('nxc-on', on);
    D.pane.hidden = !on; D.depth.hidden = !on; D.stat.hidden = !on; D.gear.hidden = !on;
    if (!on) { D.set.hidden = true; D.gear.setAttribute('aria-expanded', 'false'); }
    D.bOld.setAttribute('aria-pressed', String(!on)); D.bNew.setAttribute('aria-pressed', String(on));
    [].forEach.call(D.depth.children, function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-depth') === cfg.depth)); });
    if (on) { renderAll(); probe(); if (focus) D.ta.focus(); }
    else if (focus) { var p = document.getElementById('prompt') || document.querySelector('#chatForm textarea'); if (p) p.focus(); }
    try { window.dispatchEvent(new CustomEvent('nox-chat-mode', { detail: { mode: st.mode } })); } catch (e) { }
  }
  function setMode(m, focus) {
    if (st.busy && m === 'old') abort();
    st.mode = m === 'new' ? 'new' : 'old'; lsSet(K_MODE, st.mode); applyMode(focus);
  }

  /* ---------- шлюз ---------- */
  function setGw(state, why) {
    st.gw = state; st.gwWhy = why || '';
    D.stat.setAttribute('data-state', state);
    D.stat.textContent = state === 'ok' ? 'шлюз: онлайн' : state === 'down' ? 'шлюз недоступен' : state === 'checking' ? 'шлюз: проверка…' : 'шлюз: не проверен';
    D.stat.title = why || '';
    showGwBanner(state === 'down' ? why : '');
  }
  function showGwBanner(why) {
    D.gw.replaceChildren();
    if (!why) { D.gw.hidden = true; return; }
    var t = el('div', 'nxc-gwt'); t.append(el('b', null, 'Шлюз недоступен. '), document.createTextNode(why + ' Ответы не подменяются: новый чат работает только через шлюз GLM-5.3.'));
    var acts = el('div', 'nxc-row');
    var b1 = el('button', null, 'Вернуться на старый чат', { type: 'button', id: 'nxcBack' });
    var b2 = el('button', null, 'Проверить снова', { type: 'button', id: 'nxcRecheck' });
    b1.onclick = function () { setMode('old', true); };
    b2.onclick = function () { probe(); };
    acts.append(b1, b2); D.gw.append(t, acts); D.gw.hidden = false;
  }
  function whyOf(e) {
    if (e && e.nox === 'http') return e.message;
    if (e && e.name === 'AbortError') return 'Превышено время ожидания.';
    return 'Нет соединения с ' + cfg.api + ' (' + ((e && e.message) || e) + ').';
  }
  async function probe() {
    if (st.mode !== 'new') return;
    setGw('checking', '');
    var c = new AbortController(), t = setTimeout(function () { c.abort(); }, 4000);
    try {
      var r = await fetch(modelsUrl(), { cache: 'no-store', signal: c.signal });
      var ct = (r.headers.get('content-type') || '').toLowerCase();
      if (!r.ok || ct.indexOf('json') < 0) throw Object.assign(new Error('HTTP ' + r.status + (ct.indexOf('json') < 0 ? ', ответ не от шлюза' : '') + '.'), { nox: 'http' });
      setGw('ok', 'Ответ ' + modelsUrl());
    } catch (e) { setGw('down', whyOf(e)); }
    finally { clearTimeout(t); }
  }

  /* ---------- рендер ---------- */
  function msgNode(m) {
    var n = el('article', 'nxc-msg ' + (m.role === 'user' ? 'u' : 'a'));
    n.append(el('div', 'nxc-role', m.role === 'user' ? 'Вы' : 'NOX · GLM-5.3'));
    if (m.role === 'assistant') {
      var head = n.lastChild;
      var bd = el('span', 'nxc-badge', m.effort ? 'effort: ' + m.effort : 'effort: —', { 'data-effort': m.effort || '' }); head.append(' ', bd);
      var th = el('details', 'nxc-think'); th.append(el('summary', null, 'Размышления'), el('div', 'nxc-thinkbody', m.think || ''));
      if (!m.think) th.hidden = true; n.append(th);
    }
    n.append(el('div', 'nxc-text', tidy(m.content)));
    if (m.role === 'assistant') n.append(el('div', 'nxc-meta'), el('div', 'nxc-warns'), el('div', 'nxc-judges'));
    n._parts = { badge: n.querySelector('.nxc-badge'), think: n.querySelector('.nxc-think'), thinkBody: n.querySelector('.nxc-thinkbody'), text: n.querySelector('.nxc-text'), warns: n.querySelector('.nxc-warns'), meta: n.querySelector('.nxc-meta'), judges: n.querySelector('.nxc-judges') };
    if (m.role === 'assistant') { paintWarns(n, m); paintMeta(n, m); }
    return n;
  }
  function paintMeta(n, m) {
    var bits = []; if (m.tier) bits.push('tier: ' + m.tier); if (m.mode) bits.push('режим: ' + m.mode); if (m.actual) bits.push(m.actual + ' с');
    n._parts.meta.textContent = bits.join(' · '); n._parts.meta.hidden = !bits.length;
  }
  function paintWarns(n, m) {
    var w = n._parts.warns; w.replaceChildren();
    (m.violations || []).forEach(function (v) { w.append(el('span', 'nxc-warn', 'Нарушение стиля: ' + (VLABEL[v] || v), { 'data-v': v, title: m.vsrc === 'client' ? 'Проверено в браузере: потоковый ответ не проходит серверную проверку' : 'Проверка шлюза NOX' })); });
    if (m.retried && m.retried.length) w.append(el('span', 'nxc-note', 'Шлюз переписал ответ (повтор из-за: ' + m.retried.map(function (v) { return VLABEL[v] || v; }).join(', ') + ')', { 'data-q': 'retried' }));
    if (m.lenBad) w.append(el('span', 'nxc-warn', 'Длина: просили ' + m.lenBad.want + ', получено ' + m.lenBad.got, { 'data-v': 'length' }));
    if (m.stopped) w.append(el('span', 'nxc-note', 'Остановлено пользователем'));
    if (m.err) w.append(el('span', 'nxc-warn', 'Поток прерван: ' + m.err, { 'data-v': 'stream_error' }));
  }
  function renderAll() {
    D.list.replaceChildren();
    if (!st.msgs.length) D.list.append(el('p', 'nxc-empty', 'Новый чат на GLM-5.3 через шлюз NOX. Напишите сообщение; глубина размышления выбирается выше (Авто, Low, High, Max).'));
    st.msgs.forEach(function (m) { D.list.append(msgNode(m)); });
    toBottom(true);
  }
  var pinned = true;
  function toBottom(force) { if (force || pinned) D.list.scrollTop = D.list.scrollHeight; }
  function persist() { lsSet(K_HIST, JSON.stringify({ msgs: st.msgs.slice(-60).map(function (m) { var o = { role: m.role, content: m.content }; if (m.role === 'assistant') { if (m.think) o.think = m.think; if (m.effort) o.effort = m.effort; if (m.violations && m.violations.length) o.violations = m.violations; if (m.vsrc) o.vsrc = m.vsrc; if (m.retried) o.retried = m.retried; if (m.stopped) o.stopped = 1; if (m.tier) o.tier = m.tier; if (m.mode) o.mode = m.mode; if (m.actual) o.actual = m.actual; if (m.err) o.err = m.err; } return o; }) })); }
  function busy(b) { st.busy = b; D.send.disabled = b; D.stop.disabled = !b; D.pane.setAttribute('aria-busy', String(b)); try { window.dispatchEvent(new CustomEvent('nox-chat-activity', { detail: { active: b, newchat: true } })); } catch (e) { } }
  function abort() {
    if (!st.ctrl) return; var rid = st.rid; try { st.ctrl.abort(); } catch (e) { }
    if (rid) { try { fetch(String(cfg.api).replace(/\/chat\/completions\/?$/, '/stop'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: rid }) }).catch(function () { }); } catch (e) { } }
  }

  /* ---------- отправка ---------- */
  function buildBody(history, text) {
    var body = { model: 'glm-5.3', messages: history.concat([{ role: 'user', content: text }]), stream: !!cfg.stream };
    if (cfg.depth !== 'auto') body.reasoning_effort = cfg.depth;
    var facts = String(cfg.facts || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
    if (facts.length) body.nox_facts = facts;
    if (cfg.noRetry) body.nox_no_retry = true;
    if (cfg.mode && cfg.mode !== 'auto') body.nox_mode = cfg.mode;
    return body;
  }
  function histForRequest() { // только role+content, без размышлений и служебных полей; сбойные реплики не включаем
    return st.msgs.slice(-40).map(function (m) { return { role: m.role, content: splitThink(m.content).ans }; }).filter(function (m) { return m.content; });
  }
  async function httpError(r) {
    var msg = 'Шлюз ответил HTTP ' + r.status;
    try { var t = await r.text(); try { var j = JSON.parse(t); if (j && (j.error || j.message)) msg += ': ' + (typeof j.error === 'string' ? j.error : JSON.stringify(j.error || j.message)); } catch (e) { if (t && t.length < 160 && t.indexOf('<') < 0) msg += ': ' + t; } } catch (e) { }
    return Object.assign(new Error(msg + '.'), { nox: 'http' });
  }
  async function send(text) {
    text = String(text == null ? D.ta.value : text).trim();
    if (st.busy || !text) return;
    if (!validApi(cfg.api)) { setGw('down', 'Некорректный адрес API: ' + cfg.api + '.'); return; }
    var empty = D.list.querySelector('.nxc-empty'); if (empty) empty.remove();
    D.list.querySelectorAll('.nxc-fail').forEach(function (x) { x.remove(); });
    var body = buildBody(histForRequest(), text);
    var um = { role: 'user', content: text }, am = { role: 'assistant', content: '', think: '', effort: '' };
    D.list.append(msgNode(um)); var an = msgNode(am); D.list.append(an); pinned = true; toBottom(true);
    D.ta.value = ''; autosize(); busy(true);
    var ctrl = new AbortController(); st.ctrl = ctrl; var ok = false;
    try {
      var r = await fetch(cfg.api, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': cfg.stream ? 'text/event-stream' : 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal });
      if (!r.ok) throw await httpError(r);
      var ct = (r.headers.get('content-type') || '').toLowerCase();
      if (ct.indexOf('json') < 0 && ct.indexOf('event-stream') < 0) throw Object.assign(new Error('Ответ не похож на ответ шлюза (' + (ct || 'без Content-Type') + ').'), { nox: 'http' });
      am.effort = r.headers.get('X-NOX-Effort') || ''; am.mode = r.headers.get('X-NOX-Mode') || ''; am.rid = r.headers.get('X-NOX-Request-Id') || ''; st.rid = am.rid;
      if (cfg.stream && ct.indexOf('event-stream') >= 0) await readStream(r, am, an);
      else await readJson(r, am);
      ok = true;
    } catch (e) {
      if (e && e.name === 'AbortError' && st.ctrl === ctrl && am.content) { am.stopped = true; ok = true; }
      else if (e && e.name === 'AbortError') { an.remove(); showFail(um, text, '', false, true); }
      else { an.remove(); showFail(um, text, whyOf(e), true); setGw('down', whyOf(e)); }
    }
    if (ok) {
      var sp = splitThink(am.content); am.content = sp.ans || am.content; if (sp.think) am.think = (am.think ? am.think + '\n' : '') + sp.think;
      if (!am.content.trim() && am.skipped) { an.remove(); var sk = el('div', 'nxc-fail nxc-skip', 'Шлюз не стал отвечать: роутер счёл сообщение не требующим ответа (skipped_model). Сообщение не сохранено в историю.', { role: 'status' }); D.list.append(sk); toBottom(true); }
      else if (!am.content.trim()) { an.remove(); showFail(um, text, 'Шлюз вернул пустой ответ.', true); }
      else {
        if (!am.violations) { am.violations = clientViolations(am.content); am.vsrc = 'client'; }
        paintNode(an, am); st.msgs.push(um, am); persist(); setGw('ok', st.gwWhy);
        runJudges(text, am.content, an);
      }
    }
    st.ctrl = null; st.rid = ''; busy(false);
  }
  function paintNode(an, am) {
    var p = an._parts; p.text.textContent = tidy(am.content); p.badge.textContent = 'effort: ' + (am.effort || '—'); p.badge.setAttribute('data-effort', am.effort || '');
    if (am.think) { p.think.hidden = false; p.thinkBody.textContent = am.think; } else p.think.hidden = true;
    paintWarns(an, am); paintMeta(an, am); toBottom();
  }
  function showFail(um, text, why, offerBack, stopped) {
    var f = el('div', 'nxc-fail', null, { role: 'alert' });
    f.append(el('div', 'nxc-failtxt', stopped ? 'Остановлено до первого ответа.' : 'Не удалось получить ответ. ' + why + ' Подмены ответа нет.'));
    var row = el('div', 'nxc-row');
    var r1 = el('button', null, 'Повторить', { type: 'button', 'data-q': 'retry' }); r1.onclick = function () { var u = f.previousElementSibling; f.remove(); if (u && u.classList.contains('u')) u.remove(); send(text); };
    row.append(r1);
    if (offerBack) { var r2 = el('button', null, 'Вернуться на старый чат', { type: 'button', 'data-q': 'back' }); r2.onclick = function () { var op = document.getElementById('prompt') || document.querySelector('#chatForm textarea'); if (op && !op.value) op.value = text; setMode('old', true); }; row.append(r2); }
    f.append(row); D.list.append(f); toBottom(true);
  }
  async function readJson(r, am) {
    var j = await r.json();
    var ch = j && j.choices && j.choices[0], msg = ch && ch.message;
    if (!msg) throw Object.assign(new Error('В ответе шлюза нет choices[0].message.'), { nox: 'http' });
    var c = msg.content || '', sp = splitThink(c);
    am.content = sp.ans; am.think = [msg.reasoning_content || msg.reasoning || '', sp.think].filter(Boolean).join('\n');
    var nx = j.nox || {};
    am.effort = nx.effort || am.effort;
    if (nx.memory_text) am.content = nx.memory_text;
    am.violations = Array.isArray(nx.violations) ? nx.violations : clientViolations(am.content); am.vsrc = Array.isArray(nx.violations) ? 'server' : 'client';
    am.retried = nx.retried_for || null; am.tier = nx.tier || am.tier || ''; am.mode = nx.mode || am.mode || ''; if (nx.actual_s) am.actual = nx.actual_s; am.skipped = !!nx.skipped_model; am.rid = nx.request_id || am.rid;
    if (nx.length && nx.length.ok === false) am.lenBad = nx.length;
  }
  async function readStream(r, am, an) {
    var rd = r.body.getReader(), dec = new TextDecoder(), buf = '', rawc = '', rs = '', dirty = false, done = false;
    function paint() { dirty = false; var sp = splitThink(rawc); an._parts.text.textContent = tidy(sp.ans); var th = [rs, sp.think].filter(Boolean).join('\n'); if (th) { an._parts.think.hidden = false; an._parts.thinkBody.textContent = th; } an._parts.badge.textContent = 'effort: ' + (am.effort || '—'); paintMeta(an, am); if (!an._parts.text.textContent && !th) an._parts.text.textContent = '…'; toBottom(); }
    var sched = function () { if (!dirty) { dirty = true; requestAnimationFrame(paint); } };
    try {
    while (!done) {
      var c = await rd.read(); if (c.done) break;
      buf += dec.decode(c.value, { stream: true });
      var p; while ((p = buf.indexOf('\n')) !== -1) {
        var line = buf.slice(0, p).trim(); buf = buf.slice(p + 1);
        if (line.indexOf('data:') !== 0) continue; var d = line.slice(5).trim(); if (d === '[DONE]') { done = true; break; }
        var j; try { j = JSON.parse(d); } catch (e) { continue; }
        if (j.error) { var em = typeof j.error === 'string' ? j.error : (j.error.message || JSON.stringify(j.error)); if (rawc || rs) { am.err = em; continue; } throw Object.assign(new Error(em), { nox: 'http' }); }
        if (j.nox) { var nx = j.nox; if (nx.effort) { am.effort = nx.effort; } if (nx.tier) am.tier = nx.tier; if (nx.mode) am.mode = nx.mode; if (nx.actual_s) am.actual = nx.actual_s; if (nx.request_id) am.rid = nx.request_id; if (nx.skipped_model) am.skipped = true; if (nx.error && !am.err && (rawc || rs)) am.err = nx.error; }
        var dl = j.choices && j.choices[0] && j.choices[0].delta; if (!dl) continue;
        if (dl.reasoning_content) rs += dl.reasoning_content; else if (dl.reasoning) rs += dl.reasoning;
        if (dl.content) rawc += dl.content; sched();
      }
    }
    } catch (e) { var ps = splitThink(rawc); am.content = ps.ans; am.think = [rs, ps.think].filter(Boolean).join('\n'); throw e; }
    try { await rd.cancel(); } catch (e) { }
    paint(); var sp = splitThink(rawc); am.content = sp.ans; am.think = [rs, sp.think].filter(Boolean).join('\n');
    if (!rawc && !rs) throw Object.assign(new Error('Поток закончился без данных.'), { nox: 'http' });
  }

  /* ---------- режим судей (через тот же шлюз; старый /api/chat не используется) ---------- */
  function judgesOn() { var b = document.getElementById('noxJudgeSw'); if (b) return b.getAttribute('aria-pressed') === 'true'; return lsGet(K_JUDGE, '0') === '1'; }
  async function ask(prompt, sys) {
    var r = await fetch(cfg.api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'glm-5.3', stream: false, reasoning_effort: 'low', nox_no_retry: true, messages: [{ role: 'system', content: sys }, { role: 'user', content: prompt }] }) });
    if (!r.ok) throw Error('шлюз ответил ' + r.status);
    var j = await r.json(); var m = j.choices && j.choices[0] && j.choices[0].message; return splitThink((m && m.content) || '').ans;
  }
  async function runJudges(q, a, an) {
    if (!judgesOn() || a.length < 40) return;
    var box = an._parts.judges, n = el('div', 'nox-judge nxc-judge', null, { 'data-q': 'judge' }); n.append(el('b', null, 'Судьи'), document.createTextNode(' проверяют…')); box.append(n);
    try {
      var v = await ask('ВОПРОС:\n' + q + '\n\nОТВЕТ:\n' + a + '\n\nТри судьи: 1) факты, 2) логика, 3) полнота. По каждому одной строкой: OK или замечание. Затем строка ИТОГ: OK или ИСПРАВИТЬ.', 'Ты строгая коллегия судей. Не переписывай ответ, только оценивай кратко.');
      n.replaceChildren();
      if (/ИТОГ:\s*OK/i.test(v) || !/ИСПРАВИТЬ/i.test(v)) { n.append(el('b', null, 'Судьи:'), document.createTextNode(' замечаний нет ✓')); n.setAttribute('data-verdict', 'ok'); return; }
      n.setAttribute('data-verdict', 'fix'); n.append(el('b', null, 'Судьи: '), document.createTextNode(v.slice(0, 700)));
      var btn = el('button', null, 'Показать исправленный ответ', { type: 'button' }); n.append(btn);
      btn.onclick = async function () {
        btn.disabled = true; btn.textContent = 'Исправляю…';
        try { var fx = await ask('ВОПРОС:\n' + q + '\n\nЧЕРНОВИК:\n' + a + '\n\nЗАМЕЧАНИЯ СУДЕЙ:\n' + v + '\n\nДай исправленный итоговый ответ.', 'Ты NOX. Исправь ответ по замечаниям, без вводных слов.'); var d = el('div', 'nox-judge nxc-judge', fx); n.after(d); btn.remove(); } catch (e) { btn.disabled = false; btn.textContent = 'Повторить исправление'; }
      };
    } catch (e) { n.replaceChildren(el('b', null, 'Судьи:'), document.createTextNode(' недоступны (' + (e.message || e) + ')')); n.setAttribute('data-verdict', 'error'); }
  }

  /* ---------- UI-события ---------- */
  function autosize() { D.ta.style.height = 'auto'; D.ta.style.height = Math.min(D.ta.scrollHeight, 180) + 'px'; }
  function saveCfg() { lsSet(K_CFG, JSON.stringify({ api: cfg.api, depth: cfg.depth, stream: cfg.stream, noRetry: cfg.noRetry, facts: cfg.facts, mode: cfg.mode })); }
  function bind() {
    D.bOld.onclick = function () { setMode('old', true); };
    D.bNew.onclick = function () { setMode('new', true); };
    D.seg = D.bOld.parentNode;
    D.seg.addEventListener('keydown', function (e) { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); var t = e.key === 'ArrowRight' ? D.bNew : D.bOld; t.focus(); setMode(t.getAttribute('data-mode')); t.focus(); } });
    D.depth.addEventListener('click', function (e) { var b = e.target.closest('[data-depth]'); if (!b) return; cfg.depth = b.getAttribute('data-depth'); saveCfg(); [].forEach.call(D.depth.children, function (x) { x.setAttribute('aria-pressed', String(x === b)); }); });
    D.gear.onclick = function () { var o = D.set.hidden; D.set.hidden = !o; D.gear.setAttribute('aria-expanded', String(o)); if (o) { $('#nxcApi').value = cfg.api; $('#nxcStream').checked = cfg.stream; $('#nxcMode').value = cfg.mode; $('#nxcNoRetry').checked = cfg.noRetry; $('#nxcFacts').value = cfg.facts; $('#nxcApi').focus(); } };
    $('#nxcSave').onclick = function () {
      var u = $('#nxcApi').value.trim(), m = $('#nxcSetMsg');
      if (!validApi(u)) { m.textContent = 'Адрес должен начинаться с / или http(s)://'; return; }
      cfg.api = u; cfg.stream = $('#nxcStream').checked; cfg.mode = $('#nxcMode').value; cfg.noRetry = $('#nxcNoRetry').checked; cfg.facts = $('#nxcFacts').value; saveCfg(); m.textContent = 'Сохранено.'; probe();
    };
    $('#nxcReset').onclick = function () { cfg.api = DEFAULT_API; $('#nxcApi').value = DEFAULT_API; };
    $('#nxcClear').onclick = function () { if (st.busy) return; st.msgs = []; persist(); renderAll(); $('#nxcSetMsg').textContent = 'История очищена.'; };
    D.form.addEventListener('submit', function (e) { e.preventDefault(); send(); });
    D.stop.onclick = abort;
    D.ta.addEventListener('input', autosize);
    D.ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
    D.pane.addEventListener('keydown', function (e) { if (e.key === 'Escape' && st.busy) { e.preventDefault(); abort(); } });
    D.list.addEventListener('scroll', function () { pinned = D.list.scrollHeight - D.list.scrollTop - D.list.clientHeight < 60; });
  }
  function init() {
    if (!build()) return;
    bind(); applyMode(false);
    window.NoxNewChat = { mode: function () { return st.mode; }, setMode: setMode, state: st, cfg: cfg, probe: probe, send: send };
  }
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
