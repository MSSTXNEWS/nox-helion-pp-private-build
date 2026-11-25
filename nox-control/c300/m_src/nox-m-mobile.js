/* NOX · M: мобильный UX (таб-бар, шторка «Ещё», кнопка ИИ, свайп назад, pull-to-refresh, фиксы целей/шрифта). Активен только при ширине <=768. */
(() => {
  if (window.__noxM) return; window.__noxM = 1;
  const mq = matchMedia('(max-width:768px)');
  const $ = (s, r = document) => r.querySelector(s);
  const ic = (n) => '<sl-icon library="tabler" name="' + n + '"></sl-icon>';
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const CHAT = /chat\.html$/.test(location.pathname);
  const cur = (location.pathname.split('/').pop() || 'index.html').replace(/\.main\.html$/, '.html');
  if (mq.matches && cur === 'index.html' && !/[?&]home/.test(location.search) && !sessionStorage.getItem('nox_m_home')) { sessionStorage.setItem('nox_m_home', '1'); location.replace('./chat.html'); return; }
  const hap = (t) => { try { const h = window.iosHaptics || window.NOX_ios_haptics || window.haptic; if (typeof h === 'function') h(); else if (h && h.haptic) h.haptic(); else navigator.vibrate && navigator.vibrate(t || 8); } catch (e) { /* без haptics */ } };
  const MAIN = [['chat.html', 'Чат', 'message-circle'], ['index.html?home=1', 'Главная', 'home-2'], ['assistant.html', 'Помощник', 'checklist'], ['studio.html', 'Ателье', 'brush']];
  let built = false, nav = null, openSheet = null, scrim = null;
  const closeSheet = () => { if (!openSheet) return; openSheet.classList.remove('open'); scrim.classList.remove('open'); const s = openSheet; openSheet = null; setTimeout(() => s.remove(), 300); };
  const sheet = (html) => {
    closeSheet();
    const s = document.createElement('div'); s.className = 'nox-m-sheet'; s.innerHTML = '<div class="m-handle"></div>' + html; document.body.appendChild(s);
    requestAnimationFrame(() => { s.classList.add('open'); scrim.classList.add('open'); }); openSheet = s; hap();
    let y0 = null, dy = 0;
    s.addEventListener('touchstart', (e) => { if (s.scrollTop <= 0) { y0 = e.touches[0].clientY; dy = 0; } }, { passive: true });
    s.addEventListener('touchmove', (e) => { if (y0 == null) return; dy = e.touches[0].clientY - y0; if (dy > 0) { s.style.transition = 'none'; s.style.transform = 'translateY(' + dy + 'px)'; } }, { passive: true });
    s.addEventListener('touchend', () => { s.style.transition = ''; s.style.transform = ''; if (y0 != null && dy > 90) closeSheet(); y0 = null; });
    return s;
  };
  const loadNav = async () => { if (nav) return nav; try { nav = await (await fetch('./nav.json', { cache: 'no-cache' })).json(); } catch (e) { nav = { groups: [] }; } return nav; };
  const more = async () => {
    const n = await loadNav(); let h = '<h3>Все разделы</h3><div class="m-grid">';
    (n.groups || []).forEach((g) => { h += '<div class="m-grp">' + esc(g.group) + '</div>'; (g.items || []).forEach((i) => { h += '<a href="./' + esc(i.file) + '" class="' + (i.file === cur ? 'on' : '') + '">' + ic(i.icon || 'apps') + '<span>' + esc(i.name) + '</span></a>'; }); });
    sheet(h + '</div>');
  };
  const ask = () => {
    const acts = [['.nmc-fab', 'Диалог с NOX', 'message-circle'], ['.nai-btn', 'NOX, кратко о странице', 'sparkles'], ['#nxmPill', 'Справка', 'help-circle'], ['#nxnavx', 'Навигатор', 'compass']].filter((a) => $(a[0]));
    if (acts.length === 1) { hap(); $(acts[0][0]).click(); return; }
    const s = sheet('<h3>NOX</h3><div class="m-list">' + acts.map((a, i) => '<button data-i="' + i + '">' + ic(a[2]) + ' ' + esc(a[1]) + '</button>').join('') + '</div>');
    s.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { const t = $(acts[+b.dataset.i][0]); closeSheet(); setTimeout(() => t && t.click(), 200); }));
  };
  const proxyList = (title, items) => { // items: [группа, подпись, элемент]
    let h = '<h3>' + esc(title) + '</h3><div class="m-list">', g = ''; items.forEach((it, i) => { if (it[0] !== g) { g = it[0]; h += '<div class="m-grp">' + esc(g) + '</div>'; } h += '<button data-i="' + i + '">' + esc(it[1]) + '</button>'; });
    const s = sheet(h + '</div>'); s.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => { const el = items[+b.dataset.i][2]; closeSheet(); setTimeout(() => el.click(), 220); }));
  };
  const dialogs = () => { const b = $('#btnThreads'); if (b) b.click(); else sheet('<h3>Диалоги</h3><p>Список диалогов недоступен.</p>'); };
  const commands = () => {
    const it = []; const lab = (e) => (e.textContent || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    document.querySelectorAll('.lv-dd sl-menu-item').forEach((e) => it.push(['Память и режимы', lab(e), { click: () => { if (e.type === 'checkbox') e.checked = !e.checked; const m = e.closest('sl-menu'); if (m) m.dispatchEvent(new CustomEvent('sl-select', { bubbles: true, detail: { item: e } })); else e.click(); } }]));
    document.querySelectorAll('.lv-tag').forEach((e) => it.push(['Теги', lab(e), e]));
    
    [['.nai-btn', 'NOX, …'], ['#nuiVoice', 'Голос'], ['#nuiFlow', 'Карта мышления'], ['#btnPalette', 'Палитра'], ['#btnSettings', 'Настройки чата'], ['#nxsun', 'Пульт NOX']].forEach((a) => { const e = $(a[0]); if (e) it.push(['Функции', a[1], e]); });
    proxyList('Команды', it);
  };
  const tpls = () => { const it = []; document.querySelectorAll('#cxChips button').forEach((e) => it.push(['Заготовки', e.textContent.trim(), e])); const w = $('#tgWid'); if (w) it.push(['Система', 'Виджеты и статус', w]); [['#nxmPill', 'Справка'], ['#nxnavx', 'Навигатор'], ['#tbBell', 'Уведомления']].forEach((a) => { const e = $(a[0]); if (e) it.push(['Система', a[1], e]); }); proxyList('Заготовки и система', it); };
  const build = () => {
    if (built) return; built = true;
    scrim = document.createElement('div'); scrim.id = 'nox-m-scrim'; scrim.addEventListener('click', closeSheet); document.body.appendChild(scrim);
    const t = document.createElement('nav'); t.id = 'nox-m-tab'; t.setAttribute('aria-label', 'Основная навигация');
    if (CHAT) { document.body.classList.add('m-chat'); }
    const CT = [['chat.html', 'Чат', 'message-circle'], ['#dlg', 'Диалоги', 'messages'], ['#cmd', 'Команды', 'terminal-2'], ['#tpl', 'Заготовки', 'template']];
    t.innerHTML = (CHAT ? CT : MAIN).map((m) => '<a href="' + (m[0][0] === '#' ? m[0] : './' + m[0]) + '" class="' + (m[0] === cur || (CHAT && m[0] === 'chat.html') ? 'on' : '') + '">' + ic(m[2]) + '<span>' + m[1] + '</span></a>').join('') + '<button type="button" id="nox-m-more" aria-label="Ещё">' + ic('layout-grid') + '<span>Ещё</span></button>';
    document.body.appendChild(t);
    if (!MAIN.some((m) => m[0] === cur)) $('#nox-m-more').classList.add('on');
    $('#nox-m-more').addEventListener('click', more);
    t.addEventListener('click', (e) => { const a = e.target.closest('a[href^="#"]'); if (!a) return; e.preventDefault(); ({ '#dlg': dialogs, '#cmd': commands, '#tpl': tpls })[a.getAttribute('href')](); });
    t.addEventListener('click', (e) => { if (e.target.closest('a')) hap(); });
    const b = document.createElement('button'); b.id = 'nox-m-ai'; b.type = 'button'; b.setAttribute('aria-label', 'Спросить NOX'); b.innerHTML = ic('sparkles'); b.addEventListener('click', ask); document.body.appendChild(b); if (cur === 'chat.html') b.style.display = 'none';
    // скрыть таб-бар и ИИ при вводе (клавиатура)
    document.addEventListener('focusin', (e) => { if (e.target.matches('input,textarea,[contenteditable]')) document.body.classList.add('m-kbd'); });
    document.addEventListener('focusout', () => document.body.classList.remove('m-kbd'));
    const st = document.createElement('style'); st.textContent = '@media(max-width:768px){body.m-kbd #nox-m-tab,body.m-kbd #nox-m-ai{display:none}}'; document.head.appendChild(st);
    // свайп от левого края = назад
    let sx = null, sy = null;
    addEventListener('touchstart', (e) => { const p = e.touches[0]; sx = p.clientX < 22 ? p.clientX : null; sy = p.clientY; }, { passive: true });
    addEventListener('touchend', (e) => { if (sx == null) return; const p = e.changedTouches[0]; if (p.clientX - sx > 80 && Math.abs(p.clientY - sy) < 50) { if (openSheet) closeSheet(); else if (history.length > 1) history.back(); else location.href = './index.html'; } sx = null; }, { passive: true });
    // pull-to-refresh на страницах с данными
    if (/^(news|glance|dispatcher|downloads|training|memory|system|projects|calendar|finance|notifications|ops)\.html$/.test(cur)) {
      const sc = document.createElement('script'); sc.src = './vendor/pulltorefresh/index.umd.min.js';
      sc.onload = () => { try { window.PullToRefresh.init({ mainElement: 'body', instructionsPullToRefresh: 'Потяните для обновления', instructionsReleaseToRefresh: 'Отпустите', instructionsRefreshing: 'Обновляю…', onRefresh() { hap(); location.reload(); }, shouldPullToRefresh() { return !window.scrollY && !openSheet; } }); } catch (e) { /* без PTR */ } };
      document.head.appendChild(sc);
    }
    // диалоги Shoelace: свайп вниз закрывает
    document.addEventListener('touchstart', (e) => { const p = e.target.closest && e.target.closest('sl-dialog'); if (!p || !p.open) return; const panel = p.shadowRoot && p.shadowRoot.querySelector('[part=panel]'); if (!panel) return; const y0 = e.touches[0].clientY; if (y0 > panel.getBoundingClientRect().top + 48) return; const end = (ev) => { if (ev.changedTouches[0].clientY - y0 > 90) { hap(); p.hide(); } document.removeEventListener('touchend', end); }; document.addEventListener('touchend', end); }, { passive: true });
    document.documentElement.style.setProperty('--ds-dock-h', t.offsetHeight + 'px');
  };
  // фиксы целей >=44 и шрифта >=14
  const fix = () => {
    if (!mq.matches) return;
    const q = 'a,button,[role=button],[role=tab],input:not([type=hidden]),select,summary,label[for],sl-button,sl-icon-button,sl-tab,sl-checkbox,sl-switch';
    document.querySelectorAll(q).forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nox-m-ai,#nxdock')) return; const r = e.getBoundingClientRect(); if (!r.width || !r.height) return; if (r.width < 44 || r.height < 44) { e.classList.add('m-t44'); if (r.height < 44) { e.style.setProperty('min-height', '44px', 'important'); e.style.setProperty('max-height', 'none', 'important'); } if (r.width < 44) e.style.setProperty('min-width', '44px', 'important'); } });
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; const seen = new Set();
    while ((n = w.nextNode())) { if (!n.nodeValue.trim()) continue; const e = n.parentElement; if (!e || seen.has(e) || e.closest('script,style,svg,canvas')) continue; seen.add(e); const fs = parseFloat(getComputedStyle(e).fontSize); if (fs >= 1 && fs < 14) { e.classList.add('m-f14'); e.style.setProperty('font-size', '14px', 'important'); } }
    const W = innerWidth; document.querySelectorAll('body *').forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nxdock,.swiper,[class*=carousel],[class*=scroll],[class*=track]')) return; const r = e.getBoundingClientRect(); if (r.width > W + 1 && getComputedStyle(e).position !== 'fixed') e.classList.add('m-wrap'); });
  };
  window.__noxMfix = fix;
  let tmr; const later = () => { clearTimeout(tmr); tmr = setTimeout(fix, 120); };
  const start = () => { if (!document.body) return; if (mq.matches) build(); later(); new MutationObserver(later).observe(document.body, { childList: true, subtree: true }); [300, 700, 1200, 2000, 3000, 4500, 7000, 10000].forEach((t) => setTimeout(fix, t)); setInterval(fix, 3000); };
  mq.addEventListener && mq.addEventListener('change', () => { if (mq.matches) build(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
