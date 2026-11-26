/* C: чистый режим чата (как ChatGPT/Claude): одна колонка чтения, «Режимы»/«Шаблоны»/«Система» по запросу, компактные иконки под ответом, ≤2 чипа над полем.
   Флаг: localStorage nox.clean=0 или ?classic=1 вернёт прежний вид. Все функции сохранены, просто открываются по кнопке. */
/* K8meta: эмоция из meta.emo подсвечивает интерфейс; вызывается после каждого ответа */
(function(){const w=window;let n=0;const t=setInterval(()=>{if(++n>80)clearInterval(t);if(!w.__rqRender||w.__rqRender.__k8)return;const o=w.__rqRender;const f=function(meta,nox){try{if(meta&&w.K8meta)w.K8meta.handle({meta:meta})}catch(e){}return o.apply(this,arguments)};f.__k8=1;w.__rqRender=f;clearInterval(t)},250);
if(document.head&&!document.querySelector('script[src*="nox-k8-meta"]')){const a=document.createElement('script');a.src='/web/nox-k8-meta.js';a.defer=true;(document.head||document.documentElement).appendChild(a)}})();
(function () {
  'use strict';
  if (localStorage.getItem('nox.clean') === '0' || /[?&]classic=1/.test(location.search)) return;
  try { localStorage.setItem('nox.cx5.col', JSON.stringify({ cmd: 0, pr: 0, sys: 0 })); } catch (e) { }
  const $ = (s, r) => (r || document).querySelector(s), $$ = (s, r) => [...(r || document).querySelectorAll(s)];
  const t0 = setInterval(() => { if ($('#stage') && $('#composer') && $('.cx5-cmd') && $('.cx-right') && $('.cx5-pr')) { clearInterval(t0); init(); } }, 250);
  function init() {
    const B = document.body; B.classList.add('cw-clean'); ['cmd', 'pr', 'sys'].forEach((k) => B.classList.add('cx5-no-' + k));
    const form = $('#form'), comp = $('#composer');
    const bar = document.createElement('div'); bar.className = 'cw-bar';
    bar.innerHTML = '<sl-button size="small" outline data-p="cmd" aria-haspopup="true">⚙ Режимы</sl-button><sl-button size="small" outline data-p="pr" aria-haspopup="true">Шаблоны</sl-button><sl-button size="small" outline data-p="sys" class="cw-sysbtn" aria-haspopup="true">Система</sl-button><span class="cw-chips" role="group" aria-label="Подсказки"></span>';
    form.insertBefore(bar, comp);
    const nb = document.createElement('sl-button'); nb.size = 'small'; nb.outline = true; nb.className = 'cw-notebtn'; nb.setAttribute('aria-label', 'Блокнот'); nb.title = 'Блокнот'; nb.innerHTML = '<sl-icon library="tabler" name="notebook"></sl-icon>'; nb.addEventListener('click', (e) => { e.stopPropagation(); try { window.NOXNote && window.NOXNote.toggle(); } catch (x) { } }); bar.appendChild(nb);
    const closeAll = () => ['cmd', 'pr', 'sys'].forEach((k) => B.classList.remove('cw-open-' + k));
    bar.addEventListener('click', (e) => { const b = e.target.closest('[data-p]'); if (!b) return; const k = b.dataset.p, was = B.classList.contains('cw-open-' + k); closeAll(); if (!was) B.classList.add('cw-open-' + k); e.stopPropagation(); });
    document.addEventListener('click', (e) => { if (!e.target.closest('.cx5-cmd,.cx5-pr,.cx-right,.cw-bar')) closeAll(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAll(); });
    /* индикатор нагрузки в кнопке «Система» */
    setInterval(() => { const g = $('#cx5G'); const sb = $('.cw-sysbtn'); if (!g || !sb) return; const x = [...g.children].map((c) => (c.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean); const gpu = x.find((s) => /GPU/.test(s)); sb.textContent = gpu && /\d/.test(gpu) ? 'Система · ' + gpu.replace(/\s*GPU\s*/, ' GPU').replace(/(\d+%)\s*GPU/, 'GPU $1') : 'Система'; }, 5000);
    /* шаблоны: длинный текст обрезается, полный по наведению */
    const fixTpl = () => $$('.cx5-list > *').forEach((el) => { if (!el.title) el.title = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 400); });
    setInterval(fixTpl, 2000);
    /* кнопка STOP вне поля ввода скрыта: стоп только внутри кнопки отправки */
    const hideStop = () => $$('button,a,sl-button').forEach((el) => { if (el.closest('#composer')) return; if ((el.textContent || '').trim().toUpperCase() === 'STOP') { el.classList.add('cw-hide'); el.style.setProperty('display','none','important'); } });
    setInterval(hideStop, 1500);
    /* иконки под ответом, чипы эмоции -> максимум 2 над полем ввода */
    function decorate() {
      $$('#feed .m.a').forEach((m) => {
        const acts = m.querySelector('.acts'); if (!acts) return;
        const ra = m.querySelector('.rq-act'); if (ra && ra.parentElement !== acts) { ra.setAttribute('aria-label', 'Ответить'); ra.title = 'Ответить'; acts.appendChild(ra); }
        if (window.NOXNote && window.NOXNote.add && !acts.querySelector('.cw-pin')) { const p = document.createElement('button'); p.type = 'button'; p.className = 'cw-pin'; p.title = 'В заметку (правый клик: в NOX / на доску)'; p.setAttribute('aria-label', 'В заметку'); p.innerHTML = '<sl-icon library="tabler" name="pin"></sl-icon>'; const txt = () => ((m.querySelector('.txt') || m.querySelector('.bubble') || m).innerText || '').trim(); const add = (to) => Promise.resolve(window.NOXNote.add(txt(), { to })).then(() => { p.innerHTML = '<sl-icon library="tabler" name="check"></sl-icon>'; setTimeout(() => { p.innerHTML = '<sl-icon library="tabler" name="pin"></sl-icon>'; }, 1500); }).catch(() => { }); p.addEventListener('click', () => add('pad')); p.addEventListener('contextmenu', (e) => { e.preventDefault(); $$('.cw-pinmenu').forEach((x) => x.remove()); const mn = document.createElement('div'); mn.className = 'cw-pinmenu'; [['pad', 'В блокнот'], ['nox', 'В память NOX'], ['board', 'На доску']].forEach(([to, l]) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = l; b.onclick = () => { add(to); mn.remove(); }; mn.appendChild(b); }); const r = p.getBoundingClientRect(); mn.style.cssText = 'left:' + Math.max(8, r.left) + 'px;top:' + (r.bottom + 4) + 'px'; document.body.appendChild(mn); setTimeout(() => document.addEventListener('click', () => mn.remove(), { once: true }), 0); }); acts.appendChild(p); }
        [['.lv-up', '👍', 'Полезно'], ['.lv-dn', '👎', 'Не то']].forEach(([sel, ic, tt]) => { const o = m.querySelector(sel) || (m.querySelector('.lv-chips') || document).querySelector(sel); const k = 'cw-fb' + sel.slice(3); if (o && !acts.querySelector('.' + k)) { const b = document.createElement('button'); b.type = 'button'; b.className = k; b.title = tt; b.setAttribute('aria-label', tt); b.textContent = ic; b.addEventListener('click', () => o.click()); acts.appendChild(b); } });
        const rem = m.querySelector('.lv-rem'); if (rem && !acts.querySelector('.cw-rem')) { const b = document.createElement('button'); b.type = 'button'; b.className = 'cw-rem'; b.title = 'Запомнить'; b.setAttribute('aria-label', 'Запомнить'); b.textContent = '🔖'; b.addEventListener('click', () => rem.click()); acts.appendChild(b); }
      });
      const chips = bar.querySelector('.cw-chips'); const last = $$('#feed .m.a').pop(); const inp = $('#input'); const empty = !inp || !(inp.value || '').trim();
      const src = last ? $$('.lv-chips sl-button:not(.lv-rem):not(.lv-up):not(.lv-dn):not([class*=lv-up]):not([class*=lv-dn])', last).slice(0, 2) : [];
      const key = src.map((s) => s.textContent.trim()).join('|') + (empty ? '1' : '0');
      if (chips.dataset.k === key) return; chips.dataset.k = key; chips.innerHTML = '';
      if (!empty) return;
      src.forEach((s) => { const b = document.createElement('sl-button'); b.size = 'small'; b.pill = true; b.className = 'cw-chip'; b.textContent = s.textContent.trim(); b.addEventListener('click', () => s.click()); chips.appendChild(b); });
    }
    setInterval(decorate, 700); new MutationObserver(() => { clearTimeout(decorate.t); decorate.t = setTimeout(decorate, 120); }).observe($('#feed') || document.body, { childList: true, subtree: true });
    const i = $('#input'); i && i.addEventListener('input', decorate);
    /* приветствие и 4 подсказки при пустом чате */
    const hello = document.createElement('div'); hello.className = 'cw-hello'; hello.innerHTML = '<h2>Чем помочь?</h2><p>Спросите что угодно или выберите подсказку. Команды: «/» или ⌘K.</p><div class="cw-h4"></div>';
    ['Что ты помнишь обо мне?', 'Объясни простыми словами…', 'Помоги написать текст', 'Что нового сегодня?'].forEach((q) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = q; b.addEventListener('click', () => { const i = $('#input'); if (i) { i.value = q; i.dispatchEvent(new Event('input', { bubbles: true })); i.focus(); } }); $('.cw-h4', hello).appendChild(b); });
    const feed = $('#feed'); feed && feed.parentElement.insertBefore(hello, feed);
    setInterval(() => { hello.classList.toggle('on', !$('#feed .m')); }, 600);
    /* связанные вопросы (k7) - в колонку чтения, под последним ответом, а не отдельной строкой сетки над лентой */
    setInterval(() => { const rel = $('#k7-rel'); const col = $('#feed .col'); if (rel && col && rel.parentElement !== col) col.appendChild(rel); }, 1000);
    /* баннер «NOX пишет первым» — карточкой внутри ленты */
    setInterval(() => { const nf = $('.nox-first'); const f = $('#feed'); if (nf && f && nf.parentElement !== f) f.insertBefore(nf, f.firstChild); }, 1500);
  }
})();
