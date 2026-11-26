/* Обучение через мост /api/nox/training/status: только реальные поля, нет данных -> HOLD. Откат ?tb=0 */
(function () {
  'use strict';
  if (/[?&]tb=0/.test(location.search)) return;
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function mount() {
    var host = document.getElementById('page') || document.getElementById('app') || document.body;
    var c = document.createElement('sl-card'); c.id = 'nxTB'; c.style.cssText = 'display:block;margin:12px 0';
    c.appendChild(el('h2', '', 'Обучение: сейчас')); var b = el('div', '', 'загрузка…'); b.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px'; c.appendChild(b);
    host.insertBefore(c, host.firstChild);
    function tile(k, v) { var t = el('div'); t.style.cssText = 'padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.06);min-height:44px'; var s = el('small', '', k); s.style.opacity = '.7'; var x = el('div', '', String(v)); x.style.fontWeight = '600'; t.appendChild(s); t.appendChild(x); return t; }
    function upd() {
      fetch('/api/nox/training/status', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
        b.textContent = '';
        if (!j || j.hold) { b.textContent = 'нет данных (HOLD): ' + ((j && j.hold_reason) || 'мост недоступен'); return; }
        var L = [['Вердикт', j.verdict], ['Раунд', j.round], ['Шаг', j.step], ['Строк в данных', j.rows_total], ['Новых строк', j.new_rows], ['Чекпойнтов', j.checkpoint_count], ['Принято', j.accepted], ['Возраст квитанции, мин', j.receipt_age_seconds != null ? Math.round(j.receipt_age_seconds / 60) : null], ['Раунд, мин', j.total_min != null ? Math.round(j.total_min) : null]];
        var n = 0; L.forEach(function (x) { if (x[1] != null && x[1] !== '') { b.appendChild(tile(x[0], typeof x[1] === 'object' ? JSON.stringify(x[1]).slice(0, 40) : x[1])); n++; } });
        if (j.note) { var nt = el('div', '', String(j.note).slice(0, 200)); nt.style.cssText = 'grid-column:1/-1;opacity:.8;font-size:13px'; b.appendChild(nt); }
        if (!n) b.textContent = 'нет данных (HOLD)';
      }).catch(function () { b.textContent = 'нет данных (HOLD): мост недоступен'; });
    }
    upd(); setInterval(upd, 30000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(mount, 1200); }); else setTimeout(mount, 1200);
})();
