/* NOX · общая оболочка: ОДИНАКОВАЯ шапка (бренд, меню, состояние обоих уровней, настройки) и нижнее меню телефона — на всех страницах, включая чат.
   Подключают pages/nox-nav.js (страницы) и nox-wow.js (чат). Без зависимостей. */
export const NAV = [['home', 'Главная', 'index.html'], ['chat', 'Резонанс', 'chat.html'], ['proj', 'Проекты', 'projects.html'], ['mem', 'Память', 'memory.html'], ['train', 'Обучение', 'training.html'], ['core', 'Ядро', 'models.html'], ['sys', 'Система', 'system.html']];
export const MORE = [['cal', 'Календарь', 'calendar.html'], ['cinema', 'Кинозал', 'cinema.html'], ['wid', 'Виджеты', 'widgets.html'], ['disp', 'Диспетчер', 'dispatcher.html'], ['integ', 'Интеграции Диска', 'integrations.html'], ['about', 'О сборке и лицензии', 'about.html']];
export const SET = ['set', 'Настройки', 'settings.html'];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const titleOf = (cur) => (NAV.concat(MORE, [SET]).find((n) => n[0] === cur) || NAV[0])[1];
const link = (n, cur) => '<a href="' + n[2] + '" data-k="' + n[0] + '"' + (n[0] === cur ? ' aria-current="page"' : '') + '>' + n[1] + '</a>';

export function headerHTML(cur) {
  const inMore = MORE.some((n) => n[0] === cur);
  return '<div class="bar-l"><a class="brand" href="index.html" aria-label="NOX HELION, главная"><span class="mark" aria-hidden="true"></span><b>NOX&nbsp;HELION</b><i>' + esc({ about: 'Лицензии', integ: 'Интеграции' }[cur] || titleOf(cur)) + '</i></a></div>'
    + '<nav class="seg nav" id="nav" aria-label="Разделы">' + NAV.map((n) => link(n, cur)).join('')
    + '<button type="button" class="moreb" id="moreB" aria-haspopup="true" aria-expanded="false" aria-controls="moreM"' + (inMore ? ' aria-current="page"' : '') + '>Ещё</button></nav>'
    + '<div class="more-m" id="moreM" role="menu" hidden>' + MORE.map((n) => '<a role="menuitem" href="' + n[2] + '"' + (n[0] === cur ? ' aria-current="page"' : '') + '>' + n[1] + '</a>').join('') + '</div>'
    + '<div class="bar-r"><span class="tiers" id="gwStatus" role="status" aria-label="Состояние уровней ответа">'
    + '<span class="tier" id="tFast" title="Быстрый уровень: проверка"><i class="led"></i><span class="tt mono" data-s="Б">БЫСТРЫЙ</span><span class="ts mono"></span></span>'
    + '<span class="tier" id="tDeep" title="Глубокий уровень (GLM): проверка"><i class="led"></i><span class="tt mono" data-s="GLM">GLM-5.3</span><span class="ts mono"></span></span></span>'
    + '<span class="seg toplink"><a href="chat.html"' + (cur === 'chat' ? ' aria-current="page"' : '') + '>Резонанс</a></span>'
    + '<span class="seg icons"><a href="settings.html" id="hdrSettings" aria-label="Настройки" title="Настройки"' + (cur === 'set' ? ' aria-current="page"' : '') + '><sl-icon library="tabler" name="settings"></sl-icon></a></span></div>';
}
export function mnavHTML(cur) {
  return '<div class="swiper"><div class="swiper-wrapper seg">' + NAV.filter((n) => n[0] !== 'chat').concat(MORE, [SET]).map((n) => '<a class="swiper-slide" href="' + n[2] + '"' + (n[0] === cur ? ' aria-current="page"' : '') + '>' + n[1] + '</a>').join('') + '</div></div>';
}
/* вставляет шапку и нижнее меню; header/mnav уже могут существовать (чат) — тогда их содержимое заменяется */
export function mountShell(app, cur) {
  let bar = document.getElementById('bar');
  if (!bar) { bar = document.createElement('header'); bar.className = 'bar'; bar.id = 'bar'; app.prepend(bar); }
  bar.innerHTML = headerHTML(cur);
  let mn = document.getElementById('mnav');
  if (!mn) { mn = document.createElement('nav'); mn.className = 'mnav'; mn.id = 'mnav'; mn.setAttribute('aria-label', 'Разделы (телефон)'); app.append(mn); }
  mn.innerHTML = mnavHTML(cur);
  const b = document.getElementById('moreB'), m = document.getElementById('moreM');
  const close = () => { m.hidden = true; b.setAttribute('aria-expanded', 'false'); };
  b.addEventListener('click', (e) => { e.stopPropagation(); const open = m.hidden; if (open) { const r = b.getBoundingClientRect(), br = bar.getBoundingClientRect(); m.style.left = Math.max(8, Math.min(innerWidth - 248, r.right - 240 - br.left)) + 'px'; } m.hidden = !open; b.setAttribute('aria-expanded', String(open)); });
  document.addEventListener('click', (e) => { if (!m.contains(e.target)) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  if (cur !== 'chat') import('./nox-mini.js').then((m) => m.mountMini()).catch((e) => console.warn('mini-nox:', e.message));
  return bar;
}

/* ---------- честное состояние ОБОИХ уровней: быстрый (stats.fast_available) и глубокий GLM (/v1/models глубокого сервера) ---------- */
const getj = async (u, ms) => { const c = new AbortController(), t = setTimeout(() => c.abort(), ms || 5000); try { const r = await fetch(u, { cache: 'no-store', signal: c.signal }); if (!r.ok) return { ok: false, why: 'HTTP ' + r.status }; return { ok: true, j: await r.json() }; } catch (e) { return { ok: false, why: String(e.message || e) }; } finally { clearTimeout(t); } };
export const tiers = { fast: { ok: null, why: '' }, deep: { ok: null, id: '', why: '' }, gw: null };
export async function pollTiers() {
  const [m, s] = await Promise.all([getj('/glm/v1/models'), getj('/glm/v1/nox/stats')]);
  const gw = m.ok || s.ok;
  tiers.gw = gw;
  tiers.deep = m.ok && m.j && m.j.data && m.j.data[0] ? { ok: true, id: m.j.data[0].id || 'GLM', why: '' } : { ok: false, id: '', why: m.why || 'нет модели' };
  tiers.fast = s.ok ? { ok: !!s.j.fast_available, why: s.j.fast_available ? '' : 'быстрый сервер не отвечает' } : { ok: false, why: s.why };
  const set = (id, led, txt, title) => { const el = document.getElementById(id); if (!el) return; el.querySelector('.led').className = 'led ' + led; el.querySelector('.ts').textContent = txt; el.title = title; el.setAttribute('aria-label', title); };
  if (!gw) { set('tFast', 'bad', 'ШЛЮЗ НЕДОСТУПЕН', 'Шлюз недоступен: ' + (m.why || s.why)); set('tDeep', 'bad', 'ШЛЮЗ НЕДОСТУПЕН', 'Шлюз недоступен: ' + (m.why || s.why)); }
  else {
    set('tFast', tiers.fast.ok ? 'ok' : 'bad', tiers.fast.ok ? 'ГОТОВ' : 'НЕТ', tiers.fast.ok ? 'Быстрый уровень отвечает' : 'Быстрый уровень недоступен: ' + tiers.fast.why);
    set('tDeep', tiers.deep.ok ? 'ok' : 'warn', tiers.deep.ok ? 'ГОТОВ' : 'НЕ ЗАГРУЖЕН', tiers.deep.ok ? 'Глубокий уровень (GLM) загружен: ' + tiers.deep.id : 'Глубокий уровень (GLM) не загружен: ' + tiers.deep.why + '. Ответы идут быстрым уровнем.');
  }
  window.__noxTiers = tiers; document.dispatchEvent(new CustomEvent('nox:tiers', { detail: tiers }));
  return tiers;
}
export function startTiers() { pollTiers(); return setInterval(pollTiers, 30000); }
