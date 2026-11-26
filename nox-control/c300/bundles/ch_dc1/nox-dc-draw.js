/* NOX · рисование из чата (chat-dc): «нарисуй …» -> /img/generate (тот же сервис, что в Фотостудии) -> карточка в ленте:
   превью, подпись, действия «Скачать», «Вариации», «В фото-редактор». Тонкая обёртка над dc.connect.handler. Откат: ?draw=0 */
(function () {
  'use strict';
  if (/[?&]draw=0/.test(location.search)) return;
  var dc = document.querySelector('deep-chat'); if (!dc) return;
  var RX = /^\s*(?:\/(?:img|draw|рис\w*)\s+|(?:нарисуй(?:те)?|изобрази(?:те)?|сгенерируй(?:те)?\s+(?:картинку|изображение|рисунок|фото)|создай(?:те)?\s+(?:картинку|изображение|рисунок))\s*[:,—-]?\s*)(.+)$/is;
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  function improve(p) {
    var acc = '';
    return fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: 'fast', messages: [{ role: 'user', content: 'Сделай из описания сильный промпт для генерации изображения на английском: объект, стиль, свет, композиция, камера. Верни только промпт одной строкой.\n\n' + p }] }) })
      .then(function (r) { var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
        function pump() { return rd.read().then(function (x) { if (x.done) return acc; buf += dec.decode(x.value, { stream: true }); var k; while ((k = buf.indexOf('\n')) >= 0) { var l = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!l) continue; try { var d = JSON.parse(l); var t = d.text || (d.message && d.message.content); if (t) acc += t; } catch (e) {} } return pump(); }); }
        return pump(); })
      .then(function (a) { a = (a || '').replace(/^["«\s]+|["»\s]+$/g, '').split('\n')[0].trim(); return a.length > 15 && a.length < 600 && (a.replace(/[^\x00-\x7F]/g, '').length / a.length) > 0.9 ? a : p; })
      .catch(function () { return p; });
  }
  function gen(p, size) {
    var sz = size.split('x');
    return fetch('/img/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: p, model: 'chroma', width: +sz[0], height: +sz[1], seed: -1 }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok || !j.path) throw new Error(j.error || j.reason || ('HTTP ' + r.status)); return j; }); });
  }
  var BS = 'min-height:44px;padding:0 14px;border-radius:10px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.06);color:inherit;font:inherit;font-size:14px;cursor:pointer;';
  function card(url, prompt, shown, sec, size) {
    return '<div class="nxg" style="max-width:min(100%,520px)">' +
      '<a href="' + esc(url) + '" target="_blank" rel="noopener" aria-label="Открыть картинку целиком"><img src="' + esc(url) + '" alt="' + esc(shown) + '" loading="lazy" style="display:block;max-width:100%;max-height:52vh;width:auto;height:auto;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04)"></a>' +
      '<div style="margin:8px 2px 10px;font-size:13px;opacity:.72;line-height:1.4">' + esc(shown.slice(0, 160)) + ' · ' + esc(size) + (sec ? ' · ' + esc(sec) + ' с' : '') + '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
      '<button type="button" data-nxg="dl" data-url="' + esc(url) + '" style="' + BS + '">Скачать</button>' +
      '<button type="button" data-nxg="var" data-p="' + esc(prompt) + '" style="' + BS + '">Вариации</button>' +
      '<button type="button" data-nxg="ed" data-url="' + esc(url) + '" style="' + BS + '">В фото-редактор</button></div></div>';
  }
  window.NOXdcDraw = function (body, signals) {
    var msgs = body && body.messages || [], last = msgs[msgs.length - 1], text = last && (last.text || last.content) || '';
    var m = RX.exec(text); if (!m || (body && body.files && body.files.length)) return false;
    var prompt = m[1].trim(), T = window.NOXdc && NOXdc.cur && NOXdc.cur();
    if (T) { T.msgs.push({ role: 'user', content: text, ts: Date.now() }); if (T.title === 'Новый диалог') T.title = text.replace(/\s+/g, ' ').slice(0, 44); }
    signals.onOpen();
    improve(prompt).then(function (en) { return gen(en, '1024x1024').then(function (j) { return { j: j, en: en }; }); })
      .then(function (r) {
        var url = '/img/file?p=' + encodeURIComponent(r.j.path);
        signals.onResponse({ html: card(url, prompt, prompt, r.j.seconds ? Math.round(r.j.seconds) : '', '1024×1024') });
        [120, 600, 1600].forEach(function (t) { setTimeout(down, t); });
        if (T) { T.msgs.push({ role: 'assistant', content: '![' + prompt.replace(/[\[\]\n]/g, ' ') + '](' + url + ')\n\n' + prompt, ts: Date.now() }); NOXdc.save(); }
      })
      .catch(function (e) {
        var msg = /disabled|отключ/i.test(String(e.message)) ? 'Генерация картинок сейчас отключена (GPU занят обучением). Попробуйте позже.' : /503|занят/.test(String(e.message)) ? 'Видеокарта занята — попробуйте через минуту.' : 'Не получилось нарисовать: ' + e.message;
        signals.onResponse({ text: msg }); if (T) { T.msgs.push({ role: 'assistant', content: msg, ts: Date.now() }); NOXdc.save(); }
      })
      .then(function () { signals.onClose(); });
    return true;
  };
  function down() { var r = dc.shadowRoot, m = r && r.querySelector('#messages'); if (m) m.scrollTop = m.scrollHeight; var l = r && r.querySelectorAll('.nxg img'); if (l && l.length && !l[l.length - 1].complete) l[l.length - 1].addEventListener('load', down, { once: true }); }
  function bind() {
    var r = dc.shadowRoot; if (!r) return setTimeout(bind, 400);
    r.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-nxg]'); if (!b) return;
      var a = b.getAttribute('data-nxg'), u = b.getAttribute('data-url');
      if (a === 'dl') { var l = document.createElement('a'); l.href = u; l.download = 'nox-' + Date.now() + '.png'; document.body.appendChild(l); l.click(); l.remove(); }
      else if (a === 'var') { window.NOXdc && NOXdc.submit('нарисуй ' + b.getAttribute('data-p')); }
      else if (a === 'ed') { try { sessionStorage.setItem('nox.photo.open', u); } catch (x) {} location.href = 'photo.html'; }
    });
  }
  bind();
})();
