/* NOX · стеклянные поля вместо нативных select / input[type=date|time] / datalist. Исходный элемент остаётся в DOM (скрыт), его .value и события работают как раньше. */
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = (n) => String(n).padStart(2, '0');
const MON = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
let pop = null, popOwner = null;
function closePop() { if (pop) { pop.remove(); pop = null; } if (popOwner) { popOwner.setAttribute('aria-expanded', 'false'); popOwner = null; } }
function openPop(owner, html, wire) {
  closePop(); pop = document.createElement('div'); pop.className = 'gpop'; pop.innerHTML = html; document.body.appendChild(pop); popOwner = owner; owner.setAttribute('aria-expanded', 'true');
  const r = owner.getBoundingClientRect(), w = Math.max(r.width, pop.classList.contains('gcal') ? 296 : 160);
  pop.style.minWidth = w + 'px'; const ph = pop.offsetHeight; let top = r.bottom + 4; if (top + ph > innerHeight - 8) top = Math.max(8, r.top - ph - 4);
  pop.style.top = top + 'px'; pop.style.left = Math.max(8, Math.min(innerWidth - pop.offsetWidth - 8, r.left)) + 'px';
  wire(pop); const sel = pop.querySelector('[aria-selected=true],.sel'); if (sel) sel.scrollIntoView({ block: 'nearest' });
}
addEventListener('pointerdown', (e) => { if (pop && !pop.contains(e.target) && !(popOwner && popOwner.contains(e.target))) closePop(); }, true);
addEventListener('keydown', (e) => { if (e.key === 'Escape' && pop) { const o = popOwner; closePop(); o && o.focus(); } });
addEventListener('resize', closePop); addEventListener('scroll', (e) => { if (pop && !pop.contains(e.target)) closePop(); }, true);
const fire = (el) => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); };
function hook(el, refresh) { /* .value = ... из кода тоже обновляет отображение */
  const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value'); if (!d) return;
  Object.defineProperty(el, 'value', { configurable: true, get() { return d.get.call(this); }, set(v) { d.set.call(this, v); refresh(); } });
}
function shell(el, cls) {
  const w = document.createElement('span'); w.className = 'gfld ' + cls; el.parentNode.insertBefore(w, el); w.appendChild(el); el.classList.add('g-native'); el.setAttribute('tabindex', '-1'); el.setAttribute('aria-hidden', 'true');
  const b = document.createElement('button'); b.type = 'button'; b.className = 'gbtn'; b.setAttribute('aria-haspopup', 'listbox'); b.setAttribute('aria-expanded', 'false');
  const lab = el.closest('label'); if (lab) { const sp = lab.querySelector(':scope > span'); if (sp) { sp.id = sp.id || 'gl' + Math.random().toString(36).slice(2, 7); b.setAttribute('aria-labelledby', sp.id); } }
  w.appendChild(b); if (lab) lab.addEventListener('click', (e) => { if (e.target === lab || e.target.tagName === 'SPAN') { e.preventDefault(); b.focus(); } });
  return b;
}
export function glassSelect(el) {
  if (el.dataset.glass) return; el.dataset.glass = '1'; const b = shell(el, 'gsel');
  const refresh = () => { const o = el.options[el.selectedIndex]; b.innerHTML = '<span class="gv">' + esc(o ? o.textContent : '') + '</span><sl-icon library="tabler" name="chevron-down"></sl-icon>'; b.disabled = el.disabled; };
  hook(el, refresh); new MutationObserver(refresh).observe(el, { childList: true, subtree: true, attributes: true }); refresh();
  const open = () => { if (popOwner === b) { closePop(); return; } openPop(b, '<ul role="listbox">' + [...el.options].map((o, i) => '<li role="option" tabindex="-1" data-i="' + i + '" aria-selected="' + (i === el.selectedIndex) + '"' + (o.disabled ? ' aria-disabled="true"' : '') + '>' + esc(o.textContent) + '</li>').join('') + '</ul>', (p) => {
    const pick = (li) => { if (!li || li.getAttribute('aria-disabled')) return; el.selectedIndex = +li.dataset.i; refresh(); fire(el); closePop(); b.focus(); };
    p.addEventListener('click', (e) => pick(e.target.closest('li')));
    p.addEventListener('keydown', (e) => { const l = [...p.querySelectorAll('li')], i = l.indexOf(document.activeElement); if (e.key === 'ArrowDown') { e.preventDefault(); (l[i + 1] || l[0]).focus(); } else if (e.key === 'ArrowUp') { e.preventDefault(); (l[i - 1] || l[l.length - 1]).focus(); } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(document.activeElement.closest('li')); } });
    (p.querySelector('[aria-selected=true]') || p.querySelector('li')).focus();
  }); };
  b.addEventListener('click', open); b.addEventListener('keydown', (e) => { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); open(); } });
}
const fmtD = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(v) ? v.slice(8) + '.' + v.slice(5, 7) + '.' + v.slice(0, 4) : '');
export function glassDate(el) {
  if (el.dataset.glass) return; el.dataset.glass = '1'; const b = shell(el, 'gdate');
  const refresh = () => { b.innerHTML = '<span class="gv' + (el.value ? '' : ' ph') + '">' + (fmtD(el.value) || 'дд.мм.гггг') + '</span><sl-icon library="tabler" name="calendar"></sl-icon>'; b.disabled = el.disabled; };
  hook(el, refresh); refresh();
  b.addEventListener('click', () => {
    if (popOwner === b) { closePop(); return; } const base = /^\d{4}-\d{2}-\d{2}$/.test(el.value) ? new Date(el.value + 'T00:00:00') : new Date(); let y = base.getFullYear(), m = base.getMonth();
    const draw = (p) => {
      const first = new Date(y, m, 1), off = (first.getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate(), today = new Date(), iso = (d) => y + '-' + pad(m + 1) + '-' + pad(d);
      let cells = ''; for (let i = 0; i < off; i++) cells += '<i></i>'; for (let d = 1; d <= days; d++) { const t = today.getFullYear() === y && today.getMonth() === m && today.getDate() === d; cells += '<button type="button" data-d="' + iso(d) + '" class="' + (iso(d) === el.value ? 'sel ' : '') + (t ? 'today' : '') + '">' + d + '</button>'; }
      p.innerHTML = '<div class="gh"><button type="button" data-n="-1" aria-label="Предыдущий месяц"><sl-icon library="tabler" name="chevron-left"></sl-icon></button><b>' + MON[m] + ' ' + y + '</b><button type="button" data-n="1" aria-label="Следующий месяц"><sl-icon library="tabler" name="chevron-right"></sl-icon></button></div><div class="gw"><span>Пн</span><span>Вт</span><span>Ср</span><span>Чт</span><span>Пт</span><span>Сб</span><span>Вс</span></div><div class="gg">' + cells + '</div><div class="gf"><button type="button" data-t="1">Сегодня</button><button type="button" data-c="1">Очистить</button></div>';
    };
    openPop(b, '', (p) => {
      p.classList.add('gcal'); draw(p);
      p.addEventListener('click', (e) => { const t = e.target.closest('button'); if (!t) return;
        if (t.dataset.n) { m += +t.dataset.n; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; } draw(p); return; }
        let v = null; if (t.dataset.d) v = t.dataset.d; else if (t.dataset.t) { const n = new Date(); v = n.getFullYear() + '-' + pad(n.getMonth() + 1) + '-' + pad(n.getDate()); } else if (t.dataset.c) v = '';
        if (v != null) { el.value = v; fire(el); closePop(); b.focus(); } });
    });
  });
}
export function glassTime(el) {
  if (el.dataset.glass) return; el.dataset.glass = '1'; const b = shell(el, 'gtime');
  const refresh = () => { b.innerHTML = '<span class="gv' + (el.value ? '' : ' ph') + '">' + (el.value || 'чч:мм') + '</span><sl-icon library="tabler" name="clock"></sl-icon>'; b.disabled = el.disabled; };
  hook(el, refresh); refresh();
  b.addEventListener('click', () => { if (popOwner === b) { closePop(); return; } let [h, mi] = /^\d{2}:\d{2}$/.test(el.value) ? el.value.split(':').map(Number) : [9, 0];
    const col = (n, step, cur, k) => '<div class="gcol" data-k="' + k + '">' + Array.from({ length: Math.ceil(n / step) }, (_, i) => i * step).map((v) => '<button type="button" data-v="' + v + '" class="' + (v === cur ? 'sel' : '') + '">' + pad(v) + '</button>').join('') + '</div>';
    openPop(b, '<div class="gtm">' + col(24, 1, h, 'h') + col(60, 5, mi - (mi % 5), 'm') + '</div><div class="gf"><button type="button" data-c="1">Очистить</button><button type="button" data-ok="1">Готово</button></div>', (p) => {
      p.classList.add('gtp'); const set = () => { el.value = pad(h) + ':' + pad(mi); fire(el); };
      p.addEventListener('click', (e) => { const t = e.target.closest('button'); if (!t) return; if (t.dataset.c) { el.value = ''; fire(el); closePop(); return; } if (t.dataset.ok) { closePop(); b.focus(); return; }
        const k = t.parentNode.dataset.k; if (k === 'h') h = +t.dataset.v; else mi = +t.dataset.v; t.parentNode.querySelectorAll('button').forEach((x) => x.classList.toggle('sel', x === t)); set(); });
    }); });
}
export function glassSuggest(el) { /* input[list]: подсказки в стеклянной панели вместо нативного datalist */
  if (el.dataset.glass) return; el.dataset.glass = '1'; const dl = document.getElementById(el.getAttribute('list')); if (!dl) return; el.removeAttribute('list'); el.setAttribute('autocomplete', 'off');
  const show = () => { const q = el.value.trim().toLowerCase(), items = [...dl.options].map((o) => o.value).filter((v) => v && (!q || v.toLowerCase().includes(q)) && v !== el.value).slice(0, 12);
    if (!items.length) { if (popOwner === el) closePop(); return; } openPop(el, '<ul role="listbox">' + items.map((v) => '<li role="option" tabindex="-1">' + esc(v) + '</li>').join('') + '</ul>', (p) => { p.addEventListener('pointerdown', (e) => e.preventDefault()); p.addEventListener('click', (e) => { const li = e.target.closest('li'); if (li) { el.value = li.textContent; fire(el); closePop(); } }); }); };
  el.addEventListener('focus', show); el.addEventListener('input', show);
}
export function enhance(root) {
  (root || document).querySelectorAll('select:not([data-native]):not([data-glass]):not([multiple])').forEach(glassSelect);
  (root || document).querySelectorAll('input[type=date]:not([data-native]):not([data-glass])').forEach(glassDate);
  (root || document).querySelectorAll('input[type=time]:not([data-native]):not([data-glass])').forEach(glassTime);
  (root || document).querySelectorAll('input[list]:not([data-native]):not([data-glass])').forEach(glassSuggest);
}
enhance(); let t = 0; new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => enhance(), 50); }).observe(document.body, { childList: true, subtree: true });
