/* chat-dc: карточки-инициативы из повестки (:8810 /worms/agenda через мост). Откат ?agenda=0 */
(function () {
  'use strict';
  if (/[?&]agenda=0/.test(location.search)) return;
  var dc = document.querySelector('deep-chat'); if (!dc) return;
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  var DONE = /done|closed|reject|dismiss|выполн|закрыт|отклон|archiv/i;
  function run() {
    if (!dc.addMessage) return setTimeout(run, 1200);
    var now = new Date(); if (now.getHours() * 60 + now.getMinutes() < 480) return;
    fetch('/api/nox/agenda', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j || j.hold || !Array.isArray(j.ideas)) return;
      var day = now.toISOString().slice(0, 10), seen = {}; try { seen = JSON.parse(localStorage.getItem('nox.agenda.seen') || '{}'); } catch (e) {}
      var fresh = j.ideas.filter(function (i) { return i && i.title && !DONE.test(String(i.status || '')) && (!i.day || String(i.day).slice(0, 10) === day) && !seen[i.id || i.title]; }).slice(0, 3);
      if (!fresh.length) return;
      fresh.forEach(function (i) { seen[i.id || i.title] = 1; });
      try { localStorage.setItem('nox.agenda.seen', JSON.stringify(seen)); } catch (e) {}
      var h = '<div style="display:grid;gap:8px;max-width:520px"><b>Инициативы на сегодня</b>' + fresh.map(function (i) {
        var acts = (Array.isArray(i.actions) ? i.actions : []).slice(0, 3).map(function (a) { return '<span style="padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.1);font-size:12px">' + esc(a && (a.label || a.title || a.name) || a) + '</span>'; }).join(' ');
        return '<div style="padding:12px;border-radius:14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12)"><div style="font-weight:600">' + esc(i.title) + '</div>' + (i.why ? '<div style="opacity:.75;font-size:13px;margin-top:4px">' + esc(String(i.why).slice(0, 220)) + '</div>' : '') + '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">' + acts + '<button type="button" data-nxag="' + esc(i.title) + '" style="min-height:44px;padding:8px 14px;border-radius:12px;border:1px solid rgba(160,190,255,.6);background:rgba(120,160,255,.22);color:inherit;cursor:pointer">Обсудить</button></div></div>';
      }).join('') + '</div>';
      dc.addMessage({ role: 'ai', html: h });
      setTimeout(function () { var sr = dc.shadowRoot; if (!sr) return; sr.addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('[data-nxag]'); if (b) dc.submitUserMessage('Давай обсудим инициативу: ' + b.getAttribute('data-nxag')); }); }, 400);
    }).catch(function () {});
  }
  addEventListener('load', function () { setTimeout(run, 3000); });
})();
