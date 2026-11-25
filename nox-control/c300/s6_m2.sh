echo S4RUN:s6_m2
cd /workspace/nox/web/site
cat > nox-s6-sl.js <<'S6EOF_js'
/* S6: контролы страниц на Shoelace. Исходные элементы остаются в DOM (скрыты) и получают события: логика страниц не ломается.
   button -> sl-button, select -> sl-select, input/textarea -> sl-input/sl-textarea, checkbox -> sl-checkbox, range -> sl-range, статус-чипы -> sl-badge.
   Плюс «Спросить NOX» (sl-dialog, /api/chat) на каждой странице. */
(function () {
  if (window.__s6sl) return; window.__s6sl = 1;
  const page = document.body.getAttribute('data-page') || location.pathname.split('/').pop().replace('.html', '');
  const SKIP = 'sl-dialog,sl-tab-group,sl-tab,sl-button,sl-select,sl-input,sl-switch,sl-tooltip,sl-details,sl-menu,.s4dlg,.s6-skip,[data-s6="skip"],[class*="FIE_"],.ps-ed,.plyr,.vjs-control-bar,.swiper-button-next,.swiper-button-prev,.u-wrap,canvas,#nxnavx,.nmc,.nox-dock,#ds-tip,[id^="nxm"],[id^="nox-"],.s6bar,.cm-editor,.CodeMirror';
  const BTN = 'main.page button:not([data-s6])';
  const reg = new Map();
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const lbl = (b) => [...b.childNodes].filter((n) => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'SL-ICON' && n.tagName !== 'svg' && n.tagName !== 'SVG')).map((n) => n.textContent).join('').replace(/\s+/g, ' ').trim();
  const hide = (el) => { el.classList.add('s6h'); el.setAttribute('data-s6', '1'); el.setAttribute('tabindex', '-1'); el.setAttribute('aria-hidden', 'true'); };
  const S4 = () => !!document.querySelector('script[src*="nox-s4-sl"]');
  const skip = (el) => !el.isConnected || (S4() && el.closest('.ph .acts')) || el.closest(SKIP) || el.getAttribute('data-s6') != null;
  function simple(b) {
    if (b.querySelector('img,picture,video,canvas,div,h1,h2,h3,h4,p,li,a,button')) return false;
    if (/card|tile|poster|cover|track|thumb|item|slide|cell|row/i.test(b.className || '')) return false;
    if ([...b.children].filter((c) => !/^(SL-ICON|SVG|I)$/i.test(c.tagName) && c.textContent.trim()).length > 1) return false;
    if (lbl(b).length > 64) return false;
    const bg = getComputedStyle(b).backgroundImage; if (/url\(/.test(bg || '')) return false;
    return true;
  }
  function variantOf(b) {
    const c = b.className || '';
    if (b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-selected') === 'true' || /(^|\s)(on|act|active|sel|selected|primary|ai|go)(\s|$)/.test(c)) return 'primary';
    if (/danger|del|stop|remove/.test(c)) return 'danger';
    return 'default';
  }
  function syncBtn(b, s) {
    const l = lbl(b), lab = s.querySelector('.s6l'); if (lab && lab.textContent !== l) lab.textContent = l;
    const v = variantOf(b); if (s.getAttribute('variant') !== v) s.setAttribute('variant', v);
    (b.disabled || b.dataset.s6off) ? s.setAttribute('disabled', '') : s.removeAttribute('disabled');
    if (b.dataset.s6off) s.setAttribute('title', b.dataset.s6off); else s.removeAttribute('title');
    const bi = b.style.backgroundImage; if (/gradient/.test(bi || '')) { s.style.setProperty('--swatch', bi); s.style.setProperty('--swb', b.style.borderColor || 'transparent'); s.setAttribute('data-sw', '1'); }
    if (b.getAttribute('aria-pressed') === 'true') s.setAttribute('data-on', '1'); else s.removeAttribute('data-on');
    const ic = b.querySelector('sl-icon'), mine = s.querySelector('sl-icon'); if (ic && mine && mine.getAttribute('name') !== ic.getAttribute('name')) mine.setAttribute('name', ic.getAttribute('name'));
    if (b.hasAttribute('hidden') || b.style.display === 'none') s.setAttribute('hidden', ''); else s.removeAttribute('hidden');
  }
  function convBtn(b) {
    const ic = b.querySelector('sl-icon'), l = lbl(b), s = document.createElement('sl-button');
    s.size = 'large'; s.className = 's6sl'; s.setAttribute('data-s6for', b.id || '');
    const tt = b.title || b.getAttribute('aria-label') || l || 'Действие';
    s.innerHTML = (ic ? '<sl-icon slot="prefix" library="' + esc(ic.getAttribute('library') || 'tabler') + '" name="' + esc(ic.getAttribute('name')) + '"></sl-icon>' : '') + '<span class="s6l">' + esc(l) + '</span>';
    if (!l && !ic) s.querySelector('.s6l').textContent = (b.textContent || '').trim() || '•';
    if (!l) s.setAttribute('data-icononly', '1');
    s.setAttribute('aria-label', tt);
    s.addEventListener('click', (e) => { e.stopPropagation(); e.preventDefault(); b.click(); setTimeout(() => syncBtn(b, s), 60); });
    let out = s;
    if (!l) { const t = document.createElement('sl-tooltip'); t.content = tt; t.appendChild(s); out = t; }
    b.before(out); hide(b); syncBtn(b, s);
    const mo = new MutationObserver(() => syncBtn(b, s)); mo.observe(b, { attributes: true, childList: true, characterData: true, subtree: true });
    reg.set(b, { el: out, sync: () => syncBtn(b, s) });
  }
  function fire(el, t, init) { el.dispatchEvent(new Event(t, Object.assign({ bubbles: true }, init || {}))); }
  function convSelect(sel) {
    const s = document.createElement('sl-select'); s.className = 's6sl s6f'; s.size = 'large'; s.hoist = true; s.setAttribute('data-s6for', sel.id || '');
    s.setAttribute('placeholder', sel.getAttribute('aria-label') || sel.title || 'Выбрать');
    const fill = () => { s.innerHTML = [...sel.options].map((o) => '<sl-option value="' + esc(o.value) + '">' + esc(o.textContent) + '</sl-option>').join(''); s.value = sel.value; };
    fill(); s.addEventListener('sl-change', () => { if (sel.value !== s.value) { sel.value = s.value; fire(sel, 'input'); fire(sel, 'change'); } });
    sel.before(s); hide(sel);
    const mo = new MutationObserver(fill); mo.observe(sel, { childList: true, subtree: true });
    reg.set(sel, { el: s, sync: () => { if (s.value !== sel.value) s.value = sel.value; sel.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convText(inp) {
    const ta = inp.tagName === 'TEXTAREA', s = document.createElement(ta ? 'sl-textarea' : 'sl-input');
    s.className = 's6sl s6f'; s.size = 'large'; s.setAttribute('data-s6for', inp.id || '');
    if (!ta) s.type = inp.type === 'search' ? 'search' : (['number', 'url', 'email', 'password'].includes(inp.type) ? inp.type : 'text'); else s.rows = inp.rows || 2;
    ['placeholder', 'min', 'max', 'step', 'maxlength'].forEach((a) => { if (inp.hasAttribute(a)) s.setAttribute(a, inp.getAttribute(a)); });
    s.setAttribute('aria-label', inp.getAttribute('aria-label') || inp.placeholder || inp.title || 'Поле'); s.value = inp.value;
    if (!ta) s.clearable = inp.type === 'search';
    s.addEventListener('sl-input', () => { if (inp.value !== s.value) { inp.value = s.value; fire(inp, 'input'); } });
    s.addEventListener('sl-change', () => fire(inp, 'change'));
    s.addEventListener('keydown', (e) => { inp.dispatchEvent(new KeyboardEvent('keydown', { key: e.key, code: e.code, keyCode: e.keyCode, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, bubbles: true, cancelable: true })); });
    inp.before(s); hide(inp);
    reg.set(inp, { el: s, sync: () => { if (s.value !== inp.value) s.value = inp.value; inp.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convCheck(inp) {
    const s = document.createElement('sl-checkbox'); s.className = 's6sl'; s.size = 'large'; s.setAttribute('data-s6for', inp.id || '');
    const lb = inp.closest('label'); const txt = lb ? [...lb.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').trim() : '';
    s.textContent = txt || inp.getAttribute('aria-label') || inp.title || ''; s.checked = inp.checked;
    s.addEventListener('sl-change', () => { if (inp.checked !== s.checked) inp.click(); });
    inp.before(s); hide(inp);
    if (lb && txt) [...lb.childNodes].forEach((n) => { if (n.nodeType === 3) n.textContent = ''; });
    reg.set(inp, { el: s, sync: () => { s.checked = inp.checked; inp.disabled ? s.setAttribute('disabled', '') : s.removeAttribute('disabled'); } });
  }
  function convRange(inp) {
    const s = document.createElement('sl-range'); s.className = 's6sl s6f'; s.setAttribute('data-s6for', inp.id || '');
    ['min', 'max', 'step'].forEach((a) => { if (inp.hasAttribute(a)) s[a] = Number(inp.getAttribute(a)); }); s.value = Number(inp.value);
    s.setAttribute('aria-label', inp.getAttribute('aria-label') || inp.title || 'Значение');
    s.addEventListener('sl-input', () => { inp.value = s.value; fire(inp, 'input'); }); s.addEventListener('sl-change', () => fire(inp, 'change'));
    inp.before(s); hide(inp);
    reg.set(inp, { el: s, sync: () => { if (Number(s.value) !== Number(inp.value)) s.value = Number(inp.value); } });
  }
  const CHIP = '.s2-chip,.chip,.badge,.pill,.tag,.st-chip,.status,.stat-chip,.nox-chip';
  function convChip(c) {
    if (c.tagName === 'SL-BADGE') return;
    const s = document.createElement('sl-badge'); s.className = 's6bd'; s.pill = true;
    const sync = () => { const cl = c.className || ''; const v = /(^|\s)(ok|good|on|live|ready|success|online)(\s|$)/.test(cl) ? 'success' : /(warn|wait|busy|pending)/.test(cl) ? 'warning' : /(bad|err|fail|off|danger|down)/.test(cl) ? 'danger' : /(^|\s)(acc|primary|new|hot)(\s|$)/.test(cl) ? 'primary' : 'neutral'; if (s.variant !== v) s.variant = v; const t = c.textContent.trim(); if (s.textContent !== t) s.textContent = t; };
    sync(); c.before(s); hide(c); new MutationObserver(sync).observe(c, { attributes: true, childList: true, characterData: true, subtree: true });
    reg.set(c, { el: s, sync });
  }
  function run() {
    reg.forEach((v, k) => { if (!k.isConnected) { v.el.remove(); reg.delete(k); } });
    document.querySelectorAll(BTN).forEach((b) => { if (!skip(b) && !b.classList.contains('s6h') && simple(b)) { try { convBtn(b); } catch (e) { } } });
    document.querySelectorAll('main.page select:not([data-s6]),main.page textarea:not([data-s6]),main.page input:not([data-s6])').forEach((i) => {
      if (skip(i)) return; const t = (i.type || '').toLowerCase();
      try {
        if (i.tagName === 'SELECT') { if (!i.multiple) convSelect(i); }
        else if (i.tagName === 'TEXTAREA') convText(i);
        else if (['text', 'search', 'number', 'url', 'email', 'password', ''].includes(t)) convText(i);
        else if (t === 'checkbox') convCheck(i);
        else if (t === 'range') convRange(i);
      } catch (e) { }
    });
    document.querySelectorAll('main.page ' + CHIP.split(',').join(',main.page ')).forEach((c) => { if (!c.closest(SKIP) && c.getAttribute('data-s6') == null && c.tagName !== 'SL-BADGE' && !c.querySelector('button,a')) { try { convChip(c); } catch (e) { } } });
    states();
    ask();
  }
  /* skeleton / empty через NOXds */
  function states() {
    if (!window.NOXds) return;
    document.querySelectorAll('main.page .empty,main.page .muted,main.page [id]:not(sl-button)').forEach((el) => {
      if (el.children.length || el.getAttribute('data-s6st') || el.closest(SKIP)) return; const tx = (el.textContent || '').trim();
      if (/^(загрузка|проверка|подключение)[.…]*$/i.test(tx)) { el.setAttribute('data-s6st', 'sk'); NOXds.skeleton(el, 3); }
      else if (/^(пусто|нет данных|данных нет|ничего нет|пока пусто)\.?$/i.test(tx)) { el.setAttribute('data-s6st', 'em'); NOXds.empty(el, { title: tx.replace(/\.$/, '').replace(/^./, (c) => c.toUpperCase()), text: 'Данные появятся после первой записи или подключения источника.' }); }
    });
  }
  /* «Спросить NOX»: связь страницы с ИИ */
  function ask() {
    if (document.getElementById('s6Ask')) return; const wrap = document.querySelector('main.page .wrap'); if (!wrap) return;
    const bar = document.createElement('div'); bar.className = 's6bar'; bar.innerHTML = '<sl-badge variant="neutral" pill class="s6bd">ИИ</sl-badge><sl-button id="s6Ask" size="large" variant="primary" class="s6sl"><sl-icon slot="prefix" library="tabler" name="sparkles"></sl-icon>Спросить NOX</sl-button>';
    const tg = wrap.querySelector('.ph .acts,.nw-top,.cn-top,.mu-top'); if (tg) { bar.style.margin = '0'; bar.style.display = 'contents'; tg.appendChild(bar); } else wrap.insertAdjacentElement('afterbegin', bar);
    const d = document.createElement('sl-dialog'); d.label = 'Спросить NOX · ' + (document.title.split('·').pop() || page).trim(); d.className = 's6dlg';
    d.innerHTML = '<sl-textarea class="s6q" rows="3" size="large" placeholder="Вопрос или команда по этой странице"></sl-textarea><div class="s6a" aria-live="polite"><div class="ds-empty">Ответ появится здесь.</div></div><sl-button slot="footer" class="s6go" variant="primary" size="large">Отправить</sl-button><sl-button slot="footer" class="s6x" size="large">Закрыть</sl-button>';
    document.body.appendChild(d);
    bar.querySelector('#s6Ask').addEventListener('click', () => d.show());
    d.querySelector('.s6x').addEventListener('click', () => d.hide());
    const go = d.querySelector('.s6go'), q = d.querySelector('.s6q'), out = d.querySelector('.s6a');
    async function send() {
      const text = (q.value || '').trim(); if (!text) { q.focus(); return; }
      go.loading = true; out.innerHTML = '<sl-skeleton effect="pulse" style="height:20px;margin:8px 0"></sl-skeleton><sl-skeleton effect="pulse" style="height:20px;width:70%"></sl-skeleton>';
      const full = 'Страница NOX «' + page + '». ' + text;
      try {
        const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stream: true, nox_mode: 'fast', messages: [{ role: 'user', content: full }], message: { role: 'user', content: full } }) });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const rd = r.body.getReader(), dec = new TextDecoder(); let buf = '', acc = '';
        for (;;) { const x = await rd.read(); if (x.done) break; buf += dec.decode(x.value, { stream: true }); const ls = buf.split('\n'); buf = ls.pop(); ls.forEach((ln) => { ln = ln.replace(/^data:\s*/, '').trim(); if (!ln || ln === '[DONE]') return; try { const j = JSON.parse(ln); const c = (j.message && j.message.content) || (j.choices && j.choices[0] && ((j.choices[0].delta && j.choices[0].delta.content) || (j.choices[0].message && j.choices[0].message.content))) || j.response || j.content || ''; if (typeof c === 'string') acc += c; } catch (e) { } }); out.textContent = acc; }
        if (!acc) out.innerHTML = '<div class="ds-empty">NOX не вернул текст. Повторите запрос.</div>';
      } catch (e) { out.innerHTML = '<div class="ds-empty">ИИ недоступен: ' + esc(e.message) + '</div>'; }
      go.loading = false;
    }
    go.addEventListener('click', send);
    q.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); });
  }
  /* честная недоступность: плеер без треков */
  function honest() {
    if (page !== 'music') return; const np = document.querySelector('.mu-np'); const idle = !np || /Ничего не играет/.test(np.textContent || '');
    ['bSh', 'bPr', 'bNx', 'bRp'].forEach((id) => { const b = document.getElementById(id); if (!b) return; if (idle) b.dataset.s6off = 'Недоступно: нет треков'; else delete b.dataset.s6off; const r = reg.get(b); if (r) r.sync(); });
  }
  const go = () => { try { run(); honest(); } catch (e) { } };
  const start = () => { go(); setTimeout(go, 800); setTimeout(go, 2500); let t; new MutationObserver(() => { clearTimeout(t); t = setTimeout(go, 250); }).observe(document.body, { childList: true, subtree: true }); setInterval(() => { reg.forEach((v) => { try { v.sync(); } catch (e) { } }); try { honest(); } catch (e) { } }, 1000); };
  if (document.readyState !== 'loading') start(); else document.addEventListener('DOMContentLoaded', start);
})();
S6EOF_js
cat > nox-s6.css <<'S6EOF_css'
/* S6: единый слой sl-* + слои photo + ритм сетки news. Шрифт >=12, цель 44, сетка 8. */
.s6h{display:none!important}
.s6sl{--sl-input-height-large:44px;--sl-input-font-size-large:14px;max-width:100%}
sl-button.s6sl::part(base){min-height:44px;min-width:44px;font-size:14px;letter-spacing:0;background:var(--ds-glass,rgba(255,235,220,.06));border:1px solid var(--ds-line,rgba(255,255,255,.14));color:var(--ds-ink,#efe6df);box-shadow:var(--ds-e1);transition:background .15s,border-color .15s,transform .1s}
sl-button.s6sl::part(base):hover{background:var(--ds-glass-hi,rgba(255,235,220,.11))}
sl-button.s6sl[variant=primary]::part(base){background:rgba(233,180,101,.18);border-color:rgba(233,180,101,.55);color:#f6dcb0}
sl-button.s6sl[variant=danger]::part(base){background:rgba(229,100,90,.16);border-color:rgba(229,100,90,.5);color:#ffb3ab}
sl-button.s6sl[data-icononly]::part(label){padding:0 8px}
sl-button.s6sl:focus-visible::part(base){outline:2px solid #e9b465;outline-offset:2px}
.s6f{display:block;width:100%}
sl-select.s6f::part(combobox),sl-input.s6f::part(base),sl-textarea.s6f::part(base){background:rgba(2,3,10,.55);border-color:var(--ds-line,rgba(255,255,255,.14));color:var(--ds-ink,#efe6df);min-height:44px}
sl-textarea.s6f::part(textarea){font-size:14px;line-height:1.4}
.s6bd{--sl-font-size-x-small:12px;font-size:12px;min-height:24px;padding:2px 10px;letter-spacing:.02em}
.s6bar{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin:8px 0 16px}
.s6dlg{--width:min(560px,94vw)}
.s6dlg::part(panel){background:rgba(16,12,12,.82);backdrop-filter:blur(22px) saturate(1.3);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e2)}
.s6dlg .s6a{margin-top:16px;max-height:40vh;overflow:auto;white-space:pre-wrap;font-size:14px;line-height:1.5}
.ps-row>.s6sl,.ps-row>sl-tooltip{flex:1 1 112px}
.ps-row>sl-select,.ps-row>sl-input{flex:1 1 100%}

/* PHOTO: плавающие стеклянные панели, слои */
body[data-page=photo] .ps{position:relative;display:block;height:calc(100vh - 250px);min-height:520px;isolation:isolate}
body[data-page=photo] .ps-ed{position:absolute;inset:0;z-index:1;border-radius:16px;box-shadow:var(--ds-e1)}
body[data-page=photo] .ps-ai.glass{position:absolute;z-index:3;top:72px;right:16px;bottom:16px;width:min(336px,42%);padding:8px 16px 16px;border-radius:16px;background:rgba(14,10,10,.64);backdrop-filter:blur(24px) saturate(1.4);-webkit-backdrop-filter:blur(24px) saturate(1.4);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e2)}
body[data-page=photo] .ps-ai .ps-box{padding:16px 0!important}
body[data-page=photo] .ps-ai .ps-box>h3{min-height:44px;font-size:12px}
body[data-page=photo] .ps-log{max-height:24vh}
body[data-page=photo] .ph .acts{padding:8px;border-radius:16px;background:rgba(14,10,10,.5);backdrop-filter:blur(18px);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e1)}
body[data-page=photo] .ps-th{gap:8px}
@media (max-width:900px){
 body[data-page=photo] .ps{display:flex;flex-direction:column;gap:16px;height:auto}
 body[data-page=photo] .ps-ed{position:relative;inset:auto;height:60vh!important}
 body[data-page=photo] .ps-ai.glass{position:relative;inset:auto;width:auto;box-shadow:var(--ds-e1)}
}

/* NEWS: единый ритм сетки, сетка 8 px */
body[data-page=news] .nw-grid{grid-template-columns:repeat(auto-fill,minmax(256px,1fr));grid-auto-rows:1fr;gap:24px;margin-top:24px;align-items:stretch}
body[data-page=news] .nw-cd{height:100%;border-radius:16px;box-shadow:var(--ds-e1)}
body[data-page=news] .nw-cd .im{aspect-ratio:16/10;flex:none}
body[data-page=news] .nw-cd .b{flex:1;display:flex;flex-direction:column;gap:8px;padding:16px}
body[data-page=news] .nw-cd h4{margin:0;font-size:16px;line-height:24px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:72px}
body[data-page=news] .nw-src{font-size:12px;min-height:24px}
body[data-page=news] .nw-main{gap:24px;margin-top:16px}
body[data-page=news] .nw-li{padding:16px 0;min-height:88px}
body[data-page=news] .nw-top{gap:8px;padding:8px 0}

/* CINEMA */
body[data-page=cinema] .cn-hero{border-radius:16px;box-shadow:var(--ds-e2);margin-top:8px}
body[data-page=cinema] .cn-hero .in{margin:16px;padding:24px;border-radius:16px;background:rgba(10,8,8,.5);backdrop-filter:blur(18px) saturate(1.3);-webkit-backdrop-filter:blur(18px) saturate(1.3);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e1)}
body[data-page=cinema] .cn-row{padding:8px 8px 0}
body[data-page=cinema] .cn-row h3{min-height:48px;align-items:center}
.s6nav{margin-left:auto;display:inline-flex;gap:8px}
.s6ib{font-size:20px;min-width:44px;min-height:44px;border-radius:12px;background:var(--ds-glass,rgba(255,235,220,.06));border:1px solid var(--ds-line,rgba(255,255,255,.14));display:inline-grid;place-items:center;color:var(--ds-ink,#efe6df)}
.s6ib:hover{background:var(--ds-glass-hi,rgba(255,235,220,.11))}
.s6cb{position:absolute;left:8px;top:8px;z-index:3;display:flex;gap:4px;flex-wrap:wrap}
.cn-c .po{box-shadow:var(--ds-e1)}
.cn-c .pv .r sl-icon{font-size:18px;width:32px;height:32px;padding:7px;border-radius:50%;border:1px solid var(--ds-line,rgba(255,255,255,.14));box-sizing:border-box}
body[data-page=cinema] .cn-bar{gap:8px;padding:16px 8px 0}
body[data-page=cinema] .cn-ext{gap:16px}
body[data-page=cinema] .cn-ext a{border-radius:16px;box-shadow:var(--ds-e1);min-height:72px;padding:16px}
body[data-page=cinema] .cn-ext a span{font-size:12px}

/* LEADERS */
.s6lm-h{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:16px 0}
.s6lm-q,.s6zp-q{flex:1 1 280px;width:auto}
.s6lm-g,.s6zp-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(264px,1fr));gap:16px;margin-bottom:24px}
sl-card.s6lm-c,sl-card.s6zp-c,.s6ol-s sl-card{--border-color:var(--ds-line,rgba(255,255,255,.14));--border-radius:16px;--padding:16px;box-shadow:var(--ds-e1)}
sl-card.s6lm-c::part(base),sl-card.s6zp-c::part(base),.s6ol-s sl-card::part(base){background:var(--ds-glass,rgba(255,235,220,.06));backdrop-filter:blur(14px);height:100%}
.s6lm-t b{font:600 16px/24px var(--sans,inherit);word-break:break-all;display:block;min-height:48px}
.s6lm-b{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.s6lm-a{display:flex;gap:8px;flex-wrap:wrap}.s6lm-a sl-button{flex:1 1 auto}
.s6rc{margin:16px 0}.s6rc-l{display:flex;flex-direction:column;gap:8px;margin-top:16px}
.s6rc-r{display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:12px 16px;border-radius:16px;border:1px solid var(--ds-line,rgba(255,255,255,.14));background:var(--ds-glass,rgba(255,235,220,.06));box-shadow:var(--ds-e1)}
.s6rc-i{display:grid;place-items:center;width:44px;height:44px;border-radius:12px;background:rgba(233,180,101,.14);font-size:20px;color:#e9b465}
.s6rc-d{flex:1 1 220px;display:flex;flex-direction:column;gap:2px}.s6rc-d b{font-size:14px}.s6rc-d span{font-size:12px;color:var(--ds-mute,rgba(240,232,226,.62))}
.s6rc-p{flex:1 1 160px;width:auto}.s6rc-o{margin-top:16px;font-size:14px;min-height:24px}
.s6zp-t{display:flex;gap:8px;align-items:center;font-size:16px;min-height:32px}.s6zp-t sl-icon{font-size:20px;color:#e9b465}
.s6zp-s{font-size:12px;color:var(--ds-mute,rgba(240,232,226,.62));margin:8px 0;min-height:24px}
.s6ol{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:24px;margin:16px 0 24px;padding:32px;border-radius:24px;border:1px solid var(--ds-line,rgba(255,255,255,.14));background:var(--ds-glass,rgba(255,235,220,.06));backdrop-filter:blur(20px);box-shadow:var(--ds-e2)}
.s6ol h2{margin:0 0 8px;font:700 clamp(24px,3vw,32px)/1.2 var(--head,inherit)}.s6ol p{margin:0 0 24px;font-size:16px;color:var(--ds-mute,rgba(240,232,226,.62))}
.s6ol-b{display:flex;gap:16px;flex-wrap:wrap}
.s6ol-s{display:grid;gap:8px}.s6ol-s sl-card::part(body){display:flex;align-items:center;gap:16px}.s6ol-s sl-icon{font-size:24px;color:#e9b465}.s6ol-s b{flex:1}
@media (max-width:900px){.s6ol{grid-template-columns:1fr;padding:16px}}

/* TV: кольцо фокуса, цели 44 px (10-foot UI, без sl-*) */
body[data-page=tv] :is(a,button,[tabindex],[role=button],input,select):focus-visible,body.tv :is(a,button,[tabindex],[role=button]):focus-visible{outline:4px solid #e9b465!important;outline-offset:4px!important;box-shadow:0 0 0 8px rgba(233,180,101,.28),var(--ds-e2)!important;border-radius:12px;transform:scale(1.04);z-index:5}
body[data-page=tv] :is(a,button,[role=button]){min-height:44px;min-width:44px}
sl-card.s6lm-c::part(base),sl-card.s6zp-c::part(base),.s6ol-s sl-card::part(base){background:rgba(16,12,12,.84)}
.s6rc-r{background:rgba(16,12,12,.84)}
.s6ol{background:rgba(16,12,12,.78)}

/* SWATCH (scene) */
sl-button.s6sl[data-sw]{display:block}
sl-button.s6sl[data-sw]::part(base){width:100%;min-height:64px;justify-content:flex-start;text-align:left;background:var(--swatch);border-color:var(--swb);border-radius:16px}
sl-button.s6sl[data-sw][data-on]::part(base){outline:2px solid #e9b465;outline-offset:2px;box-shadow:var(--ds-e2)}
body[data-page=scene] #worlds>.card{padding:24px;border-radius:24px;box-shadow:var(--ds-e1)}
body[data-page=scene] #worlds>.card>div{gap:16px!important;grid-template-columns:repeat(auto-fill,minmax(144px,1fr))!important}
/* EFFECTS: Control Center */
body[data-page=effects] #lvls{gap:8px;padding:8px;border-radius:24px;background:rgba(255,235,220,.05);border:1px solid var(--ds-line,rgba(255,255,255,.14));width:fit-content;max-width:100%}
body[data-page=effects] #lvls sl-button.s6sl::part(base){border-radius:16px;min-width:112px}
body[data-page=effects] #tg{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
body[data-page=effects] #tg>p{grid-column:1/-1}
body[data-page=effects] #tg label{padding:16px;border-radius:24px;background:var(--ds-glass,rgba(255,235,220,.06));border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e1)}
body[data-page=effects] #det>div{gap:16px!important}
body[data-page=effects] #det>div>div{padding:16px;border-radius:24px;background:var(--ds-glass,rgba(255,235,220,.06));border:1px solid var(--ds-line,rgba(255,255,255,.14))}
/* CONSTRUCTOR: Framer */
.s6fr{padding:0!important;overflow:hidden;border-radius:24px!important}
.s6fr>h2{padding:16px 24px 0}
.s6fr-bar{position:absolute;z-index:6;left:50%;transform:translateX(-50%);top:72px;display:flex!important;gap:8px;padding:8px;border-radius:20px;background:rgba(16,12,12,.78);backdrop-filter:blur(20px);border:1px solid var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e2);margin:0!important;max-width:calc(100% - 32px);overflow-x:auto}
.s6fr #df{height:calc(100vh - 300px)!important;min-height:420px;border:0!important;background:radial-gradient(rgba(255,235,220,.16) 1px,transparent 1px) 0 0/24px 24px,rgba(8,6,6,.82)}
.s6fr-hint{position:absolute;inset:0;margin:auto;width:fit-content;height:fit-content;max-width:90%;flex-direction:column;align-items:center;gap:8px;text-align:center;padding:32px;border-radius:24px;background:rgba(16,12,12,.6);border:1px dashed var(--ds-line,rgba(255,255,255,.2));z-index:2}
.s6fr-hint sl-icon{font-size:32px;color:#e9b465}.s6fr-hint span{font-size:14px;color:var(--ds-mute,rgba(240,232,226,.62))}
.s6fr>p{padding:8px 24px 16px}
/* WIDGETS / GLANCE */
body[data-page=wid] #wg{gap:24px}
body[data-page=wid] #wg>.card{border-radius:24px;box-shadow:var(--ds-e1);padding:24px}
.s6gl sl-details::part(base){border-radius:16px;border-color:var(--ds-line,rgba(255,255,255,.14));background:rgba(255,235,220,.04)}
body[data-page=glance] .glx{border-radius:24px;box-shadow:var(--ds-e2);overflow:hidden}
body[data-page=glance] .glx-bar{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:12px 16px}
body[data-page=glance] .glx-bar span{flex:1 1 240px;font-size:12px}
/* ABOUT: Apple About This Mac */
.s6ab{margin:24px 0}.s6ab-h{display:flex;gap:24px;align-items:center;margin-bottom:24px}
.s6ab-l{display:grid;place-items:center;width:96px;height:96px;border-radius:28px;background:radial-gradient(circle at 30% 30%,#ffb066,#a3321f 70%);font-size:48px;box-shadow:var(--ds-e2)}
.s6ab h2{margin:0;font:700 clamp(28px,4vw,40px)/1.1 var(--head,inherit)}.s6ab-h p{margin:8px 0 0;font-size:14px;color:var(--ds-mute,rgba(240,232,226,.62))}
.s6ab-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.s6ab-c{--border-radius:24px;--padding:24px;--border-color:var(--ds-line,rgba(255,255,255,.14));box-shadow:var(--ds-e1)}
.s6ab-c::part(base){background:rgba(16,12,12,.84);height:100%}
.s6ab-c>sl-icon{font-size:24px;color:#e9b465}.s6ab-c h3{margin:8px 0 16px;font:600 16px/24px var(--sans,inherit)}
.s6ab-r{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid var(--ds-line,rgba(255,255,255,.1));font-size:14px;min-height:40px;align-items:center}
.s6ab-r span{color:var(--ds-mute,rgba(240,232,226,.62))}.s6ab-r b{font-weight:600;text-align:right}
.s6ab-p{margin-top:16px;--height:16px;--indicator-color:#e9b465;--track-color:rgba(255,255,255,.12);font-size:12px}.s6ab-p.warn{--indicator-color:#e5645a}
S6EOF_css
cat > nox-s6-cinema.js <<'S6EOF_js'
/* S6 cinema: навигация рядов (sl-icon-button), бейджи источника/года, иконки превью на sl-icon, главная кнопка героя. */
(function () {
  const root = document.getElementById('cnRows') || document.body; let t;
  function enhance() {
    document.querySelectorAll('.cn-row').forEach((row) => {
      const h = row.querySelector('h3'); if (h && !h.querySelector('.s6nav')) {
        const n = document.createElement('span'); n.className = 's6nav';
        n.innerHTML = '<sl-icon-button name="chevron-left" library="tabler" label="Назад" class="s6ib"></sl-icon-button><sl-icon-button name="chevron-right" library="tabler" label="Вперёд" class="s6ib"></sl-icon-button>';
        const sw = () => { const e = row.querySelector('.swiper'); return e && e.swiper; };
        n.children[0].addEventListener('click', () => { const s = sw(); if (s) s.slideTo(Math.max(0, s.activeIndex - 3)); });
        n.children[1].addEventListener('click', () => { const s = sw(); if (s) s.slideTo(s.activeIndex + 3); });
        h.appendChild(n);
      }
    });
    document.querySelectorAll('.cn-c').forEach((c) => {
      if (c.getAttribute('data-s6c')) return; c.setAttribute('data-s6c', '1');
      const pv = c.querySelector('.pv'), po = c.querySelector('.po'); if (!pv || !po) return;
      const txt = pv.textContent || ''; const y = (txt.match(/\b(19|20)\d\d\b/) || [])[0];
      const src = /Internet Archive/.test(txt) ? ['Архив', 'neutral'] : /YouTube/.test(txt) ? ['YouTube', 'danger'] : /Jellyfin/.test(txt) ? ['Jellyfin', 'success'] : null;
      const bd = document.createElement('span'); bd.className = 's6cb';
      bd.innerHTML = (src ? '<sl-badge pill variant="' + src[1] + '" class="s6bd">' + src[0] + '</sl-badge>' : '') + (y ? '<sl-badge pill variant="primary" class="s6bd">' + y + '</sl-badge>' : '');
      if (bd.children.length) po.appendChild(bd);
      const r = pv.querySelector('.r'); if (r) r.innerHTML = '<sl-icon library="tabler" name="player-play-filled"></sl-icon><sl-icon library="tabler" name="info-circle"></sl-icon>';
    });
    const hb = document.querySelector('.cn-hero .cn-btns button:not(.s6h)'); if (hb) hb.classList.add('ai');
    const first = document.querySelector('.cn-hero .cn-btns button'); if (first && !first.classList.contains('ai')) first.classList.add('ai');
  }
  const go = () => { try { enhance(); } catch (e) { } };
  const start = () => { go(); setTimeout(go, 1200); setTimeout(go, 3500); new MutationObserver(() => { clearTimeout(t); t = setTimeout(go, 200); }).observe(root, { childList: true, subtree: true }); };
  if (document.readyState !== 'loading') start(); else document.addEventListener('DOMContentLoaded', start);
})();
S6EOF_js
cat > nox-s6-lead.js <<'S6EOF_js'
/* S6: раскладки по лидерам. models (LM Studio), intents (Raycast), integrations (Zapier), install (Ollama). Только реальные данные: /glm/v1/models, qa/registry.json, сканер nox-registry.js. */
(function () {
  const page = document.body.getAttribute('data-page');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const wrap = () => document.querySelector('main.page .wrap');
  const ph = () => document.querySelector('main.page .wrap .ph');
  const after = (n) => { const p = ph(); if (p) p.insertAdjacentElement('afterend', n); else wrap().prepend(n); };
  const sk = (el, n) => { if (window.NOXds) NOXds.skeleton(el, n || 4); else el.textContent = 'Загрузка…'; };
  const empty = (el, o) => { if (window.NOXds) NOXds.empty(el, o); else el.textContent = (o && o.title) || 'Пусто'; };
  const toast = (m, v) => { const a = document.createElement('sl-alert'); a.variant = v || 'primary'; a.duration = 3500; a.closable = true; a.innerHTML = '<sl-icon slot="icon" library="tabler" name="' + (v === 'danger' ? 'alert-triangle' : 'check') + '"></sl-icon>' + esc(m); a.style.cssText = 'position:fixed;top:88px;right:16px;z-index:1200;max-width:min(420px,92vw)'; document.body.appendChild(a); a.toast ? a.toast() : (a.open = true); setTimeout(() => a.remove(), 4200); };

  function models() {
    const box = document.createElement('section'); box.className = 's6lm'; box.innerHTML =
      '<div class="s6lm-h"><sl-input class="s6lm-q s6f" size="large" clearable placeholder="Поиск модели (например qwen, 24b)"><sl-icon slot="prefix" library="tabler" name="search"></sl-icon></sl-input>' +
      '<sl-radio-group class="s6lm-f" size="medium" value="all"><sl-radio-button value="all">Все</sl-radio-button><sl-radio-button value="loaded">Загружены</sl-radio-button><sl-radio-button value="unloaded">В хранилище</sl-radio-button></sl-radio-group><sl-badge pill variant="neutral" class="s6bd s6lm-n">…</sl-badge></div><div class="s6lm-g" id="s6lmg"></div>';
    after(box); const g = box.querySelector('#s6lmg'); sk(g, 4);
    const old = document.querySelector('#models'); if (old) { const c = old.closest('.card'); if (c) c.setAttribute('hidden', ''); }
    let list = [], q = '', f = 'all';
    const draw = () => {
      const L = list.filter((m) => (f === 'all' || m.st === f) && (!q || m.id.toLowerCase().includes(q)));
      box.querySelector('.s6lm-n').textContent = L.length + ' / ' + list.length;
      if (!L.length) { empty(g, { icon: 'cpu', title: list.length ? 'Ничего не найдено' : 'Моделей нет', text: list.length ? 'Измените запрос или фильтр.' : 'Шлюз llama-swap не вернул список моделей.' }); return; }
      g.innerHTML = L.map((m, i) => '<sl-card class="s6lm-c"><div class="s6lm-t"><b>' + esc(m.id) + '</b></div><div class="s6lm-b"><sl-badge pill variant="' + (m.st === 'loaded' ? 'success' : 'neutral') + '" class="s6bd">' + (m.st === 'loaded' ? 'загружена' : 'в хранилище') + '</sl-badge>' + (m.size ? '<sl-badge pill variant="primary" class="s6bd">' + esc(m.size) + '</sl-badge>' : '') + '<sl-badge pill variant="neutral" class="s6bd">' + esc(m.owner) + '</sl-badge></div><div slot="footer" class="s6lm-a"><sl-button size="large" data-cp="' + esc(m.id) + '"><sl-icon slot="prefix" library="tabler" name="copy"></sl-icon>Копировать id</sl-button><sl-button size="large" variant="primary" data-ask="' + esc(m.id) + '"><sl-icon slot="prefix" library="tabler" name="sparkles"></sl-icon>О модели</sl-button><sl-button size="large" variant="warning" data-load="' + esc(m.id) + '"><sl-icon slot="prefix" library="tabler" name="player-play"></sl-icon>' + (m.st === 'loaded' ? 'Загружена' : 'Загрузить') + '</sl-button></div></sl-card>').join('');
    };
    box.querySelector('.s6lm-q').addEventListener('sl-input', (e) => { q = (e.target.value || '').toLowerCase().trim(); draw(); });
    box.querySelector('.s6lm-f').addEventListener('sl-change', (e) => { f = e.target.value; draw(); });
    g.addEventListener('click', (e) => {
      const c = e.target.closest('[data-cp]'), a = e.target.closest('[data-ask]');
      if (c) { navigator.clipboard && navigator.clipboard.writeText(c.dataset.cp).then(() => toast('Скопировано: ' + c.dataset.cp), () => toast('Буфер недоступен', 'danger')); }
      const ld = e.target.closest('[data-load]');
      if (ld && !ld.hasAttribute('disabled')) { const id = ld.dataset.load; const dlg = document.createElement('sl-dialog'); dlg.label = 'Загрузить модель?'; dlg.innerHTML = esc(id) + ' будет загружена в видеопамять через llama-swap. Текущие модели могут быть выгружены, ответы NOX на это время замедлятся.<sl-button slot="footer" size="large" data-n>Отмена</sl-button><sl-button slot="footer" size="large" variant="warning" data-y>Загрузить</sl-button>'; document.body.appendChild(dlg); dlg.show(); dlg.addEventListener('sl-after-hide', () => dlg.remove());
        dlg.querySelector('[data-n]').addEventListener('click', () => dlg.hide());
        dlg.querySelector('[data-y]').addEventListener('click', () => { dlg.hide(); ld.loading = true; fetch('/glm/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: id, max_tokens: 1, messages: [{ role: 'user', content: 'ok' }] }) }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); toast('Модель загружена: ' + id); const m = list.find((x) => x.id === id); if (m) m.st = 'loaded'; draw(); }).catch((er) => toast('Не удалось загрузить: ' + er.message, 'danger')).finally(() => { ld.loading = false; }); }); }
      if (a) { const b = document.getElementById('s6Ask'); if (b) { b.click(); setTimeout(() => { const q2 = document.querySelector('.s6dlg .s6q'); if (q2) { q2.value = 'Расскажи про модель ' + a.dataset.ask + ': для чего она подходит и стоит ли ей пользоваться в NOX?'; q2.focus(); } }, 300); } }
    });
    fetch('/glm/v1/models', { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then((j) => {
      list = (j.data || []).map((x) => ({ id: x.id, owner: x.owned_by || '—', st: x.status && x.status.value === 'loaded' ? 'loaded' : 'unloaded', size: ((x.id.match(/(\d+(?:\.\d+)?)b\b/i) || [])[1] || '') && (x.id.match(/(\d+(?:\.\d+)?)b\b/i)[1] + 'B') }));
      draw();
    }).catch((e) => { if (window.NOXds) NOXds.unavailable(g, 'Список моделей недоступен: ' + e.message); });
  }

  function intents() {
    const box = document.createElement('section'); box.className = 's6rc'; box.innerHTML = '<sl-input class="s6rc-q s6f" size="large" clearable placeholder="Команда NOX… (Enter — выполнить первую)"><sl-icon slot="prefix" library="tabler" name="terminal-2"></sl-icon></sl-input><div class="s6rc-l" id="s6rcl"></div><div class="s6rc-o" id="s6rco" aria-live="polite"></div>';
    after(box); const l = box.querySelector('#s6rcl'), o = box.querySelector('#s6rco'); sk(l, 5);
    if (!window.NOXcmd) { const s = document.createElement('script'); s.src = './nox-cmd.js'; document.head.appendChild(s); }
    let cmds = [], q = '';
    const draw = () => {
      const L = cmds.filter((c) => !q || (c.name + ' ' + c.desc).toLowerCase().includes(q));
      if (!L.length) { empty(l, { icon: 'terminal-2', title: 'Команд не найдено', text: 'Реестр qa/registry.json.' }); return; }
      l.innerHTML = L.map((c) => { const pr = Object.keys((c.params && c.params.properties) || {}); return '<div class="s6rc-r" data-n="' + esc(c.name) + '"><div class="s6rc-i"><sl-icon library="tabler" name="' + (c.confirm ? 'alert-triangle' : 'command') + '"></sl-icon></div><div class="s6rc-d"><b>' + esc(c.desc) + '</b><span class="mono">' + esc(c.name) + '</span></div>' + (c.confirm ? '<sl-badge pill variant="danger" class="s6bd">требует подтверждения</sl-badge>' : '') + pr.map((p) => '<sl-input class="s6f s6rc-p" size="medium" data-p="' + esc(p) + '" placeholder="' + esc(p) + '"></sl-input>').join('') + '<sl-button size="large" variant="' + (c.confirm ? 'danger' : 'primary') + '" data-run="' + esc(c.name) + '"><sl-icon slot="prefix" library="tabler" name="player-play"></sl-icon>Выполнить</sl-button></div>'; }).join('');
    };
    const run = async (name, row) => {
      const params = {}; if (row) row.querySelectorAll('[data-p]').forEach((i) => { if (i.value) params[i.dataset.p] = i.value; });
      o.innerHTML = '<sl-badge pill variant="warning" class="s6bd">выполняется</sl-badge> ' + esc(name);
      if (!window.NOXcmd) { o.innerHTML = '<sl-badge pill variant="danger" class="s6bd">недоступно</sl-badge> шина команд не загружена'; return; }
      try { const r = await window.NOXcmd(name, params); const ok = r && r.ok !== false; o.innerHTML = '<sl-badge pill variant="' + (ok ? 'success' : 'danger') + '" class="s6bd">' + (ok ? 'выполнено' : 'ошибка') + '</sl-badge> ' + esc(name) + ' <span class="mono">' + esc(JSON.stringify(r && (r.result || r.error || r.data) || '').slice(0, 200)) + '</span>'; } catch (e) { o.innerHTML = '<sl-badge pill variant="danger" class="s6bd">ошибка</sl-badge> ' + esc(e.message); }
    };
    l.addEventListener('click', (e) => { const b = e.target.closest('[data-run]'); if (b) run(b.dataset.run, b.closest('.s6rc-r')); });
    box.querySelector('.s6rc-q').addEventListener('sl-input', (e) => { q = (e.target.value || '').toLowerCase().trim(); draw(); });
    box.querySelector('.s6rc-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') { const r = l.querySelector('.s6rc-r'); if (r) run(r.dataset.n, r); } });
    fetch('qa/registry.json', { cache: 'no-cache' }).then((r) => r.json()).then((j) => { cmds = Object.keys(j.commands || {}).map((k) => Object.assign({ name: k }, j.commands[k])); draw(); }).catch((e) => { if (window.NOXds) NOXds.unavailable(l, 'Реестр команд недоступен: ' + e.message); });
  }

  function integrations() {
    const box = document.createElement('section'); box.className = 's6zp'; box.innerHTML = '<div class="s6lm-h"><sl-input class="s6zp-q s6f" size="large" clearable placeholder="Поиск интеграции"><sl-icon slot="prefix" library="tabler" name="search"></sl-icon></sl-input><sl-radio-group class="s6zp-f" size="medium" value="all"><sl-radio-button value="all">Все</sl-radio-button><sl-radio-button value="on">Подключено</sl-radio-button><sl-radio-button value="idle">Лежит</sl-radio-button><sl-radio-button value="no">Нет</sl-radio-button></sl-radio-group></div><div class="s6zp-g" id="s6zg"></div>';
    const sum = document.querySelector('main.page .wrap > section.card'); (sum || ph()).insertAdjacentElement('afterend', box);
    const g = box.querySelector('#s6zg'); sk(g, 4); const old = document.querySelector('#groups'); if (old) old.setAttribute('hidden', '');
    let items = [], q = '', f = 'all'; const ST = { on: ['подключено', 'success'], idle: ['лежит', 'warning'], no: ['нет', 'neutral'] };
    const draw = () => { const L = items.filter((x) => (f === 'all' || x.st === f) && (!q || (x.n + ' ' + x.g).toLowerCase().includes(q))); if (!L.length) { empty(g, { icon: 'plug', title: 'Ничего не найдено', text: 'Измените запрос или фильтр.' }); return; }
      g.innerHTML = L.map((x) => '<sl-card class="s6zp-c"><div class="s6zp-t"><sl-icon library="tabler" name="' + (x.st === 'on' ? 'plug-connected' : x.st === 'idle' ? 'plug' : 'plug-off') + '"></sl-icon><b>' + esc(x.n) + '</b></div><div class="s6zp-s">' + esc(x.g || '') + (x.ver ? ' · ' + esc(x.ver) : '') + '</div><sl-badge pill variant="' + ST[x.st][1] + '" class="s6bd">' + ST[x.st][0] + '</sl-badge></sl-card>').join(''); };
    box.querySelector('.s6zp-q').addEventListener('sl-input', (e) => { q = (e.target.value || '').toLowerCase().trim(); draw(); });
    box.querySelector('.s6zp-f').addEventListener('sl-change', (e) => { f = e.target.value; draw(); });
    const load = () => import('./nox-registry.js').then((m) => m.scan()).then((r) => { items = (r.libs || []).concat(r.assets || []).map((x) => Object.assign({ g: x.g || 'Ассеты' }, x)); draw(); }).catch((e) => { if (window.NOXds) NOXds.unavailable(g, 'Сканер недоступен: ' + e.message); });
    load(); const rs = document.getElementById('rescan'); if (rs) rs.addEventListener('click', () => { sk(g, 4); setTimeout(load, 300); });
  }

  function install() {
    const hero = document.createElement('section'); hero.className = 's6ol';
    hero.innerHTML = '<div class="s6ol-t"><h2>Установите NOX как приложение</h2><p>Один клик: окно без адресной строки, уведомления и работа офлайн.</p><div class="s6ol-b"><sl-button size="large" variant="primary" id="s6Inst"><sl-icon slot="prefix" library="tabler" name="download"></sl-icon>Установить</sl-button><sl-button size="large" id="s6Push"><sl-icon slot="prefix" library="tabler" name="bell"></sl-icon>Включить уведомления</sl-button></div></div><div class="s6ol-s"><sl-card><sl-icon library="tabler" name="app-window"></sl-icon><b>Приложение</b><sl-badge pill variant="neutral" class="s6bd" id="s6s1">проверка</sl-badge></sl-card><sl-card><sl-icon library="tabler" name="bell"></sl-icon><b>Уведомления</b><sl-badge pill variant="neutral" class="s6bd" id="s6s2">проверка</sl-badge></sl-card><sl-card><sl-icon library="tabler" name="wifi-off"></sl-icon><b>Офлайн</b><sl-badge pill variant="neutral" class="s6bd" id="s6s3">проверка</sl-badge></sl-card></div>';
    after(hero);
    const clickOrig = (id) => { const b = document.getElementById(id); if (b && !b.hidden) b.click(); else toast('Недоступно в этом браузере: ' + (id === 'instBtn' ? 'установка уже выполнена или не поддерживается' : 'уведомления не разрешены'), 'danger'); };
    hero.querySelector('#s6Inst').addEventListener('click', () => clickOrig('instBtn')); hero.querySelector('#s6Push').addEventListener('click', () => clickOrig('pushBtn'));
    const st = (id, from) => { const t = (document.getElementById(from) || {}).textContent || ''; const e = hero.querySelector('#' + id); const T = t.replace(/\s+/g, ' ').trim().slice(0, 40); const ok = /установлен|включен|активн|работает|готов/i.test(T); const bad = /не поддерж|заблок|нет|отключ|недоступ/i.test(T); e.textContent = T && T !== '—' ? T : 'проверка'; e.variant = ok ? 'success' : bad ? 'danger' : 'neutral'; };
    const tick = () => { st('s6s1', 'ins'); st('s6s2', 'pushT'); st('s6s3', 'sw'); const ib = document.getElementById('instBtn'); hero.querySelector('#s6Inst').toggleAttribute('disabled', !!(ib && ib.hidden)); };
    tick(); setInterval(tick, 1000);
  }


  function constructor_() {
    const card = document.querySelector('main.page .wrap > section.card'); const df = document.getElementById('df'); if (!card || !df) return;
    card.classList.add('s6fr'); const bar = card.querySelector('.acts'); if (bar) { bar.classList.add('s6fr-bar'); df.before(bar); }
    const hint = document.createElement('div'); hint.className = 's6fr-hint'; hint.innerHTML = '<sl-icon library="tabler" name="hierarchy-2"></sl-icon><b>Холст пуст</b><span>Добавьте первый узел и соедините выходы со входами.</span><sl-button size="large" variant="primary" id="s6fAdd"><sl-icon slot="prefix" library="tabler" name="plus"></sl-icon>Добавить узел</sl-button>';
    df.style.position = 'relative'; df.appendChild(hint);
    hint.querySelector('#s6fAdd').addEventListener('click', () => { const b = document.getElementById('nAdd'); if (b) b.click(); });
    const upd = () => { hint.style.display = df.querySelector('.drawflow-node') ? 'none' : 'flex'; }; upd(); new MutationObserver(upd).observe(df, { childList: true, subtree: true });
  }
  function glance() {
    const bar = document.querySelector('.glx-bar'); if (!bar) return; const a = bar.querySelector('a');
    const st = document.createElement('sl-badge'); st.pill = true; st.className = 's6bd'; st.variant = 'neutral'; st.textContent = 'проверка'; bar.prepend(st);
    if (a) { const b = document.createElement('sl-button'); b.size = 'large'; b.href = a.href; b.target = '_blank'; b.rel = 'noopener'; b.innerHTML = '<sl-icon slot="prefix" library="tabler" name="external-link"></sl-icon>Открыть отдельно'; b.className = 's6sl'; a.replaceWith(b); }
    fetch('/svc/glance/', { cache: 'no-store' }).then((r) => { st.textContent = r.ok ? 'Glance работает' : 'HTTP ' + r.status; st.variant = r.ok ? 'success' : 'danger'; }).catch(() => { st.textContent = 'недоступно'; st.variant = 'danger'; });
  }
  function widgets() {
    const g = document.getElementById('wg'); if (!g) return; const c = document.createElement('section'); c.className = 'card c12 s6gl'; c.setAttribute('data-s6', 'skip');
    c.innerHTML = '<h2>Лента Glance <span class="r mono">/svc/glance/</span></h2><sl-details summary="Показать погоду, новости и рынки Glance"><iframe src="about:blank" data-src="/svc/glance/" title="Glance" loading="lazy" style="width:100%;height:560px;border:0;border-radius:16px;background:#0a0808"></iframe></sl-details>';
    g.appendChild(c); const d = c.querySelector('sl-details'); d.addEventListener('sl-show', () => { const f = c.querySelector('iframe'); if (f.src === 'about:blank') f.src = f.dataset.src; });
  }
  function about() {
    const hero = document.createElement('section'); hero.className = 's6ab'; hero.innerHTML = '<div class="s6ab-h"><div class="s6ab-l"><sl-icon library="tabler" name="brain"></sl-icon></div><div><h2>NOX HELION</h2><p id="s6abv">Загрузка данных…</p></div></div><div class="s6ab-g" id="s6abg"></div>';
    after(hero); const g = hero.querySelector('#s6abg'); sk(g, 4);
    const row = (k, v) => '<div class="s6ab-r"><span>' + esc(k) + '</span><b>' + v + '</b></div>';
    const bar = (pct, label) => '<sl-progress-bar value="' + Math.round(pct) + '" class="s6ab-p ' + (pct > 90 ? 'warn' : '') + '">' + esc(label) + '</sl-progress-bar>';
    const load = () => Promise.all([fetch('/api/nox-live', { cache: 'no-store' }).then((r) => r.json()), fetch('/glm/v1/models', { cache: 'no-store' }).then((r) => r.json()).catch(() => null), fetch('/glm/running', { cache: 'no-store' }).then((r) => r.json()).catch(() => null)]).then(([L, M, R]) => {
      const n = M && M.data ? M.data.length : '—', run = R && R.running ? R.running.length : '—'; const sv = L.services || {}, ks = Object.keys(sv), ok = ks.filter((k) => sv[k].ok).length;
      hero.querySelector('#s6abv').textContent = 'Данные ' + (L.ts || '').replace('T', ' ').replace('Z', ' UTC') + ' · источник ' + (L.source || '—');
      g.innerHTML = '<sl-card class="s6ab-c"><sl-icon library="tabler" name="cpu"></sl-icon><h3>Видеокарта</h3>' + row('Модель', esc(L.gpu.name)) + row('Загрузка', Math.round(L.gpu.util_pct) + ' %') + row('Температура', Math.round(L.gpu.temp_c) + ' °C') + row('Питание', Math.round(L.gpu.power_w) + ' Вт') + bar(L.gpu.vram_pct, 'VRAM ' + (L.gpu.vram_used_mib / 1024).toFixed(1) + ' / ' + (L.gpu.vram_total_mib / 1024).toFixed(1) + ' ГБ') + '</sl-card>'
        + '<sl-card class="s6ab-c"><sl-icon library="tabler" name="database"></sl-icon><h3>Диск</h3>' + row('Свободно', L.disk.free_gb + ' ГБ') + row('Всего', L.disk.total_gb + ' ГБ') + bar(L.disk.used_pct, 'Занято ' + L.disk.used_pct + ' %') + (L.disk.used_pct > 90 ? '<sl-badge pill variant="danger" class="s6bd">мало места</sl-badge>' : '') + '</sl-card>'
        + '<sl-card class="s6ab-c"><sl-icon library="tabler" name="device-desktop-analytics"></sl-icon><h3>Память и слоты</h3>' + row('ОЗУ всего', L.ram.total_gb + ' ГБ') + row('ОЗУ доступно', L.ram.avail_gb + ' ГБ') + row('Слотов занято', L.slots.busy + ' / ' + L.slots.n) + row('Контекст слота', L.slots.ctx_each) + '</sl-card>'
        + '<sl-card class="s6ab-c"><sl-icon library="tabler" name="cube"></sl-icon><h3>Модели и службы</h3>' + row('Моделей в шлюзе', n) + row('Загружено сейчас', run) + row('Службы в строю', ok + ' / ' + ks.length) + '<sl-badge pill variant="' + (ok === ks.length ? 'success' : 'warning') + '" class="s6bd">' + (ok === ks.length ? 'всё работает' : 'есть сбои') + '</sl-badge></sl-card>';
    }).catch((e) => { if (window.NOXds) NOXds.unavailable(g, 'Данные /api/nox-live недоступны: ' + e.message); });
    load(); setInterval(load, 8000);
  }

  const go = () => { if (!wrap()) return setTimeout(go, 300); try { ({ models, intents, integrations, install, constructor: constructor_, glance, wid: widgets, about }[page === 'core' ? 'models' : page === 'integ' ? 'integrations' : page] || (() => { }))(); } catch (e) { } };
  if (['core', 'intents', 'integ', 'install', 'constructor', 'glance', 'wid', 'about'].includes(page)) { if (document.readyState !== 'loading') setTimeout(go, 400); else document.addEventListener('DOMContentLoaded', () => setTimeout(go, 400)); }
})();
S6EOF_js
python3 - photo,news,cinema,music,studio,creative,board,tv,training,projects,calendar,dispatcher,system,growth,memory,consciousness,organism,soul,selffeel,nexus,constructor,intents,models,scene,effects,widgets,about,integrations,glance,install <<'PY'
import sys,os,shutil
for p in sys.argv[1].split(','):
    f=p+'.html'
    if not os.path.exists(f): print('NOFILE',f); continue
    t=open(f).read()
    if 'nox-s6-sl.js' in t: print('already',p)
    if p=='cinema' and 'nox-s6-cinema.js' not in t:
        t=t.replace('</body>','<script src="./nox-s6-cinema.js?v=1" defer></script>\n</body>',1); open(f,'w').write(t)
    if p in ('models','intents','integrations','install','constructor','glance','widgets','about') and 'nox-s6-lead.js' not in t:
        t=t.replace('</body>','<script src="./nox-s6-lead.js?v=1" defer></script>\n</body>',1); open(f,'w').write(t)
    if 'nox-s6-sl.js' in t: continue
    if not os.path.exists(f+'.bak_s6_1'): shutil.copy(f,f+'.bak_s6_1')
    t=t.replace('</head>','<link rel="stylesheet" href="./nox-s6.css?v=1">\n</head>',1)
    t=t.replace('</body>','<script src="./vendor/shoelace/cdn/shoelace.js" type="module"></script>\n<script src="./nox-s6-sl.js?v=1" defer></script>\n</body>',1) if False else t.replace('</body>','<script src="./nox-s6-sl.js?v=1" defer></script>\n</body>',1)
    open(f,'w').write(t); print('injected',p)
PY
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; $PY -c 'import playwright' 2>/dev/null || PY=python3
cat > /tmp/s6_shot.py <<'S6EOF_PY'
import asyncio,base64,io,os,json
from playwright.async_api import async_playwright
from PIL import Image
PAGES=os.environ.get("S6P","photo").split(","); CLK=os.environ.get("S6CLICK","1")=="1"
B="http://127.0.0.1:8091/web/"
def emit(name,raw,w):
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width>w: im=im.resize((w,int(im.height*w/im.width)))
    b=io.BytesIO(); im.save(b,'JPEG',quality=35,optimize=True); s=base64.b64encode(b.getvalue()).decode()
    print("B64_%s_BEGIN"%name)
    for i in range(0,len(s),900): print(s[i:i+900])
    print("B64_%s_END"%name)
JS_STAT="""()=>{const v=e=>e.offsetParent&&e.getBoundingClientRect().width>0;
const nat=[...document.querySelectorAll('main.page button,main.page select,main.page textarea,main.page input:not([type=file])')].filter(v).filter(e=>!e.closest('[class*=FIE_],.plyr,.swiper,sl-dialog,.cm-editor,canvas')).map(e=>(e.id||e.className||e.tagName).toString().slice(0,22));
const sl=[...document.querySelectorAll('sl-button.s6sl,sl-select,sl-input,sl-textarea,sl-checkbox,sl-range')].filter(v).length;
const small=[...document.querySelectorAll('main.page sl-button,main.page sl-select,main.page sl-input')].filter(v).filter(e=>e.getBoundingClientRect().height<43).length;
const fs=[...document.querySelectorAll('main.page *')].filter(e=>e.children.length==0&&e.textContent.trim()&&v(e)&&parseFloat(getComputedStyle(e).fontSize)<12).length;
return {native:nat.length,nativeList:nat.slice(0,8),sl:sl,small:small,fs12:fs,ow:[document.documentElement.scrollWidth,innerWidth]}}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for pg_ in PAGES:
            for vp,(w,h,ow) in {"d":(1440,900,1000),"m":(390,844,390)}.items():
                ctx=await b.new_context(viewport={"width":w,"height":h}); pg=await ctx.new_page(); errs=[]; reqs=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:120])); pg.on("request",lambda r:reqs.append(r.url[-40:]) if r.method=="POST" or "/api/" in r.url else None)
                pg.on("filechooser",lambda fc:None); pg.on("dialog",lambda d:asyncio.ensure_future(d.dismiss()))
                try: await pg.goto(B+pg_+".html",wait_until="load",timeout=40000)
                except Exception as e: print("GOTO",pg_,str(e)[:80])
                await pg.wait_for_timeout(5500)
                raw=await pg.screenshot(type="jpeg",quality=60); emit(pg_+"_"+vp,raw,ow)
                print("STAT",pg_,vp,json.dumps(await pg.evaluate(JS_STAT),ensure_ascii=False),"errs",errs[:3])
                if vp=="d" and CLK:
                    n=await pg.evaluate("()=>document.querySelectorAll('main.page sl-button.s6sl').length"); dead=0; e0=len(errs)
                    for i in range(min(n,45)):
                        try:
                            sig0=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length"); r0=len(reqs)
                            await pg.evaluate("(i)=>{const e=document.querySelectorAll('main.page sl-button.s6sl')[i];if(e&&!e.disabled){e.scrollIntoView({block:'center'});e.click()}}",i)
                            await pg.wait_for_timeout(150)
                            sig1=await pg.evaluate("()=>document.body.innerHTML.length+'|'+document.querySelectorAll('sl-dialog[open]').length")
                            if sig0==sig1 and len(reqs)==r0: dead+=1
                            await pg.keyboard.press("Escape")
                        except Exception as e: pass
                    print("CLICK",pg_,"sl-buttons",n,"no-visible-effect",dead,"newerrs",errs[e0:e0+3])
                await ctx.close()
        await b.close()
asyncio.run(main())
S6EOF_PY
S6CLICK=0 S6P=scene,effects,about $PY /tmp/s6_shot.py 2>&1 | tail -n 2000
