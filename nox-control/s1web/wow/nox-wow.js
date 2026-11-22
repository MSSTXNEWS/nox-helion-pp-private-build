/* NOX WOW · «Резонанс»: один живой чат по центру, остальное - в выдвижных панелях и палитре Ctrl+K.
   Чат: старый протокол POST /api/chat (NDJSON) или шлюз GLM /glm/v1 (SSE). Голос: микрофон -> /stt/transcribe, ответ -> /tts/session (SSE/PCM).
   Библиотеки из /web/vendor: three+postprocessing (nox-wow-bg.js), motion, tsparticles, lottie-web, wavesurfer, driver.js, swiper, Shoelace, Tabler. Каждая подключается отдельно: сбой одной не ломает чат. */
import { PLANETS, byId } from './nox-wow-data.js';
const V = './vendor/';
const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const mem = {};
const ls = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? (k in mem ? mem[k] : d) : v; } catch (e) { return k in mem ? mem[k] : d; } }, set(k, v) { mem[k] = v; try { localStorage.setItem(k, v); } catch (e) { /* нет хранилища */ } } };
const jget = (k, d) => { try { const v = JSON.parse(ls.get(k, 'null')); return v == null ? d : v; } catch (e) { return d; } };
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const small = () => innerWidth <= 760;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8));
const pad = (n) => String(n).padStart(2, '0');
const hhmm = (t) => { const d = new Date(t || Date.now()); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
const loadScript = (src) => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => rej(new Error('не загрузился ' + src)); document.head.appendChild(s); });
const lib = {}; /* состояние подключённых библиотек (для честной диагностики) */
const note = (t, bad) => { const h = $('#hint'); if (!h) return; h.textContent = t; h.style.color = bad ? '#ff9db8' : ''; clearTimeout(note._t); note._t = setTimeout(() => { h.textContent = HINT; h.style.color = ''; }, 7000); };
const HINT = 'ENTER — ОТПРАВИТЬ · SHIFT+ENTER — СТРОКА · CTRL+K — КОМАНДЫ';

/* ---------- настройки ---------- */
const DEF = { proto: 'classic', enter: 'enter', speak: 'on', lang: 'auto', auto: 'off', dens: 'cozy', space: 'on', dust: 'on' };
const cfg = Object.assign({}, DEF, jget('nox.wow.cfg', {}));
const saveCfg = () => ls.set('nox.wow.cfg', JSON.stringify(cfg));
document.body.classList.add('boot');
if (cfg.dens === 'tight') document.body.classList.add('tight');
if (/Chrome\//.test(navigator.userAgent) && window.CSS && CSS.supports && CSS.supports('backdrop-filter', 'url(#nox-lens) blur(2px)')) document.documentElement.classList.add('lens');

/* ---------- диалоги ---------- */
let threads = jget('nox.wow.threads', []).filter((t) => t && Array.isArray(t.msgs));
let cur = null;
const saveThreads = () => { try { ls.set('nox.wow.threads', JSON.stringify(threads.slice(0, 40).map((t) => Object.assign({}, t, { msgs: t.msgs.slice(-80) })))); } catch (e) { /* квота */ } ls.set('nox.wow.cur', cur ? cur.id : ''); };
function newThread() { cur = { id: uid(), title: 'Новый диалог', ts: Date.now(), msgs: [] }; threads.unshift(cur); saveThreads(); renderAll(); }
function openThread(id) { const t = threads.find((x) => x.id === id); if (!t) return; cur = t; ls.set('nox.wow.cur', id); renderAll(); }
const empty = (t) => !t.msgs.length;

/* ---------- разметка сообщений ---------- */
function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
  return s.replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
}
function render(text) {
  const parts = String(text).split(/```/); let out = '';
  parts.forEach((p, i) => {
    if (i % 2) { const nl = p.indexOf('\n'); const code = nl >= 0 ? p.slice(nl + 1) : p; out += '<pre><button type="button" class="copy" data-copy>КОПИЯ</button><code>' + esc(code.replace(/\n$/, '')) + '</code></pre>'; return; }
    p.split(/\n{2,}/).forEach((b) => {
      b = b.replace(/^\n+|\n+$/g, ''); if (!b.trim()) return; const L = b.split('\n');
      if (L.every((l) => /^\s*[-*•]\s+/.test(l))) out += '<ul>' + L.map((l) => '<li>' + inline(l.replace(/^\s*[-*•]\s+/, '')) + '</li>').join('') + '</ul>';
      else if (L.every((l) => /^\s*\d+[.)]\s+/.test(l))) out += '<ol>' + L.map((l) => '<li>' + inline(l.replace(/^\s*\d+[.)]\s+/, '')) + '</li>').join('') + '</ol>';
      else if (/^#{1,4}\s/.test(b)) out += '<p><b>' + inline(b.replace(/^#{1,4}\s+/, '')) + '</b></p>';
      else out += '<p>' + inline(b) + '</p>';
    });
  });
  return out;
}
function splitThink(raw) {
  let ans = raw, i = raw.indexOf('<think>');
  if (i >= 0) { const j = raw.indexOf('</think>', i); ans = j < 0 ? raw.slice(0, i) : raw.slice(0, i) + raw.slice(j + 8); } else { const e = raw.indexOf('</think>'); if (e >= 0) ans = raw.slice(e + 8); }
  return ans.replace(/^\s+/, '');
}

/* ---------- DOM чата ---------- */
const feed = $('#feed'), msgsEl = $('#msgs'), stage = $('#stage'), input = $('#input');
let lottieOk = false;
function lot(container, name, loop) { if (!window.lottie) return null; try { return window.lottie.loadAnimation({ container, renderer: 'svg', loop, autoplay: true, path: './wow/' + name + '.json', rendererSettings: { preserveAspectRatio: 'xMidYMid meet' } }); } catch (e) { return null; } }
function iconBtn(name, label, act) { return '<button type="button" data-act="' + act + '" aria-label="' + label + '" title="' + label + '"><sl-icon library="tabler" name="' + name + '"></sl-icon></button>'; }
function mkMsg(m, idx) {
  const d = document.createElement('div'); d.className = 'm ' + (m.role === 'user' ? 'u' : 'a'); d.dataset.i = idx;
  const lab = m.role === 'user' ? 'ВЫ' : 'NOX';
  d.innerHTML = '<div class="lab mono"><i></i><span>' + lab + '</span><span>' + hhmm(m.ts) + '</span></div><div class="bubble"><div class="txt"></div></div>';
  setTxt(d, m.content, false);
  if (m.role !== 'user') d.appendChild(actsEl());
  return d;
}
function actsEl() { const a = document.createElement('div'); a.className = 'acts'; a.innerHTML = '<span class="seg">' + iconBtn('copy', 'Копировать ответ', 'copy') + iconBtn('refresh', 'Ответить заново', 'regen') + iconBtn('volume', 'Озвучить', 'say') + '</span>'; return a; }
function setTxt(d, text, streaming) { const t = $('.txt', d); t.innerHTML = render(text); t.classList.toggle('caret', !!streaming); }
function nearBottom() { return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 140; }
function toBottom(force) { if (force || nearBottom()) feed.scrollTop = feed.scrollHeight; }
function renderAll() {
  msgsEl.innerHTML = ''; cur.msgs.forEach((m, i) => msgsEl.appendChild(mkMsg(m, i)));
  stage.classList.toggle('has-msgs', cur.msgs.length > 0); document.title = 'NOX HELION · РЕЗОНАНС'; toBottom(true); renderThreads();
}
function renderThreads() {
  const ul = $('#threadList'); if (!ul) return;
  ul.innerHTML = threads.filter((t) => !empty(t) || t === cur).map((t) => '<li class="' + (t === cur ? 'on' : '') + '" data-id="' + t.id + '"><button type="button" class="t" data-open>' + esc(t.title) + '<small>' + new Date(t.ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) + ' · ' + t.msgs.length + ' СООБЩ.</small></button><button type="button" class="x" data-del aria-label="Удалить диалог"><sl-icon library="tabler" name="trash"></sl-icon></button></li>').join('');
}

/* ---------- отправка и потоки ---------- */
let busy = null; /* {ctrl, rid, proto} */
const metrics = { ttft: null, rate: null };
function setBusy(on) { $('#btnSend').hidden = on; $('#btnStop').hidden = !on; $('#composer').classList.toggle('busy', on); }
function histFor(upto) { return cur.msgs.slice(0, upto).filter((m) => m.content && !m.err).slice(-40).map((m) => ({ role: m.role, content: m.content })); }
async function send(text, opts) {
  opts = opts || {}; text = String(text || '').trim(); if (!text || busy) return;
  speaker.prime();
  if (!opts.regen) { cur.msgs.push({ role: 'user', content: text, ts: Date.now() }); if (cur.msgs.length === 1) cur.title = text.replace(/\s+/g, ' ').slice(0, 44); }
  const um = msgsEl.lastElementChild; stage.classList.add('has-msgs');
  if (!opts.regen) msgsEl.appendChild(mkMsg(cur.msgs[cur.msgs.length - 1], cur.msgs.length - 1));
  const am = { role: 'assistant', content: '', ts: Date.now() }; const idx = cur.msgs.length; cur.msgs.push(am);
  const el = mkMsg(am, idx); $('.acts', el) && ($('.acts', el).hidden = true); msgsEl.appendChild(el);
  const th = document.createElement('div'); th.className = 'think mono'; th.innerHTML = '<span class="lt"></span><span>ОЖИДАНИЕ ОТВЕТА</span>'; $('.txt', el).appendChild(th); const anim = lot($('.lt', th), 'lottie-orbit', true);
  toBottom(true); saveThreads(); renderThreads(); input.value = ''; autosize();
  const proto = cfg.proto, rid = uid(), ctrl = new AbortController(); busy = { ctrl, rid, proto }; setBusy(true);
  const t0 = performance.now(); let tFirst = 0, chunks = 0, raw = '', raf = 0, stopped = false, failed = null;
  const history = histFor(idx);
  const say = cfg.speak === 'on' ? speaker.start() : null;
  let spoken = 0;
  const paint = (fin) => { raf = 0; const vis = splitThink(raw); am.content = vis; setTxt(el, vis || (fin ? '' : ''), !fin); if (!vis && !fin) $('.txt', el).appendChild(th); toBottom(false); };
  const onDelta = (s) => {
    if (!s) return; if (!tFirst) { tFirst = performance.now(); anim && anim.destroy(); th.remove(); }
    chunks++; raw += s; if (!raf) raf = requestAnimationFrame(() => paint(false));
    if (say) { const vis = splitThink(raw); const add = vis.slice(spoken); const cut = Math.max(add.lastIndexOf('. '), add.lastIndexOf('! '), add.lastIndexOf('? '), add.lastIndexOf('\n'), add.lastIndexOf(', ')); if (cut >= 24 || add.length > 140) { const k = cut >= 24 ? cut + 1 : add.length; speaker.push(add.slice(0, k)); spoken += k; } }
  };
  try {
    if (proto === 'glm') await streamGlm(history, ctrl, onDelta, (h) => { busy.glmRid = h; });
    else await streamClassic(history, ctrl, rid, onDelta);
  } catch (e) { if (ctrl.signal.aborted) stopped = true; else failed = e; }
  if (raf) cancelAnimationFrame(raf);
  const tEnd = performance.now(); anim && anim.destroy(); th.remove();
  const vis = splitThink(raw); am.content = vis;
  if (failed) { am.err = String(failed.message || failed); setTxt(el, vis, false); $('.bubble', el).classList.add('err'); const e = document.createElement('div'); e.className = 'meta mono'; e.textContent = 'ОШИБКА: ' + am.err; $('.bubble', el).appendChild(e); }
  else { setTxt(el, vis + (stopped ? '' : ''), false); if (stopped) { const e = document.createElement('div'); e.className = 'meta mono'; e.textContent = 'ОСТАНОВЛЕНО' + (vis ? ' · ЧАСТИЧНЫЙ ОТВЕТ' : ''); $('.bubble', el).appendChild(e); } else if (!vis) { setTxt(el, '(пустой ответ)', false); } }
  if (!failed && !stopped && vis) { const mk = document.createElement('span'); mk.className = 'okmark'; $('.lab', el).appendChild(mk); lot(mk, 'lottie-ok', false); }
  if ($('.acts', el)) $('.acts', el).hidden = false;
  if (say) { speaker.push(vis.slice(spoken), true); }
  if (tFirst) { metrics.ttft = tFirst - t0; metrics.rate = chunks / Math.max(.2, (tEnd - tFirst) / 1000); updateEdges(); }
  busy = null; setBusy(false); saveThreads(); renderThreads(); toBottom(false);
}
async function streamClassic(history, ctrl, rid, onDelta) {
  const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctrl.signal, body: JSON.stringify({ model: 'nox-helion:latest', messages: history, stream: true, request_id: rid, options: { num_predict: 2048 } }) });
  if (!r.ok) { let m = 'HTTP ' + r.status; try { const j = await r.json(); m = j.error || j.reason || m; } catch (e) { /* не JSON */ } throw new Error(m); }
  const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', done = false;
  for (;;) {
    const { value, done: d } = await rd.read(); if (d) break; buf += dec.decode(value, { stream: true });
    let k; while ((k = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line) continue; let o; try { o = JSON.parse(line); } catch (e) { continue; }
      if (o.error) throw new Error(o.error); if (o.message && o.message.content) onDelta(o.message.content); if (o.done) done = true;
    }
  }
  if (!done) throw new Error('поток оборвался до завершения');
}
async function streamGlm(history, ctrl, onDelta, onRid) {
  const r = await fetch('/glm/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctrl.signal, body: JSON.stringify({ messages: history, stream: true }) });
  onRid && onRid(r.headers.get('X-NOX-Request-Id'));
  if (!r.ok) { let m = 'HTTP ' + r.status; try { const j = await r.json(); m = (j.error && (j.error.message || j.error)) || m; } catch (e) { /* не JSON */ } throw new Error(m); }
  const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', done = false;
  for (;;) {
    const { value, done: d } = await rd.read(); if (d) break; buf += dec.decode(value, { stream: true });
    let k; while ((k = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line.startsWith('data:')) continue; const p = line.slice(5).trim(); if (p === '[DONE]') { done = true; continue; }
      let j; try { j = JSON.parse(p); } catch (e) { continue; } const c = (j.choices || [{}])[0] || {}; if (c.delta && c.delta.content) onDelta(c.delta.content); if (c.finish_reason) done = true;
    }
  }
  if (!done) throw new Error('поток оборвался до завершения');
}
function stopChat() {
  if (!busy) return; const b = busy; speaker.stop();
  try { if (b.proto === 'classic') fetch('/api/chat/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: b.rid }) }).catch(() => {}); else if (b.glmRid) fetch('/glm/v1/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: b.glmRid }) }).catch(() => {}); } catch (e) { /* stop best effort */ }
  b.ctrl.abort();
}

/* ---------- озвучка (TTS 8094 через /tts/*) ---------- */
const speaker = (() => {
  let all = '', got = 0, fb = 0, ac = null, sess = null, next = 0, srcs = new Set(), pend = '', chain = Promise.resolve(), ctrl = null, on = false, rate = 24000;
  function prime() { try { if (!ac) ac = new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === 'suspended') ac.resume(); } catch (e) { ac = null; } }
  function b64pcm(b64) { const bin = atob(b64), n = bin.length >> 1, f = new Float32Array(n); for (let i = 0; i < n; i++) { let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8); if (v & 0x8000) v -= 0x10000; f[i] = v / 32768; } return f; }
  function play(f, sr) { got++; if (!ac) return; const b = ac.createBuffer(1, f.length, sr), s = ac.createBufferSource(); b.copyToChannel(f, 0); s.buffer = b; s.connect(ac.destination); const t = Math.max(ac.currentTime + .03, next); s.start(t); next = t + b.duration; srcs.add(s); s.onended = () => { srcs.delete(s); if (!srcs.size && !on) setVoiceState(''); }; setVoiceState('ГОВОРИТ'); }
  async function readAudio(id, c) {
    try {
      const r = await fetch('/tts/session/' + id + '/audio?format=sse', { signal: c.signal }); if (!r.ok) throw new Error('TTS HTTP ' + r.status);
      const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '';
      for (;;) { const { value, done } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true }); let k; while ((k = buf.indexOf('\n\n')) >= 0) { const blk = buf.slice(0, k); buf = buf.slice(k + 2); const ln = blk.split('\n').find((l) => l.startsWith('data:')); if (!ln) continue; let e; try { e = JSON.parse(ln.slice(5)); } catch (x) { continue; } if (e.type === 'audio' && e.pcm_b64) play(b64pcm(e.pcm_b64), e.sample_rate || rate); else if (e.type === 'error') note('TTS: ' + (e.error || e.message || 'ошибка синтеза'), true); else if (e.type === 'end' || e.type === 'cancelled') return; } }
    } catch (e) { if (!c.signal.aborted) note('TTS НЕДОСТУПЕН: ' + (e.message || e), true); }
  }
  function start() {
    prime(); stop(true); all = ''; got = 0; clearTimeout(fb); on = true; ctrl = new AbortController(); pend = ''; next = 0; const c = ctrl, lang = cfg.lang === 'auto' ? 'auto' : cfg.lang;
    sess = (async () => { const r = await fetch('/tts/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang }), signal: c.signal }); if (!r.ok) { let m = 'HTTP ' + r.status; try { m = (await r.json()).error || m; } catch (e) { /* не JSON */ } throw new Error(m); } const j = await r.json(); rate = j.out_rate || 24000; readAudio(j.id, c); return j.id; })();
    sess.catch((e) => { if (!c.signal.aborted) note('TTS НЕДОСТУПЕН: ' + (e.message || e), true); on = false; });
    return true;
  }
  function push(text, final) { if (!sess || !on) return; const c = ctrl; all += (text || ''); if (final) { const t = all, g0 = got; clearTimeout(fb); fb = setTimeout(() => { if (got === 0 && t.trim() && window.speechSynthesis) { note('СЕРВЕРНЫЙ ГОЛОС МОЛЧИТ — ГОВОРИТ БРАУЗЕР', true); try { const u = new SpeechSynthesisUtterance(t); u.lang = 'ru-RU'; speechSynthesis.cancel(); speechSynthesis.speak(u); } catch (e) {} } }, 6000); } chain = chain.then(async () => { try { const id = await sess; if (c.signal.aborted) return; await fetch('/tts/session/' + id + '/text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text || '', final: !!final }), signal: c.signal }); } catch (e) { /* сессия отменена или сервис недоступен */ } }); if (final) on = false; }
  function stop(silent) { clearTimeout(fb); try { window.speechSynthesis && speechSynthesis.cancel(); } catch (e) {} const c = ctrl, s = sess; on = false; if (c) c.abort(); ctrl = null; sess = null; chain = Promise.resolve(); if (s) s.then((id) => fetch('/tts/session/' + id + '/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {})).catch(() => {}); srcs.forEach((x) => { try { x.stop(); } catch (e) { /* уже остановлен */ } }); srcs.clear(); next = 0; if (!silent) setVoiceState(''); }
  return { prime, start, push, stop, get active() { return on || srcs.size > 0; } };
})();
let voiceState = '';
function setVoiceState(s) { voiceState = s; updateEdges(); }

/* ---------- микрофон -> STT ---------- */
const mic = { rec: null, ws: null, mr: null, stream: null, t0: 0, tmr: 0, cancelled: false };
async function health(path) { try { const r = await fetch(path, { cache: 'no-store' }); if (!r.ok) return { ok: false, why: 'HTTP ' + r.status }; return { ok: true, j: await r.json() }; } catch (e) { return { ok: false, why: String(e.message || e) }; } }
async function micStart() {
  if (mic.rec) return; speaker.stop();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { note('МИКРОФОН НЕДОСТУПЕН: нужен HTTPS или localhost', true); return; }
  const h = await health('/stt/health');
  if (!h.ok) { note('STT НЕДОСТУПЕН (' + h.why + '): голосовой сервис 8093 не отвечает', true); return; }
  if (h.j && h.j.ready === false) { note('STT НЕ ГОТОВ: ' + (h.j.ready_note || 'нет модели'), true); return; }
  mic.cancelled = false; $('#wavebox').hidden = false; $('#composer').classList.add('rec'); mic.rec = true; mic.t0 = Date.now();
  mic.tmr = setInterval(() => { const s = Math.floor((Date.now() - mic.t0) / 1000); $('#recTime').textContent = pad(Math.floor(s / 60)) + ':' + pad(s % 60); }, 250);
  try {
    const WS = (await import(V + 'wavesurfer.js/dist/wavesurfer.esm.js')).default, Rec = (await import(V + 'wavesurfer.js/dist/plugins/record.esm.js')).default;
    $('#wave').innerHTML = ''; const ws = WS.create({ container: '#wave', waveColor: 'rgba(127,245,239,.8)', progressColor: 'rgba(127,245,239,.8)', height: 44, barWidth: 2, barGap: 3, barRadius: 0, interact: false, cursorWidth: 0 });
    const rec = ws.registerPlugin(Rec.create({ scrollingWaveform: true, scrollingWaveformWindow: 8, renderRecordedAudio: false, mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 64000 }));
    rec.on('record-end', (blob) => { micCleanup(); if (!mic.cancelled) micSend(blob); });
    mic.ws = ws; mic.wsrec = rec; lib.wavesurfer = true; await rec.startRecording();
  } catch (e) {
    if (!mic.rec) return;
    try { /* запасной путь без волны: чистый MediaRecorder */ mic.wsrec = null; const st = await navigator.mediaDevices.getUserMedia({ audio: true }); mic.stream = st; const mt = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''; const mr = new MediaRecorder(st, mt ? { mimeType: mt } : {}); const parts = []; mr.ondataavailable = (ev) => ev.data.size && parts.push(ev.data); mr.onstop = () => { micCleanup(); if (!mic.cancelled) micSend(new Blob(parts, { type: mr.mimeType || 'audio/webm' })); }; mr.start(250); mic.mr = mr; lib.wavesurfer = 'fallback:' + (e.message || e); }
    catch (e2) { micCleanup(); note('МИКРОФОН: ' + (e2.name === 'NotAllowedError' ? 'доступ запрещён' : (e2.message || e2)), true); }
  }
}
function micStop(cancel) { if (!mic.rec) return; mic.cancelled = !!cancel; try { if (mic.wsrec) { mic.wsrec.stopRecording(); } else if (mic.mr && mic.mr.state !== 'inactive') mic.mr.stop(); else micCleanup(); } catch (e) { micCleanup(); } }
function micCleanup() { clearInterval(mic.tmr); mic.rec = null; $('#wavebox').hidden = true; $('#composer').classList.remove('rec'); try { mic.wsrec && mic.wsrec.stopMic && mic.wsrec.stopMic(); } catch (e) { /* уже закрыт */ } try { mic.ws && mic.ws.destroy(); } catch (e) { /* уже закрыт */ } mic.ws = mic.wsrec = mic.mr = null; if (mic.stream) { mic.stream.getTracks().forEach((t) => t.stop()); mic.stream = null; } $('#recTime').textContent = '00:00'; }
async function micSend(blob) {
  if (!blob || blob.size < 800) { note('ЗАПИСЬ СЛИШКОМ КОРОТКАЯ', true); return; }
  note('РАСПОЗНАЮ… ' + Math.round(blob.size / 1024) + ' КБ'); $('#btnMic').disabled = true;
  try {
    const q = '?words=0' + (cfg.lang !== 'auto' ? '&language=' + cfg.lang : '');
    const r = await fetch('/stt/transcribe' + q, { method: 'POST', headers: { 'Content-Type': blob.type || 'audio/webm' }, body: blob });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
    const text = (j.text || '').trim(); if (!text) { note('РЕЧЬ НЕ РАСПОЗНАНА', true); return; }
    input.value = (input.value ? input.value + ' ' : '') + text; autosize(); note('РАСПОЗНАНО · ' + (j.language || '').toUpperCase());
    if (cfg.auto === 'on') send(input.value); else input.focus();
  } catch (e) { note('STT ОШИБКА: ' + (e.message || e), true); } finally { $('#btnMic').disabled = false; }
}

/* ---------- ввод ---------- */
function autosize() { input.style.height = 'auto'; input.style.height = Math.min(200, input.scrollHeight) + 'px'; }
input.addEventListener('input', autosize);
input.addEventListener('keydown', (e) => { if (e.key !== 'Enter' || e.isComposing) return; const ctrlK = e.ctrlKey || e.metaKey; if (cfg.enter === 'enter' ? !e.shiftKey : ctrlK) { e.preventDefault(); send(input.value); } });
$('#form').addEventListener('submit', (e) => { e.preventDefault(); send(input.value); });
$('#btnStop').addEventListener('click', stopChat);
$('#btnMic').addEventListener('click', () => (mic.rec ? micStop(false) : micStart()));
$('#recDone').addEventListener('click', () => micStop(false)); $('#recCancel').addEventListener('click', () => micStop(true));
$('#btnAttach').addEventListener('click', () => $('#file').click());
$('#file').addEventListener('change', async (e) => { const f = e.target.files[0]; e.target.value = ''; if (!f) return; if (f.size > 200 * 1024) { note('ФАЙЛ БОЛЬШЕ 200 КБ', true); return; } const t = await f.text(); input.value += (input.value ? '\n\n' : '') + 'Файл ' + f.name + ':\n```\n' + t + '\n```\n'; autosize(); input.focus(); });
function setSpeak(on) { cfg.speak = on ? 'on' : 'off'; saveCfg(); $('#btnSpeak').setAttribute('aria-pressed', String(on)); if (!on) speaker.stop(); syncOpts(); if (on) { speaker.prime(); note('ОЗВУЧКА ОТВЕТОВ ВКЛ'); } }
$('#btnSpeak').addEventListener('click', () => setSpeak(cfg.speak !== 'on'));
$('#suggest').addEventListener('click', (e) => { const b = e.target.closest('button[data-q]'); if (b) send(b.dataset.q); });
msgsEl.addEventListener('click', async (e) => {
  const cp = e.target.closest('[data-copy]'); if (cp) { try { await navigator.clipboard.writeText($('code', cp.parentElement).textContent); cp.textContent = 'СКОПИРОВАНО'; setTimeout(() => (cp.textContent = 'КОПИЯ'), 1400); } catch (x) { cp.textContent = 'НЕТ ДОСТУПА'; } return; }
  const b = e.target.closest('[data-act]'); if (!b) return; const m = b.closest('.m'), i = +m.dataset.i, msg = cur.msgs[i];
  if (b.dataset.act === 'copy') { try { await navigator.clipboard.writeText(msg.content); note('СКОПИРОВАНО'); } catch (x) { note('БУФЕР ОБМЕНА НЕДОСТУПЕН', true); } }
  else if (b.dataset.act === 'say') { if (speaker.active) { speaker.stop(); return; } speaker.start(); speaker.push(msg.content, true); }
  else if (b.dataset.act === 'regen' && !busy && i === cur.msgs.length - 1) { cur.msgs.pop(); m.remove(); send('(повтор)', { regen: true }); }
});

/* ---------- статусы, часы, края ---------- */
function tick() { const d = new Date(); $('#clock').textContent = pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); }
let gw = { ok: null, model: '', why: '' }, stt = null, tts = null;
async function pollGw() {
  const h = await health('/glm/v1/models'); const led = $('#gwLed'), tx = $('#gwText');
  if (h.ok) { gw = { ok: true, model: ((h.j.data || [])[0] || {}).id || 'GLM', why: '' }; led.className = 'led ok'; tx.textContent = 'GLM-5.3 · ОНЛАЙН'; }
  else { gw = { ok: false, model: '', why: h.why }; led.className = 'led bad'; tx.textContent = 'ШЛЮЗ НЕДОСТУПЕН'; }
  updateEdges();
}
async function pollVoice() { const a = await health('/stt/health'), b = await health('/tts/health'); stt = a.ok ? { ready: a.j.ready !== false, note: a.j.ready_note, model: (a.j.model && (a.j.model.name || a.j.model.model)) || '' } : { ready: false, note: a.why, down: true }; tts = b.ok ? { ready: b.j.ready !== false, note: b.j.ready_note, backends: ((b.j.backends || []).filter((x) => x.available).map((x) => x.name)).join('+') } : { ready: false, note: b.why, down: true }; updateEdges(); }
function updateEdges() {
  $('#eModel').textContent = 'МОДЕЛЬ ' + (gw.ok ? gw.model.toUpperCase() : '—'); $('#eProto').textContent = 'ПРОТОКОЛ ' + (cfg.proto === 'glm' ? 'GLM /v1' : 'API /chat');
  $('#eTtft').textContent = 'ТТФТ ' + (metrics.ttft == null ? '—' : (metrics.ttft / 1000).toFixed(2) + ' С'); $('#eRate').textContent = 'ЧАНК/С ' + (metrics.rate == null ? '—' : metrics.rate.toFixed(1));
  $('#eVoice').textContent = voiceState ? 'ГОЛОС · ' + voiceState : 'ГОЛОС STT ' + (stt == null ? '…' : stt.ready ? '●' : '○') + ' TTS ' + (tts == null ? '…' : tts.ready ? '●' : '○');
  const vs = $('#voiceStat'); if (vs) vs.textContent = 'STT ' + (stt == null ? 'ПРОВЕРКА' : stt.ready ? 'ГОТОВ' + (stt.model ? ' · ' + stt.model : '') : (stt.down ? 'НЕ ЗАПУЩЕН' : 'НЕ ГОТОВ')) + ' · TTS ' + (tts == null ? 'ПРОВЕРКА' : tts.ready ? 'ГОТОВ' + (tts.backends ? ' · ' + tts.backends : '') : (tts.down ? 'НЕ ЗАПУЩЕН' : 'НЕ ГОТОВ'));
}

/* ---------- настройки / панели ---------- */
const open = (el) => (el.show ? el.show() : el.setAttribute('open', '')), close = (el) => (el.hide ? el.hide() : el.removeAttribute('open'));
function syncOpts() { $$('.opt').forEach((g) => { const v = cfg[g.dataset.opt]; $$('button', g).forEach((b) => b.setAttribute('aria-checked', String(b.dataset.v === v))); }); $('#btnSpeak').setAttribute('aria-pressed', String(cfg.speak === 'on')); }
let space = null;
function applyOpt(k) {
  saveCfg(); syncOpts();
  if (k === 'dens') document.body.classList.toggle('tight', cfg.dens === 'tight');
  if (k === 'space') { if (space) space.setLevel(cfg.space); }
  if (k === 'dust') dust();
  if (k === 'speak' && cfg.speak === 'off') speaker.stop(); if (k === 'speak' && cfg.speak === 'on') speaker.prime();
  if (k === 'proto') updateEdges();
}
$$('.opt').forEach((g) => g.addEventListener('click', (e) => { const b = e.target.closest('button[data-v]'); if (!b) return; cfg[g.dataset.opt] = b.dataset.v; applyOpt(g.dataset.opt); }));
let MF = null; const PLX = {}; async function buildPlanets() {
  try { const r = await fetch(V + 'nox-planets/manifest.json', { cache: 'no-store' }); if (r.ok) MF = new Set((await r.json()).files || []); } catch (e) { /* без манифеста - только градиенты */ }
  const box = $('#planets'); box.innerHTML = ''; const cur = ls.get('nox:planet', 'earth');
  PLANETS.forEach((p) => { const b = document.createElement('button'); b.type = 'button'; b.setAttribute('role', 'radio'); b.dataset.id = p.id; b.setAttribute('aria-checked', String(p.id === cur)); const pr = p.proc || { base: [.1, .12, .2], hi: [.3, .35, .5] }, c1 = pr.hi.map((x) => Math.round(x * 255)).join(','), c2 = pr.base.map((x) => Math.round(x * 255)).join(','); const has = p.tex && MF && p.tex.find((n) => MF.has(n)), tex = has ? 'url(' + V + 'nox-planets/' + has + '),' : ''; b.innerHTML = '<i class="pb" style="background-image:' + tex + 'radial-gradient(circle at 35% 30%,rgb(' + c1 + '),rgb(' + c2 + '))"></i><span>' + p.name + '</span>'; box.appendChild(b); PLX[p.id] = b; });
  $('#planetNote').textContent = byId(cur).note ? '' : '';
}
function pickPlanet(id) { $$('#planets button').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.id === id))); if (space) space.setPlanet(id); else if (window.NOXPlanet) window.NOXPlanet.set(id); else ls.set('nox:planet', id); const st = space && space.state.texStatus[id]; $('#planetNote').textContent = id === 'none' ? '' : (st ? (st.startsWith('photo') ? 'ТЕКСТУРА: ' + st.replace('photo:', '') + ' · Solar System Scope, CC BY 4.0' : 'ТЕКСТУРА НЕ НАЙДЕНА НА СЕРВЕРЕ — ПРОЦЕДУРНАЯ ЗАПАСНАЯ') : ''); }
$('#planets').addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (!b) return; pickPlanet(b.dataset.id); setTimeout(() => { const st = space && space.state.texStatus[b.dataset.id]; if (st) $('#planetNote').textContent = st.startsWith('photo') ? 'ТЕКСТУРА: ' + st.replace('photo:', '') + ' · SOLAR SYSTEM SCOPE, CC BY 4.0' : 'ТЕКСТУРА НЕ НАЙДЕНА — ПРОЦЕДУРНАЯ ЗАПАСНАЯ'; }, 900); });
$('#btnSettings').addEventListener('click', () => { open($('#drSettings')); pollVoice(); });
$('#btnThreads').addEventListener('click', () => { renderThreads(); open($('#drThreads')); });
$('#thNew').addEventListener('click', () => { if (!empty(cur)) newThread(); close($('#drThreads')); input.focus(); });
$('#threadList').addEventListener('click', (e) => { const li = e.target.closest('li'); if (!li) return; if (e.target.closest('[data-del]')) { threads = threads.filter((t) => t.id !== li.dataset.id); if (cur.id === li.dataset.id) { if (!threads.length) newThread(); else cur = threads[0]; } saveThreads(); renderAll(); return; } if (e.target.closest('[data-open]')) { openThread(li.dataset.id); close($('#drThreads')); } });
$('#btnClassic').addEventListener('click', () => { location.href = 'classic/chat.html'; });
$('#btnTour').addEventListener('click', () => { close($('#drSettings')); setTimeout(() => tour(true), 450); });

/* ---------- палитра Ctrl+K ---------- */
const PAGES = [['Главная', 'index.html'], ['Проекты', 'projects.html'], ['Память', 'memory.html'], ['Обучение', 'training.html'], ['Ядро NOX', 'models.html'], ['Система', 'system.html'], ['Установка', 'install.html'], ['Виджеты', 'widgets.html'], ['Кинотеатр', 'cinema.html'], ['Диспетчер задач', 'dispatcher.html'], ['Загрузки', 'downloads.html'], ['Настройки (страница)', 'settings.html']];
function commands() {
  const c = [
    { g: 'Чат', t: 'Новый диалог', run: () => { if (!empty(cur)) newThread(); input.focus(); } },
    { g: 'Чат', t: 'История диалогов', run: () => { renderThreads(); open($('#drThreads')); } },
    { g: 'Чат', t: 'Остановить ответ', run: stopChat },
    { g: 'Чат', t: 'Протокол: шлюз GLM-5.3 /glm/v1', run: () => { cfg.proto = 'glm'; applyOpt('proto'); } },
    { g: 'Чат', t: 'Протокол: классический /api/chat', run: () => { cfg.proto = 'classic'; applyOpt('proto'); } },
    { g: 'Голос', t: 'Записать голосом (микрофон)', run: () => (mic.rec ? micStop(false) : micStart()) },
    { g: 'Голос', t: 'Озвучка ответов: включить / выключить', run: () => setSpeak(cfg.speak !== 'on') },
    { g: 'Голос', t: 'Остановить озвучку', run: () => speaker.stop() },
    { g: 'Вид', t: 'Открыть настройки', run: () => { open($('#drSettings')); pollVoice(); } },
    { g: 'Вид', t: 'Космос: ярко / мягко / стоп', run: () => { const o = ['on', 'high', 'off']; cfg.space = o[(o.indexOf(cfg.space) + 1) % 3]; applyOpt('space'); note('КОСМОС: ' + { on: 'МЯГКО', high: 'ЯРКО', off: 'СТОП' }[cfg.space]); } },
    { g: 'Вид', t: 'Тур по интерфейсу', run: () => setTimeout(() => tour(true), 300) },
    { g: 'Панели', t: 'Классический чат: промпты, прогресс задач, режим судей, пять миров', run: () => { location.href = 'classic/chat.html'; } },
    { g: 'NOX SPACE', t: 'Погода, валюта, новости, кинотеатр, книги, браузер', run: () => universe() }
  ];
  PLANETS.forEach((p) => c.push({ g: 'Планета', t: p.name, run: () => pickPlanet(p.id) }));
  PAGES.forEach((p) => c.push({ g: 'Страницы', t: p[0], run: () => { location.href = p[1]; } }));
  return c;
}
let palSel = 0, palItems = [];
function palRender() { const q = $('#palInput').value.trim().toLowerCase(), toks = q.split(/\s+/).filter(Boolean); palItems = commands().filter((c) => toks.every((t) => (c.g + ' ' + c.t).toLowerCase().includes(t))); palSel = Math.min(palSel, Math.max(0, palItems.length - 1)); $('#palList').innerHTML = palItems.length ? palItems.map((c, i) => '<li role="option" data-i="' + i + '" aria-selected="' + (i === palSel) + '"><span class="g">' + esc(c.g) + '</span><span>' + esc(c.t) + '</span></li>').join('') : '<li class="g" style="cursor:default">НИЧЕГО НЕ НАЙДЕНО</li>'; const s = $('#palList [aria-selected=true]'); s && s.scrollIntoView({ block: 'nearest' }); }
function palOpen() { const d = $('#dlPalette'); $('#palInput').value = ''; palSel = 0; palRender(); open(d); setTimeout(() => $('#palInput').focus(), 120); }
function palRun(i) { const c = palItems[i]; if (!c) return; close($('#dlPalette')); setTimeout(() => c.run(), 60); }
$('#palInput').addEventListener('input', () => { palSel = 0; palRender(); });
$('#palInput').addEventListener('keydown', (e) => { if (e.key === 'ArrowDown') { e.preventDefault(); palSel = Math.min(palItems.length - 1, palSel + 1); palRender(); } else if (e.key === 'ArrowUp') { e.preventDefault(); palSel = Math.max(0, palSel - 1); palRender(); } else if (e.key === 'Enter') { e.preventDefault(); palRun(palSel); } });
$('#palList').addEventListener('click', (e) => { const li = e.target.closest('li[data-i]'); if (li) palRun(+li.dataset.i); });
$('#btnPalette').addEventListener('click', palOpen);
addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); palOpen(); return; }
  if (e.key === 'Escape' && busy && !$('#dlPalette').open && !$('#drSettings').open) { stopChat(); }
  if (e.key === '/' && document.activeElement === document.body) { e.preventDefault(); input.focus(); }
});

/* ---------- NOX SPACE (готовый модуль Диска V19: погода, валюта, новости, кинотеатр, книги, браузер) ---------- */
async function universe() {
  try {
    if (!window.NOX_UNIVERSE_V19) { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = './nox-universe-v19.css'; document.head.appendChild(l); await loadScript('./nox-universe-v19.js'); await new Promise((r) => setTimeout(r, 80)); }
    window.NOX_UNIVERSE_V19 ? window.NOX_UNIVERSE_V19.open('Погода') : note('NOX SPACE НЕ ЗАГРУЗИЛСЯ', true);
  } catch (e) { note('NOX SPACE: ' + (e.message || e), true); }
}

/* ---------- тур driver.js ---------- */
async function tour(force) {
  if (!force && ls.get('nox.wow.tour', '') === '1') return;
  try {
    const { driver } = await import(V + 'driver.js/dist/driver.js.mjs');
    const steps = [
      { element: '#composer', popover: { title: 'Чат', description: 'Пишите сюда. Enter отправляет, Shift+Enter — новая строка. STOP останавливает ответ.' } },
      { element: '#btnMic', popover: { title: 'Голос', description: 'Запись с микрофона уходит в распознавание (STT), текст появляется в поле. Озвучка ответа включается кнопкой рядом.' } },
      { element: small() ? '#btnPalette' : '#btnPalette', popover: { title: 'Команды Ctrl+K', description: 'Все остальное спрятано здесь: страницы, планеты, протокол, классический чат со всеми панелями.' } },
      { element: '#btnSettings', popover: { title: 'Настройки', description: 'Планета за интерфейсом, яркость космоса, голос, протокол чата, плотность.' } }
    ];
    const d = driver({ showProgress: true, allowClose: true, popoverClass: 'nox-tour', nextBtnText: 'Далее', prevBtnText: 'Назад', doneBtnText: 'Готово', progressText: '{{current}} / {{total}}', steps, onDestroyed: () => ls.set('nox.wow.tour', '1') });
    lib.driver = true; d.drive();
  } catch (e) { lib.driver = 'ERR ' + (e.message || e); }
}

/* ---------- частицы-пыль (tsparticles) ---------- */
let dustC = null;
async function dust() {
  if (dustC) { try { dustC.destroy(); } catch (e) { /* уже убрана */ } dustC = null; $('#dust').innerHTML = ''; }
  if (cfg.dust !== 'on' || reduce) return;
  try {
    if (!window.tsParticles) await loadScript(V + 'tsparticles/tsparticles.bundle.min.js');
    dustC = await window.tsParticles.load({ id: 'dust', options: { fullScreen: { enable: false }, background: { color: 'transparent' }, fpsLimit: 30, detectRetina: false, particles: { number: { value: small() ? 16 : 38 }, color: { value: ['#9ff7f2', '#ffffff', '#ffd9a0'] }, opacity: { value: { min: .06, max: .4 }, animation: { enable: true, speed: .35, sync: false } }, size: { value: { min: .5, max: 1.5 } }, move: { enable: true, speed: .14, direction: 'none', random: true, straight: false, outModes: { default: 'out' } }, shape: { type: 'circle' } }, interactivity: { events: { onHover: { enable: false }, onClick: { enable: false } } } } });
    lib.tsparticles = true;
  } catch (e) { lib.tsparticles = 'ERR ' + (e.message || e); }
}

/* ---------- старт ---------- */
async function boot() {
  const id = ls.get('nox.wow.cur', ''); cur = threads.find((t) => t.id === id) || threads.find((t) => !empty(t)) || null; if (!cur) newThread(); else renderAll();
  syncOpts(); buildPlanets(); tick(); setInterval(tick, 1000); autosize(); updateEdges();
  /* оболочка Shoelace (стеклянные drawer/dialog/tooltip) + иконки Tabler */
  try {
    const [bp, il] = await Promise.all([import(V + 'shoelace/cdn/utilities/base-path.js'), import(V + 'shoelace/cdn/utilities/icon-library.js')]);
    bp.setBasePath(new URL(V + 'shoelace/cdn', location.href).href); il.registerIconLibrary('tabler', { resolver: (n) => new URL(V + 'tabler-icons/icons/outline/' + n + '.svg', location.href).href });
    await import(V + 'shoelace/cdn/shoelace-autoloader.js'); lib.shoelace = true;
  } catch (e) { lib.shoelace = 'ERR ' + (e.message || e); }
  document.body.classList.remove('boot');
  /* motion: плавное «киношное» появление */
  try { await loadScript(V + 'motion/dist/motion.js'); const A = window.Motion && window.Motion.animate; lib.motion = !!A; if (A && !reduce) { A($$('.bar, .hero > *, .dock'), { opacity: [0, 1], filter: ['blur(8px)', 'blur(0px)'], transform: ['translateY(10px)', 'translateY(0px)'] }, { duration: .9, delay: window.Motion.stagger ? window.Motion.stagger(.08) : 0, ease: [.22, .8, .2, 1] }); } } catch (e) { lib.motion = 'ERR ' + (e.message || e); }
  loadScript(V + 'lottie-web/build/player/lottie.min.js').then(() => { lib.lottie = true; }).catch((e) => { lib.lottie = 'ERR ' + e.message; });
  /* космос: один WebGL-контекст three; запасной путь - прежние nox-v14-real / nox-v14-planet */
  import('./nox-wow-bg.js').then((m) => m.startSpace({ canvas: $('#space') })).then((s) => { space = s; s.setLevel(cfg.space); lib.three = 'ok'; window.__noxSpace = s; })
    .catch(async (e) => { lib.three = 'FALLBACK ' + (e.message || e); $('#space').remove(); document.body.classList.add('bgfallback'); try { await loadScript('./nox-v14-real.js'); await loadScript('./nox-v14-planet.js'); } catch (x) { /* без фона */ } });
  dust();
  /* нижнее меню-ползунок на телефоне */
  if (small()) import(V + 'swiper/swiper-bundle.min.mjs').then((m) => { const S = m.default || m.Swiper; const s = new S('.mnav .swiper', { slidesPerView: 'auto', freeMode: true, spaceBetween: 0, resistanceRatio: .6, centeredSlides: true, centeredSlidesBounds: true, initialSlide: 1 }); s.slideTo(1, 0); lib.swiper = true; }).catch((e) => { lib.swiper = 'ERR ' + e.message; });
  pollGw(); setInterval(pollGw, 30000); pollVoice(); setInterval(pollVoice, 60000);
  setTimeout(() => tour(false), 1600);
  window.__noxWow = { cfg, lib, get cur() { return cur; }, send, speaker, mic };
  input.focus({ preventScroll: true });
}
boot();
