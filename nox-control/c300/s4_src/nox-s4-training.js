/* S4 · Обучение: раскладка W&B. Чат про обучение, лента событий (зел/жёлт/крас), push красных (ntfy), карточки предложений NOX -> команды шины.
   Только реальные данные: /api/nox/outbox, /api/nox/status, qa/registry.json. Пусто = честная надпись. */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const PRE = '[Контекст: страница «Обучение». Все вопросы пользователя относятся к обучению NOX: данные, правки, чекпоинты, дистилляция, шаги, потери.]\n';
  /* 1. чат этой страницы воспринимается как про обучение */
  const of = window.fetch;
  window.fetch = function (u, o) {
    try {
      if (o && o.method === 'POST' && /\/api\/(turn|chat)(\?|$)/.test(String(u)) && typeof o.body === 'string') {
        const b = JSON.parse(o.body);
        if (Array.isArray(b.messages)) { const m = b.messages[b.messages.length - 1]; if (m && m.role === 'user' && typeof m.content === 'string' && !m.content.includes('Контекст: страница «Обучение»')) m.content = PRE + m.content; }
        else for (const k of ['text', 'message', 'prompt']) if (typeof b[k] === 'string' && !b[k].includes('Контекст: страница «Обучение»')) { b[k] = PRE + b[k]; break; }
        o = Object.assign({}, o, { body: JSON.stringify(b) });
      }
    } catch (e) { /* не JSON - не трогаем */ }
    return of.call(this, u, o);
  };
  const lvl = (m) => {
    const l = String(m.level || m.severity || m.kind || '').toLowerCase();
    if (/crit|err|red|fatal|alert/.test(l)) return 'r'; if (/warn|yellow/.test(l)) return 'y'; if (/ok|info|green|done/.test(l)) return 'g';
    const t = String(m.text || '').toLowerCase();
    if (/ошибк|сбой|критич|упал|не удалось|переполн|oom/.test(t)) return 'r'; if (/внимани|предупрежд|медленн|скапливаются|риск|пора/.test(t)) return 'y'; return 'g';
  };
  const isProp = (m) => m.proposal || m.type === 'proposal' || /предлага|рекоменду|можно применить|стоит/i.test(String(m.text || ''));
  const when = (t) => new Date(t * 1000).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
  const toast = (m) => { try { window.NoxToast ? window.NoxToast(m) : (() => { const d = document.createElement('div'); d.textContent = m; d.className = 's4-toast'; document.body.appendChild(d); setTimeout(() => d.remove(), 3500); })(); } catch (e) { /* */ } };
  let reg = null;
  const loadReg = () => fetch('qa/registry.json', { cache: 'no-cache' }).then((r) => r.json()).then((j) => (reg = j.commands || {})).catch(() => (reg = {}));
  const find = (re) => Object.keys(reg || {}).find((k) => re.test(k + ' ' + ((reg[k] || {}).desc || '')));
  const ACT = [['apply', 'применить', /apply|примен/i], ['download', 'скачать', /download|скач|export|выгруз/i], ['distill', 'дистиллировать', /distill|дистилл/i]];
  /* 2. раскладка */
  const wrap = $('.wrap'); if (!wrap) return;
  const side = document.createElement('div'); side.className = 's4-w';
  side.innerHTML = '<section class="card s4-sug"><h2>Предложения NOX <span class="r mono" id="s4sn"></span></h2><div id="s4sug" class="muted">Загрузка…</div></section>'
    + '<aside class="card s4-feed"><h2>События <span class="r mono"><i class="s4d g"></i><i class="s4d y"></i><i class="s4d r"></i></span></h2><div id="s4feed" class="muted">Загрузка…</div></aside>';
  const grid = $('.grid', wrap); grid ? grid.before(side) : wrap.appendChild(side);
  let seen = new Set(JSON.parse(localStorage.getItem('s4_push_seen') || '[]'));
  async function push(m) {
    const id = m.id || m.ts; if (seen.has(id)) return; seen.add(id); localStorage.setItem('s4_push_seen', JSON.stringify([...seen].slice(-200)));
    const link = location.origin + '/training.html';
    try {
      const r = await fetch('/svc/ntfy/nox-alerts', { method: 'POST', headers: { Title: 'NOX: важное (обучение)', Priority: '4', Tags: 'rotating_light', Click: link }, body: String(m.text || '').slice(0, 400) });
      if (!r.ok) throw new Error(r.status);
    } catch (e) { toast('ntfy недоступен (' + e.message + '): показываю локально'); }
    if (window.Notification && Notification.permission === 'granted') try { new Notification('NOX: важное', { body: String(m.text || '').slice(0, 200) }); } catch (e) { /* */ }
    toast('Важное: ' + String(m.text || '').slice(0, 90));
  }
  async function run(name, label, m) {
    if (!window.NOXcmd) return toast('Шина команд не загружена');
    const r = await window.NOXcmd(name, { source: 'training', proposal: m.id || m.ts, text: String(m.text || '').slice(0, 300) });
    toast(label + (r && r.ok ? ': готово' : ': ' + ((r && r.error) || 'ошибка')));
  }
  async function tick() {
    if (!reg) await loadReg();
    let ms = []; try { const j = await (await fetch('/api/nox/outbox', { cache: 'no-store' })).json(); ms = (j.messages || []).slice(-60).reverse(); } catch (e) { /* */ }
    const feed = $('#s4feed'), sug = $('#s4sug');
    feed.className = ms.length ? '' : 'muted';
    feed.innerHTML = ms.length ? ms.slice(0, 30).map((m) => '<div class="s4e"><i class="s4d ' + lvl(m) + '"></i><div><div>' + esc(String(m.text || '').slice(0, 220)) + '</div><small class="mono">' + when(m.ts) + '</small></div></div>').join('') : 'Событий пока нет.';
    ms.filter((m) => lvl(m) === 'r').slice(0, 3).forEach(push);
    const ps = ms.filter(isProp).slice(0, 4); $('#s4sn').textContent = ps.length ? ps.length + ' шт.' : '';
    sug.className = ps.length ? '' : 'muted';
    sug.innerHTML = ps.length ? ps.map((m, i) => '<div class="s4c"><div>' + esc(String(m.text || '').slice(0, 360)) + '</div><div class="s4b">' + ACT.map(([k, l, re]) => { const n = find(re); return '<button type="button" data-i="' + i + '" data-k="' + k + '"' + (n ? '' : ' disabled title="команда не в реестре шины"') + '>' + l + '</button>'; }).join('') + '</div></div>').join('') : 'Предложений от NOX сейчас нет.';
    sug.querySelectorAll('button').forEach((b) => (b.onclick = () => { const a = ACT.find((x) => x[0] === b.dataset.k); run(find(a[2]), a[1], ps[+b.dataset.i]); }));
  }
  tick(); setInterval(tick, 30000);
})();
