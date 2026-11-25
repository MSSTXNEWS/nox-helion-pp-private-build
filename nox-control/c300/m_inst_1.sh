S=/workspace/nox/web/site
cat > $S/nox-m-mobile.css <<'M_EOF_CSS'
/* NOX · M: мобильная адаптация. Только @media (max-width:768px). Десктоп не затрагивается. */
@media (max-width:768px){
:root{--m-tab-h:calc(60px + env(safe-area-inset-bottom,0px));--ds-dock-h:var(--m-tab-h)!important;--dock-h:var(--m-tab-h)!important}
html,body{overflow-x:hidden;max-width:100vw;-webkit-text-size-adjust:100%}
body{font-size:max(14px,1em)}
input,select,textarea{font-size:16px!important}
img,video,canvas,svg,iframe,pre,table{max-width:100%}
table{display:block;overflow-x:auto}
pre,code{white-space:pre-wrap;word-break:break-word}
#app{padding-left:env(safe-area-inset-left,0);padding-right:env(safe-area-inset-right,0);bottom:var(--m-tab-h)!important;height:auto!important}
/* прячем старые плавающие кнопки и док (остаются в DOM: программные click() работают) */
#nxdock,.nmc-fab,#nxmPill,#nxnavx,.nai-btn,.hx-ask,#miniFab,.nxpu-tog{opacity:0!important;pointer-events:none!important;position:fixed!important;left:-200px!important;bottom:0!important;width:1px!important;height:1px!important;min-width:0!important;min-height:0!important;overflow:hidden}
/* таб-бар */
#nox-m-tab{position:fixed;left:0;right:0;bottom:0;z-index:2000;height:var(--m-tab-h);padding:6px 6px env(safe-area-inset-bottom,0px);display:flex;align-items:stretch;justify-content:space-around;background:rgba(18,14,22,.72);-webkit-backdrop-filter:blur(24px) saturate(1.4);backdrop-filter:blur(24px) saturate(1.4);border-top:1px solid rgba(255,255,255,.12);box-sizing:border-box}
#nox-m-tab a,#nox-m-tab button{flex:1 1 0;min-width:44px;min-height:44px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;background:none;border:0;color:rgba(239,230,223,.7);font:600 14px/1 inherit;font-family:inherit;text-decoration:none;border-radius:14px;-webkit-tap-highlight-color:transparent;padding:0}
#nox-m-tab sl-icon{font-size:22px}
#nox-m-tab span{font-size:14px;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
#nox-m-tab .on{color:#e9b465}
#nox-m-tab .on sl-icon{filter:drop-shadow(0 0 6px rgba(233,180,101,.6))}
/* единая кнопка ИИ */
#nox-m-ai{position:fixed;right:14px;bottom:calc(var(--m-tab-h) + 12px);z-index:2001;width:56px;height:56px;min-width:56px;min-height:56px;border-radius:50%;border:1px solid rgba(255,255,255,.25);background:radial-gradient(circle at 35% 30%,#f3c981,#c9863c 70%);color:#1a1210;display:flex;align-items:center;justify-content:center;font-size:26px;box-shadow:0 8px 28px rgba(0,0,0,.5),0 0 22px rgba(233,180,101,.35);padding:0}
/* шторки */
#nox-m-scrim{position:fixed;inset:0;z-index:2100;background:rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:opacity .25s}
#nox-m-scrim.open{opacity:1;pointer-events:auto}
.nox-m-sheet{position:fixed;left:0;right:0;bottom:0;z-index:2101;max-height:82vh;overflow:auto;box-sizing:border-box;padding:10px 14px calc(18px + env(safe-area-inset-bottom,0px));background:rgba(22,17,26,.9);-webkit-backdrop-filter:blur(28px);backdrop-filter:blur(28px);border:1px solid rgba(255,255,255,.14);border-bottom:0;border-radius:24px 24px 0 0;color:#efe6df;transform:translateY(105%);transition:transform .28s cubic-bezier(.2,.8,.2,1);touch-action:pan-y}
.nox-m-sheet.open{transform:none}
.nox-m-sheet .m-handle{width:44px;height:5px;border-radius:3px;background:rgba(255,255,255,.35);margin:2px auto 12px}
.nox-m-sheet h3{margin:0 0 10px;font-size:16px}
.m-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.m-grid a,.m-list button{min-height:44px;display:flex;flex-direction:column;align-items:center;gap:6px;padding:10px 2px;border-radius:16px;background:rgba(255,255,255,.07);color:#efe6df;text-decoration:none;font-size:14px;text-align:center;line-height:1.15;word-break:break-word;border:0;font-family:inherit}
.m-grid a sl-icon{font-size:24px;color:#e9b465}
.m-grid a.on{outline:1px solid #e9b465}
.m-list{display:grid;gap:8px}
.m-list button{flex-direction:row;justify-content:flex-start;padding:12px 16px;font-size:15px}
.m-grp{grid-column:1/-1;font-size:14px;opacity:.65;margin-top:6px}
/* диалоги -> нижние шторки */
sl-dialog::part(base){align-items:flex-end!important;justify-content:center}
sl-dialog::part(panel){width:100vw!important;max-width:100vw!important;margin:0!important;max-height:88vh;border-radius:24px 24px 0 0!important;padding-bottom:env(safe-area-inset-bottom,0px)}
sl-dialog::part(panel)::before{content:"";display:block;width:44px;height:5px;border-radius:3px;background:rgba(255,255,255,.35);margin:8px auto 0}
sl-dialog{--width:100vw}
sl-drawer[placement=start]::part(panel),sl-drawer[placement=end]::part(panel){max-width:92vw}
.s2-modal{align-items:flex-end!important}
.s2-modal>*{width:100%!important;max-width:100vw!important;border-radius:24px 24px 0 0!important;max-height:88vh;overflow:auto}
/* цели и текст (JS добавляет классы) */
.m-t44{min-height:44px!important;min-width:44px!important;box-sizing:border-box}
a.m-t44:not([style*="display:block"]),span.m-t44[role=button]{display:inline-flex;align-items:center;justify-content:center}
.m-f14{font-size:14px!important}
.m-wrap{max-width:100%!important;overflow-wrap:anywhere}
.m-ptr{position:fixed;top:calc(env(safe-area-inset-top,0px) + 8px);left:50%;transform:translateX(-50%);z-index:2200;background:rgba(22,17,26,.9);color:#e9b465;border-radius:20px;padding:8px 14px;font-size:14px}
}
@media (max-width:768px) and (min-width:481px){.m-grid{grid-template-columns:repeat(6,1fr)}}
M_EOF_CSS
cat > $S/nox-m-mobile.js <<'M_EOF_JS'
/* NOX · M: мобильный UX (таб-бар, шторка «Ещё», кнопка ИИ, свайп назад, pull-to-refresh, фиксы целей/шрифта). Активен только при ширине <=768. */
(() => {
  if (window.__noxM) return; window.__noxM = 1;
  const mq = matchMedia('(max-width:768px)');
  const $ = (s, r = document) => r.querySelector(s);
  const ic = (n) => '<sl-icon library="tabler" name="' + n + '"></sl-icon>';
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cur = (location.pathname.split('/').pop() || 'index.html').replace(/\.main\.html$/, '.html');
  const hap = (t) => { try { const h = window.iosHaptics || window.NOX_ios_haptics || window.haptic; if (typeof h === 'function') h(); else if (h && h.haptic) h.haptic(); else navigator.vibrate && navigator.vibrate(t || 8); } catch (e) { /* без haptics */ } };
  const MAIN = [['index.html', 'Главная', 'home-2'], ['chat.html', 'Резонанс', 'message-circle'], ['assistant.html', 'Помощник', 'checklist'], ['studio.html', 'Ателье', 'brush']];
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
  const build = () => {
    if (built) return; built = true;
    scrim = document.createElement('div'); scrim.id = 'nox-m-scrim'; scrim.addEventListener('click', closeSheet); document.body.appendChild(scrim);
    const t = document.createElement('nav'); t.id = 'nox-m-tab'; t.setAttribute('aria-label', 'Основная навигация');
    t.innerHTML = MAIN.map((m) => '<a href="./' + m[0] + '" class="' + (m[0] === cur ? 'on' : '') + '">' + ic(m[2]) + '<span>' + m[1] + '</span></a>').join('') + '<button type="button" id="nox-m-more" aria-label="Ещё">' + ic('layout-grid') + '<span>Ещё</span></button>';
    document.body.appendChild(t);
    if (!MAIN.some((m) => m[0] === cur)) $('#nox-m-more').classList.add('on');
    $('#nox-m-more').addEventListener('click', more);
    t.addEventListener('click', (e) => { if (e.target.closest('a')) hap(); });
    const b = document.createElement('button'); b.id = 'nox-m-ai'; b.type = 'button'; b.setAttribute('aria-label', 'Спросить NOX'); b.innerHTML = ic('sparkles'); b.addEventListener('click', ask); document.body.appendChild(b);
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
    document.querySelectorAll(q).forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nox-m-ai,#nxdock')) return; const r = e.getBoundingClientRect(); if (!r.width || !r.height) return; if (r.width < 44 || r.height < 44) e.classList.add('m-t44'); });
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n; const seen = new Set();
    while ((n = w.nextNode())) { if (!n.nodeValue.trim()) continue; const e = n.parentElement; if (!e || seen.has(e) || e.closest('script,style,svg,canvas')) continue; seen.add(e); if (parseFloat(getComputedStyle(e).fontSize) < 14) e.classList.add('m-f14'); }
    const W = innerWidth; document.querySelectorAll('body *').forEach((e) => { if (e.closest('#nox-m-tab,.nox-m-sheet,#nxdock,.swiper,[class*=carousel],[class*=scroll],[class*=track]')) return; const r = e.getBoundingClientRect(); if (r.width > W + 1 && getComputedStyle(e).position !== 'fixed') e.classList.add('m-wrap'); });
  };
  let tmr; const later = () => { clearTimeout(tmr); tmr = setTimeout(() => (window.requestIdleCallback || setTimeout)(fix), 400); };
  const start = () => { if (!document.body) return; if (mq.matches) build(); later(); new MutationObserver(later).observe(document.body, { childList: true, subtree: true }); setTimeout(fix, 1500); setTimeout(fix, 4000); };
  mq.addEventListener && mq.addEventListener('change', () => { if (mq.matches) build(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
M_EOF_JS
cd $S; c=0
for f in *.html; do
  grep -q 'nox-m-mobile.js' $f && continue
  [ -e $f.bak_m_1 ] || cp $f $f.bak_m_1
  sed -i 's#</head>#<link rel="stylesheet" href="./nox-m-mobile.css?v=m1" media="(max-width:768px)"><script src="./nox-m-mobile.js?v=m1" defer></script></head>#' $f
  grep -q 'nox-m-mobile.js' $f && c=$((c+1)) || echo "OUT: no </head> in $f"
done
echo "OUT: wired $c pages"
grep -q 'pulltorefresh' /workspace/nox/web/site/../../../nox/web/site/vendor/INDEX.json 2>/dev/null || true
echo "OUT: ok"
