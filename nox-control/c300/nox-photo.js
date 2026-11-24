/* NOX · Фотостудия: miniPaint (iframe, тот же origin) + ИИ: генерация на сервере (/img), удаление фона и ×2 в браузере (ESM с CDN), описание (/vision). */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  function busy(btn, on) { if (btn) btn.disabled = on; }
  function say(id, t) { $(id).textContent = t; }

  /* --- мост к Filerobot Image Editor (готовый профессиональный редактор) --- */
  var FIE = window.FilerobotImageEditor, fie = null, curSrc = null;
  function blank() { var c = document.createElement('canvas'); c.width = 1024; c.height = 640; var x = c.getContext('2d'); var g = x.createLinearGradient(0, 0, 1024, 640); g.addColorStop(0, '#0a1124'); g.addColorStop(1, '#1b0d1f'); x.fillStyle = g; x.fillRect(0, 0, 1024, 640); x.fillStyle = 'rgba(124,200,255,.85)'; x.font = '600 44px system-ui'; x.textAlign = 'center'; x.fillText('NOX · Фотостудия', 512, 300); x.font = '22px system-ui'; x.fillStyle = 'rgba(230,240,255,.6)'; x.fillText('Открой фото или попроси NOX нарисовать', 512, 350); return c.toDataURL('image/png'); }
  function mount(src) {
    curSrc = src; var box = $('#fie'); if (fie) { try { fie.terminate(); } catch (e) {} } box.innerHTML = '';
    var T = FIE.TABS, O = FIE.TOOLS;
    fie = new FIE(box, { source: src, language: 'ru', defaultSavedImageType: 'png', closeAfterSave: false, savingPixelRatio: 1, previewPixelRatio: window.devicePixelRatio || 1,
      tabsIds: [T.ADJUST, T.FINETUNE, T.FILTERS, T.ANNOTATE, T.WATERMARK, T.RESIZE], defaultTabId: T.ADJUST, defaultToolId: O.CROP,
      theme: { palette: { 'bg-primary': '#070b16', 'bg-secondary': '#0d1424', 'bg-primary-active': '#13203a', 'accent-primary': '#7cc8ff', 'accent-primary-active': '#a6dcff', 'icons-primary': '#cfe6ff', 'icons-secondary': '#8fb3d9', 'borders-secondary': 'rgba(150,190,255,.22)', 'borders-primary': 'rgba(150,190,255,.32)', 'txt-primary': '#e6f1ff', 'txt-secondary': '#9fb7d3', 'light-shadow': 'rgba(0,0,0,.5)', 'warning': '#ffb36b' }, typography: { fontFamily: 'system-ui, sans-serif' } },
      onSave: function (img) { var a = document.createElement('a'); a.href = img.imageBase64; a.download = (img.fullName || 'nox-photo.png'); a.click(); } });
    fie.render();
  }
  function canvasOut() {
    if (!fie) throw new Error('редактор не загружен');
    var d = fie.getCurrentImgData({}, 1, true); var c = d && d.imageData && d.imageData.imageCanvas;
    if (c) return c; throw new Error('нет изображения');
  }
  function toBlob(c, type, q) { return new Promise(function (ok) { c.toBlob(ok, type || 'image/png', q || 0.92); }); }
  function insertImage(src) { return new Promise(function (ok) { mount(src); setTimeout(ok, 300); }); }
  if (FIE) mount(blank()); else $('#fie').innerHTML = '<p style="padding:20px">Редактор не загрузился.</p>';
  function dl(c, type, ext) { toBlob(c, type, 0.92).then(function (b) { var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'nox-photo.' + ext; a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 1500); }); }
  $('#expP').onclick = function () { dl(canvasOut(), 'image/png', 'png'); };
  $('#expJ').onclick = function () { dl(canvasOut(), 'image/jpeg', 'jpg'); };
  $('#expW').onclick = function () { dl(canvasOut(), 'image/webp', 'webp'); };
  $('#openF').onclick = function () { var i = document.createElement('input'); i.type = 'file'; i.accept = 'image/*'; i.onchange = function () { if (i.files[0]) { var r = new FileReader(); r.onload = function () { mount(r.result); }; r.readAsDataURL(i.files[0]); } }; i.click(); };

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
  function generate(p) {
    var sz = $('#gS').value.split('x'), b = $('#gGo'); busy(b, true); say('#gSt', 'Генерирую на сервере… (обычно 20–90 с)');
    return fetch('/img/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: p, model: $('#gM').value, width: +sz[0], height: +sz[1], seed: -1 }) })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || j.reason || ('HTTP ' + r.status)); return j; }); })
      .then(function (j) { var url = '/img/file?p=' + encodeURIComponent(j.path); say('#gSt', 'Готово за ' + (j.seconds || '?') + ' с'); thumbs.unshift(url); drawThumbs(); return insertImage(url, 'NOX: ' + p.slice(0, 30)).then(function () { return url; }); })
      .catch(function (e) { say('#gSt', 'Не вышло: ' + e.message + (/503|занят/.test(e.message) ? '\n(видеокарта занята — попробуй через минуту)' : '')); return null; })
      .then(function (u) { busy(b, false); return u; });
  }
  $('#gGo').onclick = function () { var p = $('#gP').value.trim(); if (p) generate(p); };
  function drawThumbs() { var t = $('#gTh'); t.innerHTML = ''; thumbs.slice(0, 9).forEach(function (u) { var i = new Image(); i.src = u; i.title = 'Вставить слоем'; i.onclick = function () { insertImage(u, 'NOX'); }; t.appendChild(i); }); }

  /* --- ИИ в браузере --- */
  $('#aBg').onclick = function () {
    var b = this; busy(b, true); say('#aSt', 'Загружаю модель удаления фона (первый раз ~40 МБ)…');
    toBlob(canvasOut()).then(function (blob) { return import('https://esm.sh/@imgly/background-removal@1.5.5').then(function (m) { say('#aSt', 'Удаляю фон…'); return m.removeBackground(blob, { progress: function (k, c, t) { say('#aSt', 'Модель: ' + Math.round(100 * c / (t || 1)) + '%'); } }); }); })
      .then(function (out) { say('#aSt', 'Фон удалён — в редакторе.'); return insertImage(URL.createObjectURL(out), 'Без фона'); })
      .catch(function (e) { say('#aSt', 'Ошибка: ' + e.message); }).then(function () { busy(b, false); });
  };
  $('#aUp2').onclick = function () {
    var b = this; busy(b, true); say('#aSt', 'Загружаю модель увеличения (ESRGAN)…');
    var c = canvasOut();
    Promise.all([import('https://esm.sh/upscaler@1.0.0-beta.19'), import('https://esm.sh/@upscalerjs/esrgan-slim@1.0.0-beta.12/2x')])
      .then(function (m) { var U = m[0].default, model = m[1].default; var up = new U({ model: model }); say('#aSt', 'Увеличиваю ×2 (браузер, может занять минуту)…'); return up.upscale(c.toDataURL('image/png'), { patchSize: 64, padding: 4, progress: function (p) { say('#aSt', 'Увеличение: ' + Math.round(p * 100) + '%'); } }); })
      .then(function (src) { say('#aSt', 'Готово — в редакторе (×2).'); return insertImage(src, 'Увеличено ×2'); })
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


  /* --- диалог с NOX: ядро с памятью; «нарисуй…» → генерация; галочка — NOX видит холст --- */
  var hist = [], log = $('#cLog');
  function bubble(cls, text) { var d = document.createElement('div'); d.className = 'm ' + cls; d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d; }
  var SYS = 'Ты NOX в разделе «Фотостудия» (редактор слоёв + генерация картинок на сервере). Отвечай по-русски, коротко и по делу. ' +
    'Если Создатель просит создать, нарисовать, сгенерировать изображение или вариант картинки — ответь одной-двумя фразами и последней строкой выдай: GEN: <подробный промпт на английском: объект, стиль, свет, композиция>. Иначе строку GEN не пиши.';
  function send() {
    var q = $('#cIn').value.trim(); if (!q) return; $('#cIn').value = ''; bubble('u', q); var nb = bubble('n', '…'), b = $('#cGo'); busy(b, true);
    var done = function () { busy(b, false); };
    if ($('#cSee').checked) {
      var ctx = hist.slice(-6).map(function (m) { return (m.role === 'user' ? 'Создатель: ' : 'NOX: ') + m.content; }).join('\n');
      return fetch('/vision/describe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: small(canvasOut(), 768), prompt: 'Ты NOX, фоторедактор. Контекст диалога:\n' + ctx + '\n\nСоздатель: ' + q + '\nОтветь по-русски, опираясь на изображение.' }) })
        .then(function (r) { return r.json(); }).then(function (j) { var t = j.text || ('Ошибка: ' + (j.error || 'нет ответа')); nb.textContent = t; hist.push({ role: 'user', content: q }, { role: 'assistant', content: t }); }).catch(function (e) { nb.textContent = 'Ошибка: ' + e.message; }).then(done);
    }
    hist.push({ role: 'user', content: q }); var acc = '';
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: 'fast', messages: [{ role: 'system', content: SYS }].concat(hist.slice(-12)) }) })
      .then(function (r) { var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
        function pump() { return rd.read().then(function (x) { if (x.done) return; buf += dec.decode(x.value, { stream: true }); var k; while ((k = buf.indexOf('\n')) >= 0) { var l = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!l) continue; try { var d = JSON.parse(l); if (d.message && d.message.content) { acc += d.message.content; nb.textContent = acc.replace(/\n?GEN:[\s\S]*$/, ''); log.scrollTop = log.scrollHeight; } } catch (e) {} } return pump(); }); }
        return pump(); })
      .then(function () { hist.push({ role: 'assistant', content: acc }); var m = /GEN:\s*([\s\S]+)$/.exec(acc);
        if (m) { var p = m[1].trim().split('\n')[0]; $('#gP').value = p; var gb = bubble('n', '🎨 Рисую…'); return generate(p).then(function (u) { if (u) { gb.textContent = 'Готово — картинка в редакторе:'; var im = new Image(); im.src = u; im.onclick = function () { insertImage(u, 'NOX'); }; gb.appendChild(im); } else gb.textContent = 'Видеокарта занята или генерация недоступна — попробую позже.'; }); } })
      .catch(function (e) { nb.textContent = 'NOX не ответил: ' + e.message; }).then(done);
  }
  $('#cGo').onclick = send; $('#cIn').addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  bubble('n', 'Я в Фотостудии. Скажи, что нарисовать, или включи «NOX видит холст» — подскажу по фото.');

  /* --- фильтры копией --- */
  Array.prototype.forEach.call(document.querySelectorAll('[data-f]'), function (b) {
    b.onclick = function () { var src = canvasOut(), c = document.createElement('canvas'); c.width = src.width; c.height = src.height; var x = c.getContext('2d'); x.filter = b.getAttribute('data-f'); x.drawImage(src, 0, 0); insertImage(c.toDataURL('image/png'), b.textContent).catch(function (e) { alert(e.message); }); };
  });
})();
