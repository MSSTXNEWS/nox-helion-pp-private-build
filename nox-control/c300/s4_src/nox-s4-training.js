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
      if (o && o.method === 'POST' && /\/memory\/api$/.test(String(u)) && typeof o.body === 'string' && /./.test(o.body)) return Promise.resolve(new Response(JSON.stringify({ ok: false, error: 'сервер памяти не развёрнут' }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
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
  const wb = document.createElement('div'); wb.className = 's4wb';
  wb.innerHTML = '<div class="s4tiles" id="s4t"></div><aside class="card s4runs"><h2>Запуски <span class="r mono" id="s4rn"></span></h2><div id="s4rl" class="muted">Загрузка…</div></aside>'
    + '<div class="s4charts" id="s4ch"></div><div class="s4side"></div>';
  const ph = $('.ph', wrap); ph ? ph.after(wb) : wrap.prepend(wb);
  const sideCol = $('.s4side', wb); [...side.children].forEach((c) => sideCol.appendChild(c));
  [...wrap.querySelectorAll('section.card > h2')].forEach((h) => { if (/Кривые обучения/i.test(h.textContent)) h.parentNode.classList.add('s4hide'); });
  const COL = ['#e0654a', '#d9a441', '#6aa9d8', '#8fc28a', '#b48ad8', '#d68aa6'];
  async function runs() {
    let d = null, L = null; try { d = await (await fetch('./data/train_logs.json?t=' + Date.now(), { cache: 'no-store' })).json(); } catch (e) { /* */ }
    try { L = await (await fetch('./data/live.json?t=' + Date.now(), { cache: 'no-store' })).json(); } catch (e) { /* */ }
    const R = d && d.runs ? Object.keys(d.runs).filter((k) => (d.runs[k].points || []).length) : [];
    const pts = R.flatMap((k) => d.runs[k].points), best = (f) => { const a = pts.map((p) => p[f]).filter((v) => typeof v === 'number'); return a.length ? Math.min(...a) : null; };
    const last = R.length ? d.runs[R.slice().sort((a, b) => d.runs[b].mtime - d.runs[a].mtime)[0]].points.slice(-1)[0] : null;
    const tile = (k, v, s) => '<div class="s4tl"><small>' + k + '</small><b>' + v + '</b><em>' + (s || '') + '</em></div>';
    $('#s4t').innerHTML = tile('Статус', d ? (d.running ? 'идёт' : 'остановлено') : 'нет данных', d && d.ts ? when(d.ts) : '') + tile('Запусков', R.length, 'с точками') + tile('Последний шаг', last ? last.step : '—', last ? 'loss ' + last.loss : '') + tile('Лучший loss', best('loss') == null ? '—' : best('loss')) + tile('Лучший CE', best('ce') == null ? '—' : best('ce').toFixed(3)) + tile('VRAM', L && L.gpu ? L.gpu.vram_pct + '%' : '—', L && L.gpu ? 'GPU ' + L.gpu.gpu_util_pct + '%' : '');
    const hid = JSON.parse(localStorage.getItem('s4_hid') || '[]');
    $('#s4rn').textContent = R.length + ' шт.'; $('#s4rl').className = R.length ? '' : 'muted';
    $('#s4rl').innerHTML = R.length ? R.map((k, i) => '<label class="s4rr"><input type="checkbox" data-k="' + esc(k) + '"' + (hid.includes(k) ? '' : ' checked') + '><i style="background:' + COL[i % 6] + '"></i><span>' + esc(k.replace(/\.log$/, '')) + '</span><small class="mono">' + d.runs[k].points.length + ' т.</small></label>').join('') : 'Логов обучения пока нет.';
    const draw = () => {
      const off = JSON.parse(localStorage.getItem('s4_hid') || '[]'), box = $('#s4ch');
      if (!R.length) { box.innerHTML = '<section class="card" id="s4em"></section>'; const em = $('#s4em'); if (window.NOXds) NOXds.unavailable(em, 'Нет логов обучения (data/train_logs.json).'); else em.textContent = 'Нет логов обучения.'; return; }
      if (!box.children.length || !box.querySelector('.s4cp')) box.innerHTML = [['loss', 'Train loss'], ['ce', 'Holdout CE']].map(([f, t]) => '<section class="card s4cp"><h2>' + t + ' <span class="r mono">шаг</span></h2><div class="s4cc" id="s4c_' + f + '"></div></section>').join('') + '<p class="muted s4note">' + (pts.length < 12 ? 'Точек мало (' + pts.length + '): логи пишутся раз в 10 шагов, кривая достроится по мере обучения.' : '') + '</p>';
      ['loss', 'ce'].forEach((f) => { const el = $('#s4c_' + f), c = echarts.getInstanceByDom(el) || echarts.init(el, 'nox');
        c.setOption({ animation: false, color: COL, grid: { left: 40, right: 12, top: 12, bottom: 28 }, tooltip: { trigger: 'axis', backgroundColor: 'rgba(20,16,16,.92)', borderColor: '#5a3a34', textStyle: { color: '#efe6df', fontSize: 12 } },
          xAxis: { type: 'value', name: '', axisLabel: { color: '#9a8f88', fontSize: 10 }, splitLine: { show: false }, axisLine: { lineStyle: { color: '#3a302d' } } }, yAxis: { type: 'value', scale: true, axisLabel: { color: '#9a8f88', fontSize: 10 }, splitLine: { lineStyle: { color: 'rgba(255,235,220,.07)' } } },
          series: R.map((k, i) => ({ name: k, type: 'line', showSymbol: true, symbolSize: 5, smooth: true, lineStyle: { width: 1.8 }, data: off.includes(k) ? [] : d.runs[k].points.filter((p) => typeof p[f] === 'number').map((p) => [p.step, p[f]]) })) }, true); });
    };
    draw(); $('#s4rl').querySelectorAll('input').forEach((i) => (i.onchange = () => { const a = [...$('#s4rl').querySelectorAll('input')].filter((x) => !x.checked).map((x) => x.dataset.k); localStorage.setItem('s4_hid', JSON.stringify(a)); draw(); }));
  }
  runs(); setInterval(runs, 60000); addEventListener('resize', () => document.querySelectorAll('.s4cc').forEach((e) => { const c = echarts.getInstanceByDom(e); c && c.resize(); }));
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
    sug.innerHTML = ps.length ? ps.map((m, i) => '<div class="s4c"><div>' + esc(String(m.text || '').slice(0, 360)) + '</div><div class="s4b">' + ACT.map(([k, l, re]) => { const n = find(re), un = !n || /недоступн/i.test((reg[n] || {}).desc || ''); return '<sl-button size="medium" variant="' + (k === 'apply' ? 'primary' : 'default') + '" data-i="' + i + '" data-k="' + k + '"' + (un ? ' disabled title="' + esc(n ? (reg[n].desc || 'недоступно') : 'команда не в реестре шины') + '"' : '') + '>' + l + (un ? ' · недоступно' : '') + '</sl-button>'; }).join('') + '</div></div>').join('') : 'Предложений от NOX сейчас нет.';
    sug.querySelectorAll('sl-button').forEach((b) => (b.onclick = () => { const a = ACT.find((x) => x[0] === b.dataset.k); run(find(a[2]), a[1], ps[+b.dataset.i]); }));
  }
  tick(); setInterval(tick, 30000);
})();
