/* NOX chat-dc live: Я сейчас (state/core/self_now.json), брифы 08:00/22:30, филлеры. Откат ?live=0 */
(function () {
  'use strict';
  if (/[?&]live=0/.test(location.search)) return;
  var $ = function (s) { return document.querySelector(s); };
  function el(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function walk(o, f, p) { if (o && typeof o === 'object') Object.keys(o).forEach(function (k) { var v = o[k]; if (typeof v === 'string' || typeof v === 'number') f(p ? p + '.' + k : k, v); else walk(v, f, p ? p + '.' + k : k); }); }
  function pick(d, re) { var r = null; walk(d, function (k, v) { if (r == null && re.test(k.split('.').pop()) && String(v).trim()) r = v; }); return r; }

  /* 1. Я сейчас: только вместе с метрикой-причиной */
  function nowCard() {
    var box = $('#dcW .dc-body') || $('#dcW'); if (!box) return setTimeout(nowCard, 800);
    var c = el('div', 'dc-w'); c.id = 'dcNow'; c.style.cssText = 'display:block;margin:8px 0;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)';
    c.appendChild(el('b', '', 'Я сейчас')); var t = el('div', '', 'загрузка…'); t.style.cssText = 'margin-top:4px;font-size:13px;line-height:1.4'; c.appendChild(t);
    box.insertBefore(c, box.firstChild);
    function upd() {
      fetch('/api/nox/self_now', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
        if (!j || j.hold || !j.data) { t.textContent = 'нет данных (HOLD)'; return; }
        var d = j.data, feel = d.text || pick(d, /^(feel|feeling|sense|summary)/i), tl = d.telemetry || {}, why = [];
        if (tl.gpu_temp != null) why.push('GPU ' + Math.round(tl.gpu_temp) + '°C');
        if (tl.vram_pct != null) why.push('видеопамять ' + Math.round(tl.vram_pct) + '%');
        if (tl.ram_used_pct != null) why.push('ОЗУ ' + Math.round(tl.ram_used_pct) + '%');
        if (tl.silence_h != null) why.push('тишина ' + (Math.round(tl.silence_h * 10) / 10) + ' ч');
        if (tl.train_running != null) why.push(tl.train_running ? 'идёт обучение' : 'обучение не идёт');
        why = why.join(', ');
        if (!feel) { t.textContent = 'нет данных (HOLD)'; return; }
        if (!why) { t.textContent = 'ощущение без метрики-причины не показываю (HOLD)'; return; }
        t.textContent = ''; t.appendChild(el('div', '', String(feel).slice(0, 220)));
        var m = el('small', '', 'причина: ' + String(why).slice(0, 160)); m.style.opacity = '.7'; t.appendChild(m);
      }).catch(function () { t.textContent = 'нет данных (HOLD)'; });
    }
    upd(); setInterval(upd, 60000);
  }

  /* 2. Брифы: NOX пишет первым */
  function briefText(d) { if (d && Array.isArray(d.lines) && d.lines.length) return d.lines.map(function (x) { return typeof x === 'string' ? '• ' + x : '• ' + (x.text || x.title || JSON.stringify(x)); }).join('\n'); var t = pick(d, /^(text|brief|message|summary|body|content|markdown|reply)$/i); if (t) return String(t); var a = []; walk(d, function (k, v) { if (typeof v === 'string' && v.length > 20 && a.length < 6) a.push(v); }); return a.join('\n\n'); }
  function toast(msg) { var a = document.createElement('sl-alert'); a.variant = 'primary'; a.closable = true; a.duration = 7000; a.innerHTML = '<sl-icon slot="icon" name="chat-dots"></sl-icon><strong>NOX пишет первым</strong><br>' + msg; if (a.toast) a.toast(); else document.body.appendChild(a); }
  function briefs() {
    var dc = $('deep-chat'); if (!dc || !dc.addMessage) return setTimeout(briefs, 1000);
    fetch('/api/nox/briefs', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
      var now = new Date(), mins = now.getHours() * 60 + now.getMinutes(), day = now.toDateString();
      [['morning', 'Утренний бриф', 480], ['evening', 'Вечерний бриф', 22 * 60 + 30]].forEach(function (x) {
        var b = j && j[x[0]]; if (!b || b.hold || !b.data || mins < x[2]) return;
        if (new Date(b.mtime * 1000).toDateString() !== day) return;
        var key = 'nox.brief.' + x[0] + '.' + b.mtime; try { if (localStorage.getItem(key)) return; localStorage.setItem(key, '1'); } catch (e) {}
        var tx = briefText(b.data); if (!tx) return;
        dc.addMessage({ role: 'ai', text: '**' + x[1] + '**\n\n' + tx }); toast(x[1] + ' готов');
      });
    }).catch(function () {});
  }

  /* 3. Филлеры: ждём первый токен > 1,2 с, не в историю */
  var FILL = ['угу…', 'секунду…', 'так…', 'сейчас гляну…'], fi = 0;
  var bar = el('div'); bar.setAttribute('aria-live', 'polite'); bar.style.cssText = 'position:fixed;left:50%;top:76px;transform:translateX(-50%);padding:6px 14px;border-radius:999px;background:rgba(20,24,34,.78);backdrop-filter:blur(10px);color:#fff;font-size:13px;opacity:0;pointer-events:none;transition:opacity .25s;z-index:50';
  function hide() { bar.style.opacity = '0'; }
  var of = window.fetch;
  window.fetch = function (u, o) {
    var p = of.apply(this, arguments), url = typeof u === 'string' ? u : (u && u.url) || '';
    if (url.indexOf('/api/turn') < 0 || url.indexOf('/stop') >= 0) return p;
    var done = false, tm = setTimeout(function () { if (done) return; if (!bar.parentNode) document.body.appendChild(bar); bar.textContent = FILL[fi++ % FILL.length]; bar.style.opacity = '1'; }, 1200);
    function fin() { done = true; clearTimeout(tm); hide(); }
    p.then(function (r) {
      if (!r.body || !r.clone) return fin();
      var rd = r.clone().body.getReader(), dec = new TextDecoder();
      (function pump() { rd.read().then(function (x) { if (x.done) return fin(); if (/"t"\s*:\s*"(delta|error|done)"/.test(dec.decode(x.value, { stream: true }))) { fin(); try { rd.cancel(); } catch (e) {} return; } pump(); }).catch(fin); })();
    }).catch(fin);
    return p;
  };

  function start() { nowCard(); briefs(); }
  if (document.readyState === 'complete') setTimeout(start, 1500); else addEventListener('load', function () { setTimeout(start, 1500); });
})();
