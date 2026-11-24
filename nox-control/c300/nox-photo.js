/* NOX · Фотостудия: miniPaint (iframe, тот же origin) + ИИ: генерация на сервере (/img), удаление фона и ×2 в браузере (ESM с CDN), описание (/vision). */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var frame = $('#mp');
  function W() { return frame.contentWindow; }
  function busy(btn, on) { if (btn) btn.disabled = on; }
  function say(id, t) { $(id).textContent = t; }

  /* --- мост к miniPaint --- */
  function canvasOut() {
    var w = W(); if (!w) throw new Error('редактор не загружен');
    var L = w.Layers, cfg = w.config || w.AppConfig || {};
    if (L && L.convert_layers_to_canvas && cfg.WIDTH) {
      var c = document.createElement('canvas'); c.width = cfg.WIDTH; c.height = cfg.HEIGHT;
      L.convert_layers_to_canvas(c.getContext('2d'), null, false); return c;
    }
    var v = w.document.querySelector('#canvas_minipaint, canvas'); if (!v) throw new Error('холст не найден'); return v;
  }
  function toBlob(c, type, q) { return new Promise(function (ok) { c.toBlob(ok, type || 'image/png', q || 0.92); }); }
  function insertImage(src, name) {
    return new Promise(function (ok, no) {
      var img = new Image(); img.crossOrigin = 'anonymous';
      img.onload = function () {
        var w = W(), L = w && w.Layers;
        if (!L || !L.insert) return no(new Error('API слоёв miniPaint недоступно'));
        var cfg = w.config || {};
        try { if (cfg.WIDTH !== undefined && (img.width > cfg.WIDTH || img.height > cfg.HEIGHT)) { cfg.WIDTH = Math.max(cfg.WIDTH, img.width); cfg.HEIGHT = Math.max(cfg.HEIGHT, img.height); w.Layers.render && w.Layers.render(); } } catch (e) {}
        L.insert({ name: name || 'NOX', type: 'image', data: img, width: img.naturalWidth, height: img.naturalHeight, width_original: img.naturalWidth, height_original: img.naturalHeight });
        ok();
      };
      img.onerror = function () { no(new Error('картинка не загрузилась')); };
      img.src = src;
    });
  }
  function dl(c, type, ext) { toBlob(c, type, 0.92).then(function (b) { var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'nox-photo.' + ext; a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 1500); }); }
  $('#expP').onclick = function () { dl(canvasOut(), 'image/png', 'png'); };
  $('#expJ').onclick = function () { dl(canvasOut(), 'image/jpeg', 'jpg'); };
  $('#expW').onclick = function () { dl(canvasOut(), 'image/webp', 'webp'); };
  $('#openF').onclick = function () { var i = document.createElement('input'); i.type = 'file'; i.accept = 'image/*'; i.onchange = function () { if (i.files[0]) insertImage(URL.createObjectURL(i.files[0]), i.files[0].name).catch(function (e) { alert(e.message); }); }; i.click(); };

  /* --- NOX (текст) --- */
  function askNox(prompt) {
    $('#noxBox').hidden = false; var out = $('#noxOut'), acc = ''; out.textContent = '…';
    return fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: 'fast', messages: [{ role: 'user', content: prompt }] }) }).then(function (r) {
      var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
      function pump() { return rd.read().then(function (x) { if (x.done) return acc; buf += dec.decode(x.value, { stream: true }); var k; while ((k = buf.indexOf('\n')) >= 0) { var l = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!l) continue; try { var d = JSON.parse(l); if (d.message && d.message.content) { acc += d.message.content; out.textContent = acc; } } catch (e) {} } return pump(); }); }
      return pump();
    }).catch(function (e) { out.textContent = 'NOX не ответил: ' + e.message; return ''; });
  }

  /* --- генерация на сервере --- */
  var thumbs = [];
  $('#gImp').onclick = function () { var p = $('#gP').value.trim(); if (!p) return; askNox('Сделай из описания сильный промпт для генерации изображения на английском: объект, стиль, свет, композиция, камера. Верни только промпт одной строкой.\n\n' + p).then(function (a) { if (a) $('#gP').value = a.replace(/^["«]|["»]$/g, '').trim(); }); };
  $('#gGo').onclick = function () {
    var p = $('#gP').value.trim(); if (!p) return; var sz = $('#gS').value.split('x'), b = $('#gGo'); busy(b, true); say('#gSt', 'Генерирую на сервере… (обычно 10–60 с)');
    fetch('/img/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: p, model: $('#gM').value, width: +sz[0], height: +sz[1], seed: -1 }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || j.reason || ('HTTP ' + r.status)); return j; }); })
      .then(function (j) { var url = '/img/file?p=' + encodeURIComponent(j.path); say('#gSt', 'Готово за ' + (j.seconds || '?') + ' с'); thumbs.unshift(url); drawThumbs(); return insertImage(url, 'NOX: ' + p.slice(0, 30)); })
      .catch(function (e) { say('#gSt', 'Не вышло: ' + e.message + (/503/.test(e.message) ? '\n(видеокарта занята — попробуй через минуту)' : '')); })
      .then(function () { busy(b, false); });
  };
  function drawThumbs() { var t = $('#gTh'); t.innerHTML = ''; thumbs.slice(0, 9).forEach(function (u) { var i = new Image(); i.src = u; i.title = 'Вставить слоем'; i.onclick = function () { insertImage(u, 'NOX'); }; t.appendChild(i); }); }

  /* --- ИИ в браузере --- */
  $('#aBg').onclick = function () {
    var b = this; busy(b, true); say('#aSt', 'Загружаю модель удаления фона (первый раз ~40 МБ)…');
    toBlob(canvasOut()).then(function (blob) { return import('https://esm.sh/@imgly/background-removal@1.5.5').then(function (m) { say('#aSt', 'Удаляю фон…'); return m.removeBackground(blob, { progress: function (k, c, t) { say('#aSt', 'Модель: ' + Math.round(100 * c / (t || 1)) + '%'); } }); }); })
      .then(function (out) { say('#aSt', 'Фон удалён — новый слой.'); return insertImage(URL.createObjectURL(out), 'Без фона'); })
      .catch(function (e) { say('#aSt', 'Ошибка: ' + e.message); }).then(function () { busy(b, false); });
  };
  $('#aUp2').onclick = function () {
    var b = this; busy(b, true); say('#aSt', 'Загружаю модель увеличения (ESRGAN)…');
    var c = canvasOut();
    Promise.all([import('https://esm.sh/upscaler@1.0.0-beta.19'), import('https://esm.sh/@upscalerjs/esrgan-slim@1.0.0-beta.12/2x')])
      .then(function (m) { var U = m[0].default, model = m[1].default; var up = new U({ model: model }); say('#aSt', 'Увеличиваю ×2 (браузер, может занять минуту)…'); return up.upscale(c.toDataURL('image/png'), { patchSize: 64, padding: 4, progress: function (p) { say('#aSt', 'Увеличение: ' + Math.round(p * 100) + '%'); } }); })
      .then(function (src) { say('#aSt', 'Готово — новый слой ×2.'); return insertImage(src, 'Увеличено ×2'); })
      .catch(function (e) { say('#aSt', 'Ошибка: ' + e.message); }).then(function () { busy(b, false); });
  };
  function small(c, max) { var k = Math.min(1, max / Math.max(c.width, c.height)); var s = document.createElement('canvas'); s.width = Math.round(c.width * k); s.height = Math.round(c.height * k); s.getContext('2d').drawImage(c, 0, 0, s.width, s.height); return s.toDataURL('image/jpeg', 0.85); }
  function vision(q) {
    $('#noxBox').hidden = false; $('#noxOut').textContent = 'NOX смотрит на фото…';
    return fetch('/vision/describe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: small(canvasOut(), 768), prompt: q }) })
      .then(function (r) { return r.json(); }).then(function (j) { $('#noxOut').textContent = j.text || ('Ошибка: ' + (j.error || 'нет ответа')); })
      .catch(function (e) { $('#noxOut').textContent = 'Ошибка: ' + e.message; });
  }
  $('#aDesc').onclick = function () { vision('Опиши это изображение по-русски: что на нём, композиция, свет, настроение. 3–5 предложений.'); };
  $('#aIdea').onclick = function () { vision('Ты фоторедактор. Предложи 5 конкретных правок этого изображения по-русски (кадрирование, свет, цвет, ретушь, стиль), коротко по пунктам.'); };

  /* --- фильтры копией --- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-f]'), function (b) {
    b.onclick = function () { var src = canvasOut(), c = document.createElement('canvas'); c.width = src.width; c.height = src.height; var x = c.getContext('2d'); x.filter = b.getAttribute('data-f'); x.drawImage(src, 0, 0); insertImage(c.toDataURL('image/png'), b.textContent).catch(function (e) { alert(e.message); }); };
  });
})();
