/* NOX roles-x2 (WEB): (1) память роли для всех студий через /api/notes (rolemem-<роль>-NNN, localStorage = кэш; та же схема, что у Писателя), подмешивается в system чата роли;
   (2) Учёный: поиск источников OpenAlex / Semantic Scholar / Crossref / Wikipedia (прямо из браузера, CORS) и arXiv (через мост /api/sci/arxiv), без ключей;
   (3) Музыка/Видео: генерация HOLD со ссылками на найденные варианты. Откат: ?rx2=0 */
(function () {
  'use strict';
  if (/[?&]rx2=0/.test(location.search)) return;
  var rid = new URLSearchParams(location.search).get('role') || 'writer';
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  var css = document.createElement('style');
  css.textContent = '#rx2{border-top:1px solid var(--gx-5,#2a2c30);padding:12px 14px;display:flex;flex-direction:column;gap:12px}#rx2 .rx2-r{display:flex;gap:8px;flex-wrap:wrap;align-items:center}#rx2 .rx2-t{min-height:44px;padding:0 14px;border-radius:10px;border:1px solid var(--gx-6,#363a3f);background:var(--gx-3,#212225);color:var(--gx-12,#edeef0);font:600 14px var(--sans,system-ui);cursor:pointer}#rx2 .rx2-t[aria-pressed=true]{border-color:var(--gx-acc,#9db1d1);background:color-mix(in srgb,var(--gx-acc,#9db1d1) 16%,var(--gx-3,#212225))}#rx2 .rx2-st{font-size:13px;color:var(--gx-11,#b0b4ba);margin:0}#rx2 sl-card{--padding:12px}#rx2 sl-card a{color:var(--gx-acc,#9db1d1)}#rx2 .rx2-m{font-size:13px;color:var(--gx-11,#b0b4ba);margin:4px 0 8px}#rx2 sl-details::part(base){background:var(--gx-2,#18191b)}';
  document.head.appendChild(css);

  /* ---------- память роли ---------- */
  var KEY = 'nox.rm.' + rid, ID = 'rolemem-' + rid + '-', CH = 3500, Q = Promise.resolve(), pt = 0, mem = { ts: 0, text: '' };
  try { var c = JSON.parse(localStorage.getItem(KEY) || 'null'); if (c && typeof c.text === 'string') mem = c; } catch (e) {}
  function seq(f) { var g = function () { return navigator.locks ? navigator.locks.request('nox-notes', f) : f(); }; Q = Q.then(g, g); return Q; }
  function jget() { return fetch('/api/notes', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
  function stat(t) { var e = document.getElementById('rx2-ms'); if (e) e.textContent = t; }
  async function push0() {
    try {
      var j = await jget(); if (!j) { stat('только в браузере'); return; }
      var list = (j.notes || []).filter(function (n) { return !(n && String(n.id).indexOf(ID) === 0); }), txt = JSON.stringify(mem), n = 0;
      for (var i = 0; i < txt.length; i += CH) list.push({ id: ID + ('000' + (n++)).slice(-3), text: txt.slice(i, i + CH), ts: mem.ts / 1000 });
      var r = await fetch('/api/notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ notes: list }) });
      stat(r.ok ? 'синхронизировано' : 'только в браузере');
    } catch (e) { stat('только в браузере'); }
  }
  function saveMem(t) { mem = { ts: Date.now(), text: t }; try { localStorage.setItem(KEY, JSON.stringify(mem)); } catch (e) {} clearTimeout(pt); pt = setTimeout(function () { seq(push0); }, 1800); stat('сохраняю…'); }
  async function pull() {
    var j = await jget(); if (!j) return false;
    var p = (j.notes || []).filter(function (n) { return n && String(n.id).indexOf(ID) === 0; }).sort(function (a, b) { return a.id < b.id ? -1 : 1; }); if (!p.length) return false;
    try { var o = JSON.parse(p.map(function (n) { return n.text; }).join('')); if (o && typeof o.text === 'string' && (o.ts || 0) > (mem.ts || 0)) { mem = o; try { localStorage.setItem(KEY, JSON.stringify(mem)); } catch (e) {} return true; } } catch (e) {}
    return false;
  }
  window.NOXroleMem = { get: function () { return mem.text; }, role: rid };
  /* подмешать память в system чата роли (/api/chat, conversation_id = role-<роль>) */
  var of = window.fetch;
  window.fetch = function (u, o) {
    try {
      if (String(u).indexOf('/api/chat') === 0 && mem.text.trim() && o && typeof o.body === 'string') {
        var b = JSON.parse(o.body);
        if (b && b.conversation_id === 'role-' + rid && Array.isArray(b.messages) && b.messages[0] && b.messages[0].role === 'system') {
          b.messages[0].content += '\n\nПамять этой роли (факты и договорённости владельца, учитывай их):\n' + mem.text.slice(0, 4000);
          o = Object.assign({}, o, { body: JSON.stringify(b) });
        }
      }
    } catch (e) {}
    return of.call(this, u, o);
  };

  /* ---------- Учёный: источники ---------- */
  var SRC = [['openalex', 'OpenAlex'], ['semantic', 'Semantic Scholar'], ['crossref', 'Crossref'], ['arxiv', 'arXiv'], ['wiki', 'Википедия']];
  var JS = function (u) { return fetch(u, { headers: { Accept: 'application/json' } }).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }); };
  var authors = function (a) { return (a || []).slice(0, 6).join(', '); };
  var FIND = {
    openalex: function (q) { return JS('https://api.openalex.org/works?per-page=8&search=' + encodeURIComponent(q) + '&select=id,title,doi,publication_year,authorships,primary_location').then(function (j) { return (j.results || []).map(function (w) { return { title: w.title, url: w.doi || w.id, year: w.publication_year, authors: (w.authorships || []).map(function (a) { return a.author && a.author.display_name; }).filter(Boolean), venue: w.primary_location && w.primary_location.source && w.primary_location.source.display_name }; }); }); },
    semantic: function (q) { return JS('/api/sci/semantic?q=' + encodeURIComponent(q)).then(function (j) { return (j.data || []).map(function (w) { return { title: w.title, url: (w.externalIds && w.externalIds.DOI) ? 'https://doi.org/' + w.externalIds.DOI : w.url, year: w.year, authors: (w.authors || []).map(function (a) { return a.name; }), venue: w.venue }; }); }); },
    crossref: function (q) { return JS('https://api.crossref.org/works?rows=8&select=DOI,title,author,issued,container-title,URL&query=' + encodeURIComponent(q)).then(function (j) { return ((j.message && j.message.items) || []).map(function (w) { return { title: (w.title || [])[0], url: w.DOI ? 'https://doi.org/' + w.DOI : w.URL, year: w.issued && w.issued['date-parts'] && w.issued['date-parts'][0] && w.issued['date-parts'][0][0], authors: (w.author || []).map(function (a) { return [a.given, a.family].filter(Boolean).join(' '); }), venue: (w['container-title'] || [])[0] }; }); }); },
    arxiv: function (q) { return JS('/api/sci/arxiv?q=' + encodeURIComponent(q)).then(function (j) { if (j.hold) throw new Error(j.hold_reason || 'HOLD'); return j.items || []; }); },
    wiki: function (q) { return JS('https://ru.wikipedia.org/w/api.php?action=query&list=search&format=json&origin=*&srlimit=8&srsearch=' + encodeURIComponent(q)).then(function (j) { return ((j.query && j.query.search) || []).map(function (w) { return { title: w.title, url: 'https://ru.wikipedia.org/wiki/' + encodeURIComponent(w.title.replace(/ /g, '_')), year: '', authors: [], venue: 'Википедия', summary: String(w.snippet || '').replace(/<[^>]+>/g, '') }; }); }); }
  };
  function cite(it) { return (authors(it.authors) || 'Без автора') + (it.year ? ' (' + it.year + ')' : '') + '. ' + (it.title || '') + '.' + (it.venue ? ' ' + it.venue + '.' : '') + (it.url ? ' ' + it.url : ''); }
  function sciPanel(host) {
    var cur = 'openalex', box = document.createElement('div');
    box.innerHTML = '<div class="rx2-m">Поиск источников без ключей. Ничего не выдумываю: нет ответа источника значит нет результатов.</div><div class="rx2-r" role="group" aria-label="Источник">' +
      SRC.map(function (s, i) { return '<button type="button" class="rx2-t" data-s="' + s[0] + '" aria-pressed="' + (i === 0) + '">' + s[1] + '</button>'; }).join('') + '</div>' +
      '<div class="rx2-r"><sl-input id="rx2-q" placeholder="Тема, автор, DOI…" aria-label="Запрос" style="flex:1 1 240px" clearable></sl-input><sl-button id="rx2-go" variant="primary" style="min-height:44px">Искать</sl-button></div><p class="rx2-st" id="rx2-ss" role="status"></p><div id="rx2-res" style="display:grid;gap:8px"></div>';
    host.appendChild(box);
    var q = box.querySelector('#rx2-q'), ss = box.querySelector('#rx2-ss'), res = box.querySelector('#rx2-res');
    box.querySelectorAll('.rx2-t').forEach(function (b) { b.addEventListener('click', function () { cur = b.dataset.s; box.querySelectorAll('.rx2-t').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); }); if (q.value.trim()) run(); }); });
    var tok = 0;
    function run() {
      var my = ++tok, t = (q.value || '').trim(); if (!t) { ss.textContent = 'Введите запрос.'; return; }
      ss.textContent = 'Ищу…'; res.innerHTML = '';
      FIND[cur](t).then(function (items) {
        if (my !== tok) return;
        items = (items || []).filter(function (x) { return x && x.title; });
        ss.textContent = items.length ? 'Найдено: ' + items.length + ' (' + SRC.filter(function (s) { return s[0] === cur; })[0][1] + ')' : 'Нет результатов в этом источнике.';
        items.forEach(function (it) {
          var c = document.createElement('sl-card'); c.innerHTML = '<a href="' + esc(it.url || '#') + '" target="_blank" rel="noopener"><b>' + esc(it.title) + '</b></a><div class="rx2-m">' + esc([authors(it.authors), it.year, it.venue].filter(Boolean).join(' · ')) + '</div>' + (it.summary ? '<div class="rx2-m">' + esc(it.summary) + '</div>' : '');
          var b = document.createElement('sl-button'); b.size = 'small'; b.textContent = 'Копировать ссылку'; b.style.minHeight = '44px';
          b.addEventListener('click', function () { var t2 = cite(it); (navigator.clipboard ? navigator.clipboard.writeText(t2) : Promise.reject()).then(function () { ss.textContent = 'Скопировано.'; }, function () { ss.textContent = t2; }); });
          c.appendChild(b); res.appendChild(c);
        });
      }).catch(function (e) { if (my !== tok) return; ss.textContent = 'Источник недоступен: ' + e.message + '. Попробуйте другой.'; });
    }
    box.querySelector('#rx2-go').addEventListener('click', run);
    q.addEventListener('keydown', function (e) { if (e.key === 'Enter') run(); });
  }

  /* ---------- Музыка/Видео: HOLD со ссылками ---------- */
  function holdPanel(host) {
    var v = rid === 'video';
    var links = v ? [['Wan 2.x (Alibaba, Apache-2.0, открытые веса)', 'https://github.com/Wan-Video/Wan2.1'], ['LTX-Video (Lightricks, открытые веса)', 'https://github.com/Lightricks/LTX-Video'], ['Puter.js: бесплатный Wan API без ключа (платит пользователь сервиса)', 'https://developer.puter.com/tutorials/free-unlimited-wan-ai-api/']]
      : [['MusicGen (Meta, открытые веса)', 'https://github.com/facebookresearch/audiocraft'], ['Stable Audio Open (Stability AI)', 'https://huggingface.co/stabilityai/stable-audio-open-1.0'], ['ACE-Step (открытая модель музыки)', 'https://github.com/ace-step/ACE-Step']];
    var d = document.createElement('sl-details'); d.setAttribute('summary', 'Генерация ' + (v ? 'видео' : 'музыки') + ': HOLD, найденные варианты');
    d.innerHTML = '<p class="rx2-m">Рабочего бесплатного API без ключа и без своего GPU не найдено. GPU сервера занят обучением, поэтому локальную модель не запускаю. Варианты на выбор владельца:</p><ul style="margin:0;padding-left:18px">' + links.map(function (l) { return '<li><a href="' + l[1] + '" target="_blank" rel="noopener">' + esc(l[0]) + '</a></li>'; }).join('') + '</ul>';
    host.appendChild(d);
  }

  /* ---------- панель памяти ---------- */
  function memPanel(host) {
    var d = document.createElement('sl-details'); d.setAttribute('summary', 'Память роли');
    d.innerHTML = '<div class="rx2-m">Что NOX должен помнить в этой роли: стиль, факты, договорённости. Хранится на сервере (заметки), подмешивается в запросы роли.</div><sl-textarea id="rx2-mt" rows="5" resize="vertical" label="Память" aria-label="Память роли"></sl-textarea><p class="rx2-st" id="rx2-ms" role="status"></p>';
    host.appendChild(d);
    var t = d.querySelector('#rx2-mt'); t.value = mem.text; t.addEventListener('sl-input', function () { saveMem(t.value || ''); });
    pull().then(function (ch) { if (ch) t.value = mem.text; stat(mem.text ? 'загружено' : ''); });
  }

  function build() {
    var cv = document.getElementById('rs-cv'); if (!cv || document.getElementById('rx2')) return false;
    var h = document.createElement('div'); h.id = 'rx2'; cv.appendChild(h);
    if (rid !== 'writer') memPanel(h);
    if (rid === 'scientist') { sciPanel(h); var o = document.querySelector('#rs-media .rx-hold'); if (o) o.textContent = 'Формулы в записи $…$ и $$…$$ отображаются в «Просмотре» и в ответах (KaTeX). Источники ищутся панелью ниже.'; }
    if (rid === 'music' || rid === 'video') holdPanel(h);
    if (!h.children.length) h.remove();
    return true;
  }
  var n = 0, iv = setInterval(function () { if (build() || ++n > 50) clearInterval(iv); }, 300);
})();
