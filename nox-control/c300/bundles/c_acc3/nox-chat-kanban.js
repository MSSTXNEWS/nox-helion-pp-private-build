/* C: канбан задач в колонке 5 чата. Источник: GET /svc/nox-a2/board -> {колонка:[{id,title,stage,blocker,doing,pct,eta_sec,idle_sec}]}; карточка: GET /svc/nox-a2/task/{id}/card. Только чтение. */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const EP = '/svc/nox-a2'; let box, dlg, timer, dead = 0;
  function init() {
    const right = $('.cx-right'); if (!right || $('.cxk')) return false;
    box = document.createElement('section'); box.className = 'cxk cx5-w'; box.setAttribute('aria-label', 'Задачи');
    box.innerHTML = '<header class="cx5-h"><b>ЗАДАЧИ</b><span class="cxk-n" id="cxkN"></span></header><div class="cxk-b" id="cxkB"><div class="cxk-e">загрузка…</div></div>';
    right.appendChild(box);
    dlg = document.createElement('sl-dialog'); dlg.label = 'Карточка задачи'; dlg.className = 'cxk-d'; document.body.appendChild(dlg);
    box.addEventListener('click', (e) => { const c = e.target.closest('[data-tid]'); if (c) open(c.dataset.tid); });
    box.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.dataset && e.target.dataset.tid) { e.preventDefault(); open(e.target.dataset.tid); } });
    load(); timer = setInterval(() => { if (!document.hidden) load(); }, 10000); return true;
  }
  async function load() {
    if (dead && Date.now() - dead < 60000) return;
    try {
      const r = await fetch(EP + '/board', { cache: 'no-store' }); if (!r.ok) throw 0; const d = await r.json(); let n = 0;
      const html = Object.keys(d).map((col) => { const L = Array.isArray(d[col]) ? d[col] : []; n += L.length; if (!L.length) return '';
        return '<div class="cxk-c"><div class="cxk-ch">' + esc(col) + ' <span>' + L.length + '</span></div>' + L.slice(0, 6).map((t) => '<div class="cxk-t" tabindex="0" role="button" data-tid="' + esc(t.id) + '" title="' + esc(t.doing || t.blocker || '') + '"><b>' + esc(t.title || t.id) + '</b><small>' + esc(t.stage || '') + (t.blocker ? ' · ' + esc(String(t.blocker).slice(0, 40)) : '') + '</small><sl-progress-bar value="' + (+t.pct || 0) + '" style="--height:4px"></sl-progress-bar></div>').join('') + '</div>'; }).join('');
      $('#cxkB').innerHTML = html || '<div class="cxk-e">задач нет</div>'; $('#cxkN').textContent = n ? String(n) : '';
    } catch (e) { dead = Date.now(); $('#cxkB').innerHTML = '<div class="cxk-e">доска недоступна</div>'; }
  }
  async function open(id) {
    dlg.label = 'Задача ' + id; dlg.innerHTML = 'загрузка…'; dlg.show();
    try { const c = await fetch(EP + '/task/' + encodeURIComponent(id) + '/card', { cache: 'no-store' }).then((r) => r.json());
      dlg.innerHTML = '<dl class="cxk-dl">' + Object.keys(c).slice(0, 24).map((k) => '<dt>' + esc(k) + '</dt><dd>' + esc(typeof c[k] === 'object' ? JSON.stringify(c[k]) : c[k]).slice(0, 600) + '</dd>').join('') + '</dl>';
    } catch (e) { dlg.textContent = 'карточка недоступна'; }
  }
  const t = setInterval(() => { if (init()) clearInterval(t); }, 600);
})();
