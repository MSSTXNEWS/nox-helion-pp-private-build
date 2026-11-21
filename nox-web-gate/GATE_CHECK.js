/* GATE_CHECK: «ворота» перед подключением нового чата. Запуск: bash GATE_CHECK.sh (NODE_PATH=$(npm root -g)).
   Поднимает: статический сервер на /tmp/final (+ прокси /glm/ -> 127.0.0.1:8082, как на S1), НАСТОЯЩИЙ gateway.py (NOX_UPSTREAM -> поддельный llama-server),
   затем Playwright e2e на 1440x900 и 390x844. Итог: GATE_REPORT.md, код выхода 0 только если всё прошло.
   Фикстуры /api/* нужны только чтобы старый чат мог отправить сообщение; к новому чату они отношения не имеют. */
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path'), cp = require('child_process');
const ROOT = process.env.GATE_ROOT || '/tmp/final';
const REPO_GW = process.env.GATE_GATEWAY || '/home/claude/nox-helion-pp-private-build/nox-control/glm53/gateway.py';
const SP = 18790, UP = 18081, GW = 8082, UPF = 18083, GWF = 18082;
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.woff': 'font/woff', '.mp4': 'video/mp4', '.webm': 'video/webm', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.txt': 'text/plain' };
const rows = []; let cur = '';
const rec = (name, ok, detail) => { rows.push({ vp: cur, name, ok, detail: String(detail || '').replace(/\|/g, '/').replace(/\n/g, ' ').slice(0, 220) }); console.log((ok ? 'PASS' : 'FAIL') + ' [' + cur + '] ' + name + (ok ? '' : ' :: ' + detail)); };
let curPg = null;
async function T(name, fn) { try { const r = await fn(); if (r === false) rec(name, false, 'условие не выполнено'); else rec(name, true, typeof r === 'string' ? r : ''); } catch (e) { rec(name, false, (e && e.message || e).toString().split('\n')[0]); try { if (curPg) await curPg.screenshot({ path: path.join(ROOT, 'qa/gate/fail_' + cur + '_' + rows.length + '.png') }); } catch { } } }
const sleep = ms => new Promise(r => setTimeout(r, ms));
const J = o => JSON.stringify(o);

/* ---------- статический сервер ---------- */
let apiChatHits = 0;
const stat = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x'); let p = decodeURIComponent(u.pathname);
  if (p.startsWith('/glm/') || p.startsWith('/glmf/')) {   // как маршрут S1: /glm/ -> 127.0.0.1:8082/ (/glmf/ — второй шлюз с быстрым тиром)
    const fastRoute = p.startsWith('/glmf/');
    const pr = http.request({ host: '127.0.0.1', port: fastRoute ? GWF : GW, path: p.slice(fastRoute ? 5 : 4) + u.search, method: req.method, headers: Object.assign({}, req.headers, { host: '127.0.0.1:' + GW }) }, r => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
    pr.on('error', e => { res.writeHead(502, { 'Content-Type': 'text/plain' }); res.end('Bad Gateway: ' + e.message); });
    req.pipe(pr); return;
  }
  if (p.startsWith('/api/')) {                       // фикстуры для старого чата (только тест)
    let b = ''; req.on('data', d => b += d); req.on('end', () => {
      const js = (o, c = 200) => { res.writeHead(c, { 'Content-Type': 'application/json' }); res.end(J(o)); };
      if (p === '/api/nox/status') return js({ status: 'READY', model: 'nox-helion:latest', digest: 'sha256:gate', memory: { status: 'HOLD' } });
      if (p === '/api/settings') return js({ settings: {} });
      if (p === '/api/voice/status') return js({ status: 'UNAVAILABLE', reason: 'fixture' });
      if (p === '/api/chat' && req.method === 'POST') {
        apiChatHits++; let q = {}; try { q = JSON.parse(b); } catch { }
        res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
        const rid = q.request_id, m = 'nox-helion:latest';
        res.write(J({ request_id: rid, model: m, message: { content: 'Ответ СТАРОГО чата ' } }) + '\n');
        setTimeout(() => { res.write(J({ request_id: rid, model: m, message: { content: 'на проверочный запрос.' } }) + '\n'); res.end(J({ request_id: rid, model: m, done: true, digest: 'sha256:gate', frames: 2 }) + '\n'); }, 60); return;
      }
      return js({ status: 'HOLD', ok: false, reason: 'fixture: ' + p });
    }); return;
  }
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(ROOT, p); if (!f.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  fs.stat(f, (e, s) => { if (e || !s.isFile()) { res.writeHead(404, { 'Content-Type': 'text/plain' }); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res); });
});

/* ---------- процессы ---------- */
let fake = null, fake2 = null, gw = null, gwf = null;
function spawnPy(args, env) { const c = cp.spawn('python3', args, { env: Object.assign({}, process.env, env), stdio: ['ignore', 'pipe', 'pipe'] }); c.stderr.on('data', () => { }); c.stdout.on('data', () => { }); return c; }
function get(url) { return new Promise((ok, no) => { http.get(url, r => { let b = ''; r.on('data', d => b += d); r.on('end', () => ok({ status: r.statusCode, headers: r.headers, body: b })); }).on('error', no); }); }
function post(port, p, body) { return new Promise((ok, no) => { const d = Buffer.from(J(body)); const r = http.request({ host: '127.0.0.1', port, path: p, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': d.length } }, x => { let b = ''; x.on('data', c => b += c); x.on('end', () => ok({ status: x.statusCode, headers: x.headers, body: b })); }); r.on('error', no); r.end(d); }); }
async function up(url, tries = 40) { for (let i = 0; i < tries; i++) { try { await get(url); return true; } catch { await sleep(150); } } return false; }
async function startGw() { gw = spawnPy([REPO_GW], { NOX_UPSTREAM: 'http://127.0.0.1:' + UP, NOX_FAST_UPSTREAM: 'off' }); if (!await up('http://127.0.0.1:' + GW + '/v1/models')) throw Error('gateway.py не поднялся на :' + GW); }
async function startGwFast() { gwf = spawnPy([REPO_GW], { NOX_UPSTREAM: 'http://127.0.0.1:' + UP, NOX_FAST_UPSTREAM: 'http://127.0.0.1:' + UPF, NOX_LISTEN_PORT: String(GWF) }); if (!await up('http://127.0.0.1:' + GWF + '/v1/nox/stats')) throw Error('gateway.py (быстрый тир) не поднялся на :' + GWF); }
async function stopGw() { if (gw) { gw.kill('SIGKILL'); gw = null; await sleep(400); } }
const upLog = async () => JSON.parse((await get('http://127.0.0.1:' + UP + '/__log')).body);

/* ---------- 0. шлюз напрямую ---------- */
async function gatewayDirect() {
  cur = 'gateway';
  const P = '/v1/chat/completions';
  await T('gateway.py: обычный ответ, nox.effort/memory_text/violations/length', async () => {
    const r = await post(GW, P, { messages: [{ role: 'user', content: 'Привет, ответь в 5 словах' }] }); const j = JSON.parse(r.body);
    return r.status === 200 && j.nox && j.nox.effort === 'low' && !/<think>/.test(j.nox.memory_text) && Array.isArray(j.nox.violations) && j.nox.length && j.nox.length.want === 5 ? 'effort=' + j.nox.effort : false; });
  await T('gateway.py: авто-effort high для «почему», max для кода, неверное значение -> high', async () => {
    const e = async b => JSON.parse((await post(GW, P, b)).body).nox.effort;
    const a = await e({ messages: [{ role: 'user', content: 'Почему небо голубое?' }] }), c = await e({ messages: [{ role: 'user', content: 'Напиши функцию на python' }] }), x = await e({ reasoning_effort: 'ultra', messages: [{ role: 'user', content: 'Привет' }] });
    return a === 'high' && c === 'max' && x === 'high' ? [a, c, x].join('/') : false; });
  await T('gateway.py: нарушение -> одна повторная попытка (retried_for), nox_no_retry отключает', async () => {
    const a = JSON.parse((await post(GW, P, { messages: [{ role: 'user', content: 'нарушение' }] })).body).nox;
    const b = JSON.parse((await post(GW, P, { nox_no_retry: true, messages: [{ role: 'user', content: 'нарушение' }] })).body).nox;
    return a.retried_for && a.retried_for.length >= 2 && a.violations.length === 0 && b.violations.length >= 2 && !b.retried_for ? 'retried_for=' + a.retried_for : false; });
  await T('gateway.py: stream -> SSE, X-NOX-Mode/X-NOX-Request-Id, первый чанк nox.effort, [DONE]', async () => {
    const r = await post(GW, P, { stream: true, reasoning_effort: 'max', messages: [{ role: 'user', content: 'Привет' }] });
    const first = JSON.parse(r.body.split('\n').find(l => l.startsWith('data: {')).slice(6));
    return /event-stream/.test(r.headers['content-type']) && r.headers['x-nox-mode'] && r.headers['x-nox-request-id'] && first.nox && first.nox.effort === 'max' && /\[DONE\]/.test(r.body) ? 'mode=' + r.headers['x-nox-mode'] + ', effort=' + first.nox.effort : J([r.headers['x-nox-mode'], first.nox]).slice(0, 160); });
  await T('gateway.py: размышления из stream не попадают в delta (QS6)', async () => {
    const r = await post(GW, P, { stream: true, messages: [{ role: 'user', content: 'Привет' }] }); return !/THINKSECRET/.test(r.body) ? '' : 'THINKSECRET в потоке'; });
  await T('gateway.py: двухтактный стрим (fast -> deep, nox_stage) на втором шлюзе с быстрым тиром', async () => {
    const r = await post(GWF, P, { stream: true, nox_mode: 'deep', messages: [{ role: 'user', content: 'Объясни подробно как это работает' }] });
    const st = r.body.split('\n').filter(l => l.startsWith('data: {')).map(l => { try { return JSON.parse(l.slice(6)); } catch { return {}; } }).map(o => o.choices && o.choices[0] && o.choices[0].delta && o.choices[0].delta.nox_stage).filter(Boolean);
    return st.includes('fast') && /\[DONE\]/.test(r.body) ? 'stages=' + [...new Set(st)].join('>') : 'stages=' + J(st); });
  await T('gateway.py: POST /v1/stop отвечает {request_id, stopped}', async () => { const r = await post(GW, '/v1/stop', { request_id: 'none' }); const j = JSON.parse(r.body); return r.status === 200 && j.request_id === 'none' && 'stopped' in j ? '' : false; });
  await T('gateway.py: история — размышления не уходят в апстрим (G01)', async () => {
    const n0 = (await upLog()).length;
    await post(GW, P, { messages: [{ role: 'user', content: 'один' }, { role: 'assistant', content: '<think>СЕКРЕТНОЕ</think>ответ', reasoning_content: 'СЕКРЕТНОЕ' }, { role: 'user', content: 'два' }] });
    const l = (await upLog()).slice(n0)[0]; return !JSON.stringify(l.messages).includes('СЕКРЕТНОЕ') && l.chat_template_kwargs.reasoning_effort ? 'ok' : false; });
}

/* ---------- страницы/меню ---------- */
function attach(pg, bag) { pg.on('console', m => { if (m.type() === 'error') bag.push('console: ' + m.text().slice(0, 140)); }); pg.on('pageerror', e => bag.push('pageerror: ' + String(e).slice(0, 140))); }
async function menus(br, vp) {
  const ctx = await br.newContext({ viewport: vp }); ctx.setDefaultTimeout(15000); ctx.setDefaultNavigationTimeout(60000); const pg = await ctx.newPage(); const bag = []; attach(pg, bag);
  const base = 'http://127.0.0.1:' + SP + '/';
  await pg.goto(base + 'index.html', { waitUntil: 'load' }); await pg.waitForTimeout(2500);
  const items = await pg.evaluate(() => [...document.querySelectorAll('#nxTop a[href],#nxBot a[href],#nxMore a[href]')].map(a => ({ href: a.getAttribute('href'), t: (a.getAttribute('aria-label') || a.title || a.textContent || '').trim() })));
  const acts = await pg.evaluate(() => [...document.querySelectorAll('#nxTop [data-act],#nxBot [data-act],#nxMore [data-act]')].map(a => ({ act: a.dataset.act, t: (a.getAttribute('aria-label') || a.title || a.textContent || '').trim(), more: !!a.closest('#nxMore') })));
  await T('index: нет ошибок консоли при загрузке', async () => bag.length === 0 ? '' : bag.slice(0, 2).join(' ; '));
  await T('index: нет горизонтального скролла', async () => { const w = await pg.evaluate(() => [document.documentElement.scrollWidth, innerWidth]); return w[0] <= w[1] ? w.join('/') : 'scrollWidth ' + w[0] + ' > ' + w[1]; });
  await T('index: центр планеты (мини-ядро) = W/2±1', async () => {
    const r = await pg.evaluate(() => { const W = innerWidth, out = []; document.querySelectorAll('canvas').forEach(c => { const b = c.getBoundingClientRect(); if (b.width > 0 && b.height > 0) out.push({ id: c.id || (c.parentElement && c.parentElement.id) || 'canvas', cx: b.left + b.width / 2, w: b.width }); }); const res = document.getElementById('nxRes'); const rb = res && res.getBoundingClientRect(); return { W, out, res: rb ? rb.left + rb.width / 2 : null }; });
    const bad = r.out.filter(o => Math.abs(o.cx - r.W / 2) > 1); if (!r.out.length) return false;
    return bad.length === 0 ? 'canvas=' + r.out.length + ', W/2=' + r.W / 2 : 'сдвиг: ' + bad.map(b => b.id + ' cx=' + b.cx.toFixed(1)).join(', ');
  });
  await T('index: кнопка «Резонанс» по центру W/2±1', async () => { const r = await pg.evaluate(() => { const e = document.getElementById('nxRes'); if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width / 2, innerWidth / 2]; }); return r && Math.abs(r[0] - r[1]) <= 1 ? r.map(x => x.toFixed(1)).join('/') : 'сдвиг ' + J(r); });
  /* переход по каждому пункту-ссылке */
  const seen = new Set();
  for (const it of items) {
    const h = it.href.split('#')[0]; if (seen.has(h)) continue; seen.add(h);
    const p2 = await ctx.newPage(); const b2 = []; attach(p2, b2);
    await T('пункт меню «' + it.t + '» -> ' + it.href + ': открывается без ошибок консоли, без h-скролла', async () => {
      const r = await p2.goto(base + it.href, { waitUntil: 'domcontentloaded', timeout: 25000 }); await p2.waitForTimeout(3000);
      const w = await p2.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
      if (!r || r.status() !== 200) return 'HTTP ' + (r && r.status());
      if (b2.length) return b2.slice(0, 2).join(' ; ');
      if (w[0] > w[1] + 0) return 'горизонтальный скролл ' + w.join('>');
      return '';
    }); await p2.close();
  }
  /* кнопки-действия (в т.ч. «Поиск (Ctrl+K)», «Ещё» и его пункты) */
  for (const a of acts) {
    const p2 = await ctx.newPage(); const b2 = []; attach(p2, b2);
    await T('пункт меню «' + a.t + '» [' + a.act + ']: действие без ошибок', async () => {
      await p2.goto(base + 'index.html', { waitUntil: 'domcontentloaded' }); await p2.waitForTimeout(2500);
      if (a.more) { await p2.click('#nxTop [data-more]'); await p2.waitForTimeout(200); }
      await p2.click((a.more ? '#nxMore' : '#nxTop,#nxBot') + ' [data-act="' + a.act + '"]', { timeout: 25000 }); await p2.waitForTimeout(700);
      await p2.keyboard.press('Escape'); await p2.waitForTimeout(200);
      return b2.length ? b2.slice(0, 2).join(' ; ') : '';
    }); await p2.close();
  }
  await T('меню «Поиск (Ctrl+K)»: открывается с клавиатуры', async () => {
    const p2 = await ctx.newPage(); const b2 = []; attach(p2, b2); await p2.goto(base + 'index.html', { waitUntil: 'load' }); await p2.waitForTimeout(1500);
    await p2.keyboard.press('Control+k'); await p2.waitForTimeout(600); const ok = await p2.evaluate(() => !!document.querySelector('input[type=search],#nxPal,.nx-pal,[role=dialog] input,input[placeholder*="оиск"]')); await p2.close(); return ok && !b2.length ? '' : (b2[0] || 'палитра не найдена');
  });
  await ctx.close();
}

/* ---------- чат ---------- */
async function chat(br, vp) {
  const ctx = await br.newContext({ viewport: vp }); ctx.setDefaultTimeout(30000); ctx.setDefaultNavigationTimeout(60000); const pg = await ctx.newPage(); const bag = []; attach(pg, bag);
  curPg = pg; const bodies = []; pg.on('request', r => { if (r.url().includes('/glm') && !r.url().endsWith('/stop') && r.method() === 'POST') { try { bodies.push(JSON.parse(r.postData())); } catch { } } });
  const base = 'http://127.0.0.1:' + SP + '/';
  const dom = sel => pg.evaluate(s => document.querySelector(s).click(), sel);
  const setSel = (sel, v) => pg.evaluate(([s, v]) => { document.querySelector(s).value = v; }, [sel, v]);
  const setChk = (sel, v) => pg.evaluate(([s, v]) => { document.querySelector(s).checked = v; }, [sel, v]);
  const clk = async sel => { const hit = await pg.evaluate(s => { const e = document.querySelector(s); if (!e) return 'нет элемента'; e.scrollIntoView({ block: 'center' }); const r = e.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t && (t === e || e.contains(t)) ? 'ok' : 'перекрыт: ' + (t && [t.id, t.className, t.tagName, t.parentElement && (t.parentElement.id || t.parentElement.className), t.textContent && t.textContent.slice(0, 30)].join('|')); }, sel); if (hit !== 'ok') { try { await pg.screenshot({ path: path.join(ROOT, 'qa/gate/overlap_' + cur + '_' + sel.replace(/[^a-z0-9]+/gi, '_').slice(0, 40) + '.png') }); } catch { } throw Error(sel + ' ' + hit); } await pg.locator(sel).first().click({ force: true }); };
  await pg.goto(base + 'chat.html', { waitUntil: 'load' }); await pg.waitForTimeout(1800);
  await T('чат: загрузка без ошибок консоли', async () => bag.length ? bag.slice(0, 2).join(' ; ') : '');
  const hs = async () => { const w = await pg.evaluate(() => [document.documentElement.scrollWidth, innerWidth]); return w[0] <= w[1] ? w.join('/') : 'h-скролл ' + w[0] + '>' + w[1]; };
  await T('чат (старый режим): нет горизонтального скролла', hs);
  await T('переключатель: кнопки «Старый чат»/«Новый чат (GLM-5.3)» есть, по умолчанию — старый', async () => (await pg.locator('#nxcOld[aria-pressed=true]').count()) === 1 && (await pg.locator('#nxcNew[aria-pressed=false]').count()) === 1 && !(await pg.locator('#nxcPane').isVisible()));
  await T('старый чат: отправка сообщения и ответ (/api/chat)', async () => {
    await pg.waitForFunction(() => { const e = document.getElementById('chatOllama'); return e && e.textContent === 'ONLINE'; }, null, { timeout: 20000 });
    await pg.fill('#prompt', 'Проверка старого чата'); await clk('button[data-action="send"]');
    await pg.waitForFunction(() => /Ответ СТАРОГО чата на проверочный запрос/.test(document.getElementById('messages').innerText), null, { timeout: 20000 }); return 'hits=' + apiChatHits; });
  const nChat = apiChatHits;
  await T('переключение на «Новый чат»: панель видна, старое поле скрыто, режим в localStorage', async () => {
    await clk('#nxcNew'); await pg.waitForTimeout(500);
    const r = await pg.evaluate(() => ({ on: document.documentElement.classList.contains('nxc-on'), pane: getComputedStyle(document.getElementById('nxcPane')).display, old: getComputedStyle(document.getElementById('chatForm')).display, ls: localStorage.getItem('nox.chat.mode'), foc: document.activeElement && document.activeElement.id }));
    return r.on && r.pane !== 'none' && r.old === 'none' && r.ls === 'new' && r.foc === 'nxcInput' ? 'фокус в поле' : J(r); });
  await T('новый чат: шлюз онлайн (индикатор)', async () => { await pg.waitForSelector('#nxcStat[data-state=ok]', { timeout: 20000 }); return ''; });
  await T('новый чат (новый режим): нет горизонтального скролла', hs);
  const ask = async t => { const n0 = await pg.locator('#nxcList .nxc-msg.a').count(); await pg.fill('#nxcInput', t); await clk('#nxcSend'); await pg.waitForFunction(n => document.querySelectorAll('#nxcList .nxc-msg.a').length >= n && document.getElementById('nxcPane').getAttribute('aria-busy') !== 'true', n0 + 1, { timeout: 30000 }).catch(async e => { const d = await pg.evaluate(() => ({ fail: [...document.querySelectorAll('#nxcList .nxc-fail')].map(x => x.textContent.slice(0, 160)), busy: document.getElementById('nxcPane').getAttribute('aria-busy'), n: document.querySelectorAll('#nxcList .nxc-msg.a').length, stat: document.getElementById('nxcStat').dataset.state })).catch(() => ({})); throw Error('ask(' + t.slice(0, 20) + ') ' + J(d)); }); };
  const lastA = () => pg.locator('#nxcList .nxc-msg.a').last();
  let nb = bodies.length;
  await T('новый чат: отправка (стрим), ответ, бейдж effort=low из nox первого чанка, в видимом ответе нет размышлений', async () => {
    await ask('Привет, как дела');
    const a = lastA(); const txt = await a.locator('.nxc-text').innerText(); const badge = await a.locator('.nxc-badge').innerText(); const meta = await a.locator('.nxc-meta').innerText();
    if (!/Ответ NOX на ваш вопрос/.test(txt) || /THINKSECRET|<think>/.test(txt)) return 'текст: ' + txt.slice(0, 80);
    if (badge !== 'effort: low') return 'бейдж ' + badge;
    return 'stream=' + bodies[nb].stream + ', ' + badge + ', ' + meta; });
  await T('новый чат: размышления НЕ уходят в историю следующего запроса', async () => {
    nb = bodies.length; await ask('Второй вопрос');
    const b = bodies[nb]; const s = J(b.messages); return b.messages.length === 3 && !/THINKSECRET|<think>|reasoning/.test(s) && b.messages.every(m => Object.keys(m).sort().join() === 'content,role') ? 'messages=3, только role+content' : s.slice(0, 160); });
  await T('глубина Max: reasoning_effort=max в запросе, бейдж max', async () => {
    await clk('.nxc-depth [data-depth="max"]'); nb = bodies.length; await ask('Короткий вопрос');
    const up = await upLog(); const last = up[up.length - 1];
    return bodies[nb].reasoning_effort === 'max' && last.chat_template_kwargs.reasoning_effort === 'max' && (await lastA().locator('.nxc-badge').innerText()) === 'effort: max' ? 'upstream effort=max' : J(bodies[nb]).slice(0, 120); });
  await T('глубина Low/High: переключение, aria-pressed и сохранение в localStorage', async () => {
    await clk('.nxc-depth [data-depth="high"]'); nb = bodies.length; await ask('Ещё вопрос');
    const ok1 = bodies[nb].reasoning_effort === 'high' && (await lastA().locator('.nxc-badge').innerText()) === 'effort: high';
    await clk('.nxc-depth [data-depth="low"]'); nb = bodies.length; await ask('И ещё');
    const ls = await pg.evaluate(() => JSON.parse(localStorage.getItem('nox.newchat.cfg')).depth); const ok2 = bodies[nb].reasoning_effort === 'low' && ls === 'low';
    await clk('.nxc-depth [data-depth="auto"]'); nb = bodies.length; await ask('Авто снова'); const ok3 = !('reasoning_effort' in bodies[nb]);
    return ok1 && ok2 && ok3 ? 'high/low/auto' : [ok1, ok2, ok3].join(); });
  await T('SSE: reasoning_content/<think> не попадают в видимый ответ и не в блок (шлюз QS6 их режет)', async () => { await ask('рц проверка'); const a = lastA(); const t = await a.locator('.nxc-text').innerText(); const th = await a.locator('details.nxc-think').evaluate(d => d.hidden || !/THINKSECRET/.test(d.textContent)); return /после размышления/.test(t) && !/THINKSECRET/.test(t) && th ? '' : t.slice(0, 80); });
  await T('violations (стрим): плашки «не X, а Y», лесть, самоназвание Claude', async () => {
    await ask('нарушение'); const v = await lastA().locator('.nxc-warn').evaluateAll(n => n.map(x => x.dataset.v)); return ['not_x_but_y', 'flattery_opener', 'names_self_claude'].every(k => v.includes(k)) ? v.join(',') : 'только ' + v.join(','); });
  /* настройки: без стрима */
  await T('настройки: API по умолчанию /glm/v1/chat/completions, меняется и сохраняется', async () => {
    await dom('#nxcGear'); const v = await pg.inputValue('#nxcApi'); if (v !== '/glm/v1/chat/completions') return 'по умолчанию ' + v;
    await pg.fill('#nxcApi', 'glm/bad'); await dom('#nxcSave'); const m = await pg.textContent('#nxcSetMsg'); if (!/должен начинаться/.test(m)) return 'нет валидации';
    await pg.fill('#nxcApi', '/glm/v1/chat/completions'); await setChk('#nxcStream', false); await setChk('#nxcNoRetry', true); await pg.fill('#nxcFacts', 'Факт один\nФакт два'); await dom('#nxcSave');
    const c = await pg.evaluate(() => JSON.parse(localStorage.getItem('nox.newchat.cfg'))); await dom('#nxcGear'); return c.stream === false && c.noRetry === true && /Факт два/.test(c.facts) ? '' : J(c); });
  await T('без стрима: nox.effort в бейдже, violations шлюза (nox_no_retry), nox_facts доходят до модели', async () => {
    nb = bodies.length; await ask('нарушение'); const a = lastA();
    const v = await a.locator('.nxc-warn').evaluateAll(n => n.map(x => x.dataset.v + '|' + x.title)); const up = await upLog(); const last = up[up.length - 1]; const um = last.messages[last.messages.length - 1].content;
    const th = await a.locator('details.nxc-think').evaluate(d => ({ hidden: d.hidden, open: d.open, ok: /THINKSECRET/.test(d.textContent) })); const tx = await a.locator('.nxc-text').innerText();
    if (th.hidden || th.open || !th.ok || /THINKSECRET|<think>/.test(tx)) return 'think-блок: ' + J(th) + ' текст: ' + tx.slice(0, 60);
    return bodies[nb].stream === false && bodies[nb].nox_no_retry === true && bodies[nb].nox_facts.length === 2 && /Важные факты/.test(um) && v.length >= 2 && v.every(s => /Проверка шлюза/.test(s)) && /effort: (low|high|max)/.test(await a.locator('.nxc-badge').innerText()) ? v.length + ' плашек от шлюза, размышления свёрнуты' : J(v).slice(0, 120) + ' ' + um.slice(0, 60); });
  await T('без стрима: автоповтор шлюза — плашка «переписал», нарушений нет', async () => {
    await dom('#nxcGear'); await setChk('#nxcNoRetry', false); await dom('#nxcSave'); await dom('#nxcGear'); await ask('нарушение'); const a = lastA();
    return (await a.locator('.nxc-note[data-q=retried]').count()) === 1 && (await a.locator('.nxc-warn').count()) === 0 ? '' : false; });
  await T('двухтактный ответ (шлюз с быстрым тиром, nox_mode=deep): быстрый такт + GLM, tier в мета', async () => {
    await dom('#nxcGear'); await pg.fill('#nxcApi', '/glmf/v1/chat/completions'); await setSel('#nxcMode', 'deep'); await setChk('#nxcStream', true); await dom('#nxcSave'); await dom('#nxcGear');
    nb = bodies.length; await ask('Объясни подробно как это работает'); const a = lastA(); const t = await a.locator('.nxc-text').innerText(); const m = await a.locator('.nxc-meta').innerText();
    await dom('#nxcGear'); await pg.fill('#nxcApi', '/glm/v1/chat/completions'); await setSel('#nxcMode', 'auto'); await setChk('#nxcStream', false); await dom('#nxcSave'); await dom('#nxcGear');
    return bodies[nb].nox_mode === 'deep' && /Быстрый такт: это первое предложение/.test(t) && /two_stage/.test(m) ? m : J([bodies[nb].nox_mode, t.slice(0, 80), m]); });
  await T('режим судей: проверка идёт через шлюз, а не через старый /api/chat', async () => {
    await pg.evaluate(() => { const b = document.getElementById('noxJudgeSw'); if (b && b.getAttribute('aria-pressed') !== 'true') b.click(); });
    if (!(await pg.evaluate(() => document.getElementById('noxJudgeSw') && document.getElementById('noxJudgeSw').getAttribute('aria-pressed') === 'true'))) return 'переключатель судей не включился';
    await ask('Расскажи подробно про тест, ОШИБКА-СУДЕЙ'); await pg.waitForSelector('#nxcList .nxc-judge[data-verdict=fix]', { timeout: 30000 });
    await clk('#nxcList .nxc-judge[data-verdict=fix] button'); await pg.waitForFunction(() => /Исправленный итоговый ответ судей/.test(document.getElementById('nxcList').innerText), null, { timeout: 25000 });
    await ask('Расскажи подробно про обычный тест'); await pg.waitForSelector('#nxcList .nxc-judge[data-verdict=ok]', { timeout: 30000 });
    return apiChatHits === nChat ? 'старый /api/chat не вызывался' : '/api/chat вызван ' + (apiChatHits - nChat) + ' раз'; });
  await pg.evaluate(() => { const b = document.getElementById('noxJudgeSw'); if (b && b.getAttribute('aria-pressed') === 'true') b.click(); });
  await T('режим судей выключен: плашка судей не появляется', async () => { await ask('Расскажи подробно ещё один тест'); await sleep(800); return (await lastA().locator('.nxc-judge').count()) === 0 ? '' : false; });
  /* стрим назад, STOP */
  await dom('#nxcGear'); await setChk('#nxcStream', true); await dom('#nxcSave'); await dom('#nxcGear');
  await T('STOP: кнопка прерывает поток, частичный ответ остаётся с пометкой', async () => {
    await pg.fill('#nxcInput', 'длинный ответ'); await clk('#nxcSend'); await pg.waitForFunction(() => document.querySelector('#nxcList .nxc-msg.a:last-child .nxc-text').textContent.length > 12, null, { timeout: 25000 });
    await clk('#nxcStop'); await pg.waitForFunction(() => !document.getElementById('nxcSend').disabled, null, { timeout: 20000 });
    const r = await lastA().evaluate(a => ({ t: a.querySelector('.nxc-text').textContent, n: a.querySelector('.nxc-warns').textContent })); return r.t.length > 5 && r.t.length < 400 && /Остановлено/.test(r.n) ? 'частичный ответ ' + r.t.length + ' симв.' : J(r).slice(0, 120); });
  await T('клавиатура: Esc останавливает поток из поля ввода', async () => {
    await pg.focus('#nxcInput'); await pg.keyboard.type('длинный ответ два'); await pg.keyboard.press('Enter'); await pg.waitForFunction(() => { const t = document.querySelector('#nxcList .nxc-msg.a:last-child .nxc-text'); return t && t.textContent.length > 12; }, null, { timeout: 15000 });
    await pg.waitForTimeout(100); await pg.keyboard.press('Escape'); await pg.waitForFunction(() => !document.getElementById('nxcSend').disabled, null, { timeout: 20000 }); return /Остановлено/.test(await lastA().locator('.nxc-warns').innerText()) ? '' : false; });
  await T('клавиатура: Enter отправляет, Shift+Enter — перенос строки, фокус остаётся читаемым', async () => {
    await pg.focus('#nxcInput'); await pg.keyboard.type('строка1'); await pg.keyboard.press('Shift+Enter'); await pg.keyboard.type('строка2'); const v = await pg.inputValue('#nxcInput'); if (v !== 'строка1\nстрока2') return 'значение ' + J(v);
    await pg.keyboard.press('Enter'); await pg.waitForFunction(() => document.getElementById('nxcInput').value === '' && !document.getElementById('nxcSend').disabled, null, { timeout: 25000 });
    return (await pg.evaluate(() => document.activeElement.id)) === 'nxcInput' ? '' : 'фокус потерян'; });
  await T('клавиатура: стрелки переключают режим на сегменте, Enter/Space на кнопке', async () => {
    await pg.focus('#nxcNew'); await pg.keyboard.press('ArrowLeft'); const a = await pg.evaluate(() => [document.documentElement.classList.contains('nxc-on'), document.activeElement.id]);
    await pg.keyboard.press('ArrowRight'); const b = await pg.evaluate(() => [document.documentElement.classList.contains('nxc-on'), document.activeElement.id]);
    await pg.focus('#nxcOld'); await pg.keyboard.press('Enter'); const c = await pg.evaluate(() => document.documentElement.classList.contains('nxc-on'));
    await pg.focus('#nxcNew'); await pg.keyboard.press('Space'); const d = await pg.evaluate(() => document.documentElement.classList.contains('nxc-on'));
    return a[0] === false && a[1] === 'nxcOld' && b[0] === true && b[1] === 'nxcNew' && c === false && d === true ? '' : J([a, b, c, d]); });
  await T('новый чат: длинная строка без пробелов не даёт горизонтального скролла', async () => {
    await pg.fill('#nxcInput', 'A'.repeat(600)); await pg.keyboard.press('Enter'); await pg.waitForFunction(() => !document.getElementById('nxcSend').disabled, null, { timeout: 25000 }); await pg.waitForTimeout(300);
    const r = await pg.evaluate(() => { const p = document.getElementById('nxcPane').getBoundingClientRect(), l = document.getElementById('nxcList'); return { sw: document.documentElement.scrollWidth, w: innerWidth, l: p.left, r: p.right, lsw: l.scrollWidth, lcw: l.clientWidth }; });
    return r.sw <= r.w && r.l >= 0 && r.r <= r.w + 1 && r.lsw <= r.lcw + 1 ? 'pane ' + Math.round(r.l) + '..' + Math.round(r.r) : J(r); });
  await T('история нового чата переживает перезагрузку, режим сохраняется', async () => {
    const n = await pg.locator('#nxcList .nxc-msg').count(); await pg.reload({ waitUntil: 'load' }); await pg.waitForTimeout(1500);
    const m = await pg.evaluate(() => [document.documentElement.classList.contains('nxc-on'), document.querySelectorAll('#nxcList .nxc-msg').length]); return m[0] && m[1] >= n - 2 && m[1] > 6 ? 'сообщений ' + m[1] : J([n, m]); });
  await T('новый чат: ошибок консоли за время e2e нет (кроме остановки шлюза)', async () => { const x = bag.filter(e => !/Failed to load resource|ERR_|net::/.test(e)); return x.length ? x.slice(0, 2).join(' ; ') : ''; });
  /* неверный адрес (сетевая ошибка) */
  await T('неверный API (сетевая ошибка): честная ошибка, ответ не подменяется, есть «Вернуться на старый чат»', async () => {
    await dom('#nxcGear'); await pg.fill('#nxcApi', 'http://127.0.0.1:1/v1/chat/completions'); await dom('#nxcSave'); await dom('#nxcGear');
    const before = await pg.locator('#nxcList .nxc-msg.a').count(); await pg.fill('#nxcInput', 'тест сети'); await clk('#nxcSend'); await pg.waitForSelector('#nxcList .nxc-fail', { timeout: 25000 });
    const t = await pg.textContent('#nxcList .nxc-fail'); const after = await pg.locator('#nxcList .nxc-msg.a').count(); return after === before && /Подмены ответа нет/.test(t) && (await pg.locator('#nxcList .nxc-fail [data-q=back]').count()) === 1 ? '' : t.slice(0, 120); });
  await dom('#nxcGear'); await pg.fill('#nxcApi', '/glm/v1/chat/completions'); await dom('#nxcSave'); await dom('#nxcGear'); await pg.waitForSelector('#nxcStat[data-state=ok]', { timeout: 20000 });
  /* остановка шлюза */
  await stopGw(); const bagBefore = bag.length;
  await T('шлюз остановлен: индикатор «недоступен», баннер, честная ошибка, нет фейкового ответа', async () => {
    const before = await pg.locator('#nxcList .nxc-msg.a').count(); await pg.fill('#nxcInput', 'шлюз лежит'); await clk('#nxcSend'); await pg.waitForSelector('#nxcList .nxc-fail', { timeout: 25000 });
    const stt = await pg.getAttribute('#nxcStat', 'data-state'); const gwv = await pg.isVisible('#nxcGw'); const t = await pg.textContent('#nxcList .nxc-fail'); const after = await pg.locator('#nxcList .nxc-msg.a').count();
    return stt === 'down' && gwv && after === before && /Подмены ответа нет/.test(t) && /HTTP 502|Нет соединения/.test(t) ? t.slice(30, 110) : J([stt, gwv, before, after, t.slice(0, 100)]); });
  await T('шлюз остановлен: кнопка «Проверить снова» остаётся честной (всё ещё недоступен)', async () => { await clk('#nxcRecheck'); await pg.waitForTimeout(800); return (await pg.getAttribute('#nxcStat', 'data-state')) === 'down' ? '' : false; });
  await T('шлюз остановлен: «Вернуться на старый чат» переключает режим, текст не теряется', async () => {
    await clk('#nxcList .nxc-fail [data-q=back]'); await pg.waitForTimeout(400);
    const r = await pg.evaluate(() => [document.documentElement.classList.contains('nxc-on'), (document.getElementById('prompt') || document.querySelector('#chatForm textarea') || { value: 'НЕТ ПОЛЯ ' + document.querySelectorAll('textarea').length }).value, localStorage.getItem('nox.chat.mode'), getComputedStyle(document.getElementById('chatForm')).display]); return !r[0] && r[1] === 'шлюз лежит' && r[2] === 'old' && r[3] !== 'none' ? '' : J(r); });
  await T('после возврата старый чат снова отвечает', async () => { await pg.fill('#prompt', 'Ещё раз старый'); const h = apiChatHits; await clk('button[data-action="send"]'); await pg.waitForFunction(h0 => true, h); await sleep(900); return apiChatHits > h ? '' : '/api/chat не вызван'; });
  await T('остановка шлюза: нет неперехваченных ошибок страницы (pageerror)', async () => { const x = bag.slice(bagBefore).filter(e => e.startsWith('pageerror')); return x.length ? x[0] : ''; });
  await startGw(); await ctx.close();
}

(async () => {
  let code = 1;
  try {
    for (const f of [REPO_GW]) if (!fs.existsSync(f)) throw Error('нет ' + f);
    await new Promise((ok, no) => stat.listen(SP, '127.0.0.1', ok).on('error', no));
    fake = spawnPy([path.join(ROOT, 'GATE_FAKE_LLAMA.py'), String(UP)]); if (!await up('http://127.0.0.1:' + UP + '/v1/models')) throw Error('поддельный llama-server не поднялся');
    fake2 = spawnPy([path.join(ROOT, 'GATE_FAKE_LLAMA.py'), String(UPF)]); if (!await up('http://127.0.0.1:' + UPF + '/v1/models')) throw Error('второй поддельный llama-server не поднялся');
    await startGw(); await startGwFast();
    await gatewayDirect();
    const br = await chromium.launch();
    for (const [name, vp] of [['1440x900', { width: 1440, height: 900 }], ['390x844', { width: 390, height: 844 }]]) {
      if (process.env.GATE_VP && process.env.GATE_VP !== name) continue;
      cur = name; if (process.env.GATE_ONLY !== 'menus') { await chat(br, vp); } cur = name; if (process.env.GATE_ONLY !== 'chat') await menus(br, vp);
    }
    await br.close();
  } catch (e) { rec('ВОРОТА: инфраструктура', false, e.message || e); }
  finally { await stopGw(); if (gwf) gwf.kill('SIGKILL'); if (fake) fake.kill('SIGKILL'); if (fake2) fake2.kill('SIGKILL'); stat.close(); }
  const fails = rows.filter(r => !r.ok);
  const md = ['# GATE_REPORT', '', 'Дата: ' + new Date().toISOString() + ' · сборка: ' + ROOT, '', 'Итого: ' + (rows.length - fails.length) + ' PASS / ' + fails.length + ' FAIL из ' + rows.length, '', '| Экран | Пункт | Результат | Детали |', '|---|---|---|---|'].concat(rows.map(r => '| ' + r.vp + ' | ' + r.name.replace(/\|/g, '/') + ' | ' + (r.ok ? 'PASS' : '**FAIL**') + ' | ' + r.detail + ' |'));
  fs.writeFileSync(path.join(ROOT, 'GATE_REPORT.md'), md.join('\n') + '\n');
  console.log('\nИТОГО: ' + (rows.length - fails.length) + ' PASS / ' + fails.length + ' FAIL'); process.exit(fails.length || !rows.length ? 1 : 0);
})();
