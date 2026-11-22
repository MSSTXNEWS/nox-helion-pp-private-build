/* NOX · общие помощники страниц: запросы к API NOX с честными ошибками, опрос служб, хранилище. Выдуманных данных нет. */
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } },
  json(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  setJson(k, v) { return ls.set(k, JSON.stringify(v)); }
};
export const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
export const basisRu = (b) => (b === 'default' ? 'оценка по умолчанию' : /^measured:(\d+)/.test(b) ? 'измерено по ' + b.split(':')[1] + ' запр.' : 'измерено');
export const pad = (n) => String(n).padStart(2, '0');
export const hhmmss = (d = new Date()) => pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
export const ymd = (d) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());

/* запрос: никогда не бросает исключение; error - готовая русская фраза */
export async function call(url, o = {}) {
  const { method = 'GET', body, timeout = 7000 } = o, t0 = performance.now(), ctl = new AbortController(), to = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, { method, signal: ctl.signal, cache: 'no-store', headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined, body: body !== undefined ? JSON.stringify(body) : undefined });
    const ms = Math.round(performance.now() - t0); let text = '', data = null;
    try { text = await r.text(); data = text ? JSON.parse(text) : null; } catch (e) { /* не JSON */ }
    if (!r.ok) return { ok: false, status: r.status, ms, data, text, error: 'HTTP ' + r.status + (data && data.error ? ': ' + String(data.error).slice(0, 200) : '') };
    return { ok: true, status: r.status, ms, data, text };
  } catch (e) {
    return { ok: false, status: 0, ms: Math.round(performance.now() - t0), error: e && e.name === 'AbortError' ? 'нет ответа за ' + Math.round(timeout / 1000) + ' с' : 'сеть недоступна: ' + (e && e.message || e) };
  } finally { clearTimeout(to); }
}
export const memory = (req) => call('/memory/api', { method: 'POST', body: req });

/* опрос всех служб NOX: шлюз, глубокий и быстрый тир, память, голос (STT/TTS), панель S2 */
/* панель S2 (/api/*): проверяем не чаще раза в 10 минут (результат общий для страниц), чтобы не засорять консоль повторными 503 */
export async function apiProbe(force) {
  const c = ls.json('nox.apiprobe', null);
  if (!force && c && Date.now() - c.t < 600000) return c.r;
  const r = await call('/api/health', { timeout: 4000 }); const s2 = r.ok && !(r.data && r.data.panel_s2 === false); /* веб S1 отвечает /api/health сам: это не панель S2 */
  const s = { ok: s2, status: r.status, ms: r.ms, error: s2 ? r.error : (r.ok ? 'панель S2 не подключена (отвечает только веб-сервер S1)' : r.error), data: r.ok ? r.data : null };
  ls.setJson('nox.apiprobe', { t: Date.now(), r: s }); return s;
}
export async function probeAll(force) {
  const [stats, models, mem, stt, tts, api] = await Promise.all([call('/glm/v1/nox/stats'), call('/glm/v1/models'), call('/memory/health'), call('/stt/health'), call('/tts/health'), apiProbe(force)]);
  const S = stats.ok && stats.data ? stats.data : null, sv = [];
  const pct = (x) => (x == null ? '—' : Math.round(x * 100) + '%');
  sv.push({ id: 'gw', name: 'Шлюз GLM', sub: '/glm → gateway.py', state: S ? 'ok' : 'bad', ms: stats.ms, error: S ? '' : stats.error || 'пустой ответ',
    lines: S ? ['активных запросов: ' + (S.active || []).length, 'кэш префикса: ' + (S.cache && S.cache.hit_ratio != null ? pct(S.cache.hit_ratio) + ' (' + S.cache.requests + ' запр.)' : 'ещё нет запросов')] : [] });
  const mid = models.ok && models.data && Array.isArray(models.data.data) ? models.data.data.map((m) => m.id) : null;
  sv.push({ id: 'deep', name: 'Глубокий тир', sub: 'основная модель', state: mid && mid.length ? 'ok' : 'bad', ms: models.ms, error: mid && mid.length ? '' : (!S ? 'шлюз недоступен: ' : '') + (models.error || 'шлюз не вернул ни одной модели'),
    lines: mid ? ['модель: ' + mid.join(', '), S && S.speed && S.speed.deep ? 'скорость: ' + S.speed.deep.tps + ' ток/с (' + basisRu(S.speed.deep.basis) + ')' : ''].filter(Boolean) : [] });
  sv.push({ id: 'fast', name: 'Быстрый тир', sub: 'малая модель', state: !S ? 'bad' : S.fast_available ? 'ok' : 'warn', ms: stats.ms, error: !S ? 'шлюз недоступен: ' + stats.error : S.fast_available ? '' : 'быстрый тир не подключён или не отвечает (fast_available=false)',
    lines: S && S.fast_available && S.speed && S.speed.fast ? ['скорость: ' + S.speed.fast.tps + ' ток/с (' + basisRu(S.speed.fast.basis) + ')'] : [] });
  const M = mem.ok && mem.data && mem.data.ok ? mem.data.stats : null;
  sv.push({ id: 'mem', name: 'Память', sub: '/memory → recall_api', state: M ? 'ok' : 'bad', ms: mem.ms, error: M ? '' : mem.error || 'служба памяти ответила без статистики',
    lines: M ? ['фактов: ' + M.facts + ' · эпизодов: ' + M.episodes + ' · профиль: ' + M.profile, 'правок в журнале: ' + M.changes + ' · FTS5: ' + (M.fts5 ? 'да' : 'нет')] : [] });
  const voice = (id, name, sub, r, extra) => { const d = r.ok && r.data ? r.data : null; sv.push({ id, name, sub, state: !d ? 'bad' : d.ready === false ? 'warn' : 'ok', ms: r.ms, error: !d ? r.error : d.ready === false ? (d.ready_note || 'сервис запущен, но не готов') : '', lines: d ? extra(d) : [] }); };
  voice('stt', 'Распознавание (STT)', '/stt → faster-whisper', stt, (d) => [d.model && (d.model.name || d.model.model) ? 'модель: ' + (d.model.name || d.model.model) : '', 'сессий: ' + (d.sessions == null ? '—' : d.sessions)].filter(Boolean));
  voice('tts', 'Озвучка (TTS)', '/tts → XTTS/Piper', tts, (d) => { const b = (d.backends || []).filter((x) => x.available).map((x) => x.name); return [b.length ? 'движки: ' + b.join(', ') : 'нет доступных движков'].concat(d.out_rate ? ['частота: ' + d.out_rate + ' Гц'] : []); });
  sv.push({ id: 'api', name: 'Панель S2 (/api)', sub: 'задачи, обучение, метрики ПК', state: api.ok ? 'ok' : 'warn', ms: api.ms, error: api.ok ? '' : 'не подключена: ' + api.error, lines: [] });
  return { stats, models, mem, stt, tts, api, services: sv };
}
export const ST_RU = { ok: 'В СТРОЮ', warn: 'ВНИМАНИЕ', bad: 'НЕДОСТУПНО' };
export function download(name, text, type = 'application/json') {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: type + ';charset=utf-8' })); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
let tt = 0;
export function toast(msg, bad) {
  let box = $('#toasts'); if (!box) { box = el('<div id="toasts" aria-live="polite"></div>'); document.body.appendChild(box); }
  const t = el('<div class="toast' + (bad ? ' bad' : '') + '">' + esc(msg) + '</div>'); box.appendChild(t); setTimeout(() => t.remove(), bad ? 7000 : 3500); tt++;
}
