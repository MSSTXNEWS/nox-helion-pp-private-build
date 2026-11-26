/* chat-dc 1920: пустой центр до первого сообщения -> инициативы дня, быстрые команды, последние диалоги. Откат ?fill=0 */
(function () {
  'use strict';
  if (/[?&](fill|mini)=/.test(location.search) && !/fill=1/.test(location.search)) return;
  var dc = document.querySelector('deep-chat'), main = document.querySelector('.dc-main'); if (!dc || !main) return;
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  var css = document.createElement('style');
  css.textContent = '#dcFill{display:none}@media(min-width:1200px){body:not(.dc-mini) .dc-main{position:relative}body:not(.dc-mini) #dcFill{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;position:absolute;left:0;right:0;top:36%;max-width:960px;margin:0 auto;padding:0 16px;z-index:1;transition:opacity .35s,transform .35s}body.dc-started #dcFill{opacity:0;transform:translateY(8px);pointer-events:none}#dcFill sl-card{--border-color:rgba(255,255,255,.1);--border-radius:16px;--padding:14px}#dcFill sl-card::part(base){background:rgba(255,255,255,.055);backdrop-filter:blur(16px) saturate(1.3);-webkit-backdrop-filter:blur(16px) saturate(1.3)}#dcFill h3{margin:0 0 8px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;opacity:.65;font-weight:600}#dcFill button{display:flex;align-items:center;gap:8px;width:100%;min-height:44px;margin:0 0 6px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:inherit;font:inherit;text-align:left;cursor:pointer}#dcFill button:hover{background:rgba(255,255,255,.12)}#dcFill small{opacity:.6;display:block}}';
  document.head.appendChild(css);
  var box = el('div'); box.id = 'dcFill'; main.appendChild(box);
  function card(h) { var c = document.createElement('sl-card'); c.appendChild(el('h3', '', h)); box.appendChild(c); return c; }
  var ini = card('Инициативы дня'), cmd = card('Быстрые команды'), rec = card('Последние диалоги');
  function btn(c, t, sub, fn) { var b = el('button'); b.type = 'button'; b.appendChild(document.createTextNode(t)); if (sub) b.appendChild(el('small', '', sub)); b.onclick = fn; c.appendChild(b); }
  [['Новый диалог', function () { var n = document.getElementById('dcNew'); n && n.click(); }], ['Нарисовать картинку', function () { window.NOXdcSetInput ? NOXdcSetInput('Нарисуй ') : 0; }], ['План дня', function () { dc.submitUserMessage('Составь план на сегодня'); }], ['Идеи', function () { dc.submitUserMessage('Предложи идеи, чем заняться сегодня'); }], ['Блокнот', function () { window.NOXNote && NOXNote.toggle(); }]].forEach(function (x) { btn(cmd, x[0], '', x[1]); });
  function fillRec() {
    [].slice.call(rec.querySelectorAll('button')).forEach(function (b) { b.remove(); });
    var ts = []; try { ts = window.NOXdc.threads().filter(function (t) { return t.msgs && t.msgs.length; }).slice(0, 4); } catch (e) {}
    if (!ts.length) { btn(rec, 'Пока нет диалогов', '', function () {}); return; }
    ts.forEach(function (t) { btn(rec, (t.title || 'Диалог').slice(0, 36), t.msgs.length + ' сообщ.', function () { var it = document.querySelector('#dcL sl-tree-item[data-id="' + t.id + '"]'); it && it.click(); }); });
  }
  fetch('/api/nox/agenda', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
    var a = (j && !j.hold && j.ideas || []).filter(function (i) { return i && i.title && !/done|closed|reject|dismiss/i.test(String(i.status || '')); }).slice(0, 3);
    if (!a.length) { btn(ini, 'Нет данных (HOLD)', 'повестка пуста или недоступна', function () {}); return; }
    a.forEach(function (i) { btn(ini, String(i.title).slice(0, 48), i.why ? String(i.why).slice(0, 70) : '', function () { dc.submitUserMessage('Давай обсудим инициативу: ' + i.title); }); });
  }).catch(function () { btn(ini, 'Нет данных (HOLD)', 'мост недоступен', function () {}); });
  setTimeout(fillRec, 1500); setInterval(fillRec, 20000);
  var of = window.fetch; window.fetch = function (u) { try { var url = typeof u === 'string' ? u : (u && u.url) || ''; if (url.indexOf('/api/turn') >= 0 && url.indexOf('/stop') < 0) document.body.classList.add('dc-started'); } catch (e) {} return of.apply(this, arguments); };
  setInterval(function () { try { var t = window.NOXdc.cur(); document.body.classList.toggle('dc-started', !!(t && t.msgs && t.msgs.length)); } catch (e) {} }, 1200);
})();
