/* NOX · Инструменты: 20 модулей (vendor/nox-x), ленивая загрузка, NOX в каждом модуле, ТВ-режим. */
(function () {
  'use strict';
  var X = './vendor/nox-x/';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var el = function (t, a, h) { var e = document.createElement(t); if (a) for (var k in a) { if (k === 'cls') e.className = a[k]; else e.setAttribute(k, a[k]); } if (h != null) e.innerHTML = h; return e; };
  var loaded = {};
  function js(src) { return loaded[src] || (loaded[src] = new Promise(function (ok, no) { var s = el('script', { src: src }); s.onload = ok; s.onerror = function () { delete loaded[src]; no(new Error('не загрузился ' + src)); }; document.head.appendChild(s); })); }
  function css(href) { if (loaded[href]) return; loaded[href] = 1; document.head.appendChild(el('link', { rel: 'stylesheet', href: href })); }
  function seq(list) { return list.reduce(function (p, s) { return p.then(function () { return js(s); }); }, Promise.resolve()); }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem('nox-tools:' + k) || 'null'); localStorage.setItem('nox-tools:' + k, JSON.stringify(v)); } catch (e) { return null; } }
  function download(name, data, type) { var b = data instanceof Blob ? data : new Blob([data], { type: type || 'text/plain' }); var a = el('a', { href: URL.createObjectURL(b), download: name }); document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500); }
  function pickFile(accept, multi) { return new Promise(function (ok) { var i = el('input', { type: 'file', accept: accept || '' }); if (multi) i.multiple = true; i.onchange = function () { ok(multi ? Array.from(i.files) : i.files[0]); }; i.click(); }); }
  var tvChan = ('BroadcastChannel' in window) ? new BroadcastChannel('nox-tv') : null;
  function toTV(msg) { if (tvChan) tvChan.postMessage(msg); try { localStorage.setItem('nox-tv:last', JSON.stringify(msg)); } catch (e) {} }

  /* ---- NOX: ответ потоком через /api/chat (NDJSON) ---- */
  function askNox(prompt, onPart, mode) {
    var out = $('#stNox'), txt = $('#stNoxOut'); out.hidden = false; txt.textContent = '…'; var acc = '';
    return fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: mode || 'fast', messages: [{ role: 'user', content: prompt }] }) })
      .then(function (r) {
        if (!r.ok || !r.body) throw new Error('HTTP ' + r.status);
        var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
        function pump() { return rd.read().then(function (x) {
          if (x.done) return acc;
          buf += dec.decode(x.value, { stream: true }); var k;
          while ((k = buf.indexOf('\n')) >= 0) { var line = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!line) continue;
            try { var d = JSON.parse(line); var c = d.message && d.message.content; if (c) { acc += c; txt.textContent = acc; if (onPart) onPart(acc); } if (d.error) txt.textContent = 'Ошибка: ' + d.error; } catch (e) {} }
          return pump(); }); }
        return pump();
      }).catch(function (e) { txt.textContent = 'NOX не ответил: ' + e.message; return ''; });
  }

  /* ---- каркас ---- */
  var cur = null;
  function stage(m) {
    $('#grid').hidden = true; $('#stage').hidden = false; $('#backBtn').hidden = false;
    $('#stTitle').textContent = m.name; $('#stTools').innerHTML = ''; $('#stNox').hidden = true;
    var body = $('#stBody'); body.innerHTML = ''; body.className = 'nt-body' + (m.pad ? ' pad' : '');
    cur = { m: m, cleanup: null };
    body.innerHTML = '<p class="muted" style="padding:14px">Загружаю модуль…</p>';
    Promise.resolve().then(function () { body.innerHTML = ''; return m.open(body, tools); })
      .catch(function (e) { body.innerHTML = '<p style="padding:14px;color:#ff9a9a">Модуль не открылся: ' + e.message + '</p>'; });
    history.replaceState(null, '', '#' + m.id);
  }
  function tools(label, fn, cls) { var b = el('button', { type: 'button' }, label); if (cls) b.className = cls; b.onclick = fn; $('#stTools').appendChild(b); return b; }
  function close() { if (cur && cur.cleanup) try { cur.cleanup(); } catch (e) {} cur = null; $('#stage').hidden = true; $('#grid').hidden = false; $('#backBtn').hidden = true; $('#stBody').innerHTML = ''; history.replaceState(null, '', location.pathname); }
  function onClose(fn) { if (cur) cur.cleanup = fn; }

  /* ---- 20 модулей ---- */
  var M = [];
  function mod(id, icon, name, desc, lib, open, pad) { M.push({ id: id, icon: icon, name: name, desc: desc, lib: lib, open: open, pad: pad }); }

  mod('code', 'code', 'Код', 'Редактор с подсветкой, NOX разбирает и правит код', 'Monaco', function (b, t) {
    return js(X + 'monaco/min/vs/loader.js').then(function () { return new Promise(function (ok) {
      window.require.config({ paths: { vs: X + 'monaco/min/vs' } }); window.require(['vs/editor/editor.main'], ok); }); }).then(function () {
      var mo = window.monaco; mo.editor.defineTheme('nox', { base: 'vs-dark', inherit: true, rules: [], colors: { 'editor.background': '#05070dcc', 'editor.lineHighlightBackground': '#7cc8ff12' } });
      var ed = mo.editor.create(b, { value: store('code') || '# NOX: вставь код и нажми «NOX: разбери»\nprint("Привет, Создатель")\n', language: store('codeLang') || 'python', theme: 'nox', automaticLayout: true, fontSize: 14, minimap: { enabled: false } });
      ed.onDidChangeModelContent(function () { store('code', ed.getValue()); });
      var sel = el('select'); ['python', 'javascript', 'typescript', 'bash', 'json', 'html', 'css', 'markdown', 'sql', 'yaml', 'cpp', 'go', 'rust'].forEach(function (l) { var o = el('option', { value: l }, l); if (l === (store('codeLang') || 'python')) o.selected = true; sel.appendChild(o); });
      sel.onchange = function () { mo.editor.setModelLanguage(ed.getModel(), sel.value); store('codeLang', sel.value); }; $('#stTools').appendChild(sel);
      t('Открыть', function () { pickFile('', false).then(function (f) { if (f) f.text().then(function (s) { ed.setValue(s); }); }); });
      t('Скачать', function () { download('nox-code.' + ({ python: 'py', javascript: 'js', typescript: 'ts', bash: 'sh', markdown: 'md' }[sel.value] || sel.value), ed.getValue()); });
      t('NOX: разбери', function () { var s = ed.getModel().getValueInRange(ed.getSelection()) || ed.getValue(); askNox('Разбери этот код (' + sel.value + '): что делает, ошибки, как улучшить. Коротко и по делу.\n\n```\n' + s.slice(0, 12000) + '\n```'); }, 'nt-ai');
      t('NOX: исправь', function () { var s = ed.getValue(); askNox('Исправь и улучши код (' + sel.value + '). Верни только итоговый код в одном блоке ```.\n\n```\n' + s.slice(0, 12000) + '\n```').then(function (a) { var m = /```[a-z]*\n([\s\S]*?)```/.exec(a); if (m && confirm('Заменить код версией NOX?')) ed.setValue(m[1]); }); }, 'nt-ai');
      onClose(function () { ed.dispose(); });
    });
  });

  mod('console', 'terminal-2', 'Консоль', 'Терминал-диалог с NOX: команды и ответы потоком', 'xterm.js', function (b, t) {
    css(X + 'xterm/xterm.css');
    return seq([X + 'xterm/xterm.js', X + 'xterm/addon-fit.js']).then(function () {
      var term = new window.Terminal({ cursorBlink: true, fontSize: 14, theme: { background: '#04060cdd', foreground: '#cfe6ff', cursor: '#7cc8ff' }, allowTransparency: true });
      var fit = new window.FitAddon.FitAddon(); term.loadAddon(fit); term.open(b); fit.fit();
      var ro = new ResizeObserver(function () { try { fit.fit(); } catch (e) {} }); ro.observe(b);
      var line = '', busy = false; term.writeln('\x1b[38;5;117mNOX консоль\x1b[0m — пиши вопрос и Enter. /clear — очистить.'); term.write('\r\n\x1b[38;5;215mnox›\x1b[0m ');
      term.onData(function (d) {
        if (busy) return;
        if (d === '\r') { var q = line.trim(); line = ''; term.write('\r\n');
          if (q === '/clear') { term.clear(); term.write('\x1b[38;5;215mnox›\x1b[0m '); return; }
          if (!q) { term.write('\x1b[38;5;215mnox›\x1b[0m '); return; }
          busy = true; var shown = 0;
          askNox(q, function (acc) { term.write(acc.slice(shown).replace(/\n/g, '\r\n')); shown = acc.length; }).then(function () { busy = false; term.write('\r\n\x1b[38;5;215mnox›\x1b[0m '); });
        } else if (d === '\u007f') { if (line) { line = line.slice(0, -1); term.write('\b \b'); } }
        else if (d >= ' ' || d.length > 1) { line += d; term.write(d); }
      });
      $('#stNox').hidden = true; var orig = $('#stNox'); orig.style.display = 'none';
      onClose(function () { ro.disconnect(); term.dispose(); orig.style.display = ''; });
    });
  });

  mod('board', 'chalkboard', 'Доска', 'Наброски, схемы, стрелки — сохраняется сама', 'Excalidraw', function (b, t) {
    window.EXCALIDRAW_ASSET_PATH = X + 'excalidraw/dist/';
    return seq([X + 'react/react.production.min.js', X + 'react/react-dom.production.min.js', X + 'excalidraw/dist/excalidraw.production.min.js']).then(function () {
      var R = window.React, RD = window.ReactDOM, E = window.ExcalidrawLib, api = null, saved = store('board') || {};
      b.style.height = '72vh';
      var root = RD.createRoot(b);
      root.render(R.createElement(E.Excalidraw, { theme: 'dark', langCode: 'ru-RU', initialData: { elements: saved.elements || [], appState: { viewBackgroundColor: 'transparent', theme: 'dark' } },
        excalidrawAPI: function (a) { api = a; },
        onChange: function (els) { clearTimeout(b._t); b._t = setTimeout(function () { store('board', { elements: els }); }, 600); } }));
      t('PNG', function () { if (!api) return; E.exportToBlob({ elements: api.getSceneElements(), appState: { exportBackground: true, viewBackgroundColor: '#05070d' }, files: api.getFiles() }).then(function (bl) { download('nox-board.png', bl); }); });
      t('NOX: что на доске?', function () { if (!api) return; var tx = api.getSceneElements().filter(function (e) { return e.type === 'text'; }).map(function (e) { return e.text; }).join('\n'); askNox('На моей доске такие надписи:\n' + (tx || '(текста нет)') + '\nПодскажи, как развить эту схему.'); }, 'nt-ai');
      onClose(function () { root.unmount(); });
    });
  });

  mod('notes', 'notebook', 'Заметки', 'Редактор текста, автосохранение, NOX улучшает', 'Quill', function (b, t) {
    css(X + 'quill/quill.snow.css'); b.className += ' pad';
    return js(X + 'quill/quill.js').then(function () {
      var box = el('div'); box.style.minHeight = '55vh'; b.appendChild(box);
      var q = new window.Quill(box, { theme: 'snow', placeholder: 'Пиши… NOX рядом.', modules: { toolbar: [[{ header: [1, 2, 3, false] }], ['bold', 'italic', 'underline', 'strike'], [{ list: 'ordered' }, { list: 'bullet' }], ['blockquote', 'code-block', 'link'], ['clean']] } });
      var s = store('notes'); if (s) q.setContents(s);
      q.on('text-change', function () { store('notes', q.getContents()); });
      t('Скачать HTML', function () { download('nox-notes.html', '<meta charset="utf-8">' + q.root.innerHTML, 'text/html'); });
      t('NOX: улучши текст', function () { askNox('Улучши текст: ясность, стиль, без воды. Верни только текст.\n\n' + q.getText().slice(0, 10000)); }, 'nt-ai');
      t('NOX: продолжи', function () { askNox('Продолжи этот текст в том же стиле (1–2 абзаца):\n\n' + q.getText().slice(-4000)).then(function (a) { if (a) q.insertText(q.getLength(), '\n' + a); }); }, 'nt-ai');
    });
  }, true);

  function tableApp(b, t, kind) {
    css(X + 'tabulator/tabulator_midnight.min.css'); b.className += ' pad';
    return seq([X + 'tabulator/tabulator.min.js', X + 'xlsx/xlsx.full.min.js']).then(function () {
      var box = el('div'); b.appendChild(box);
      var data = store('table') || [{ 'Задача': 'Пример', 'Статус': 'в работе', 'Срок': '2026-12-01' }];
      var tb = new window.Tabulator(box, { data: data, autoColumns: true, layout: 'fitDataStretch', height: '60vh', reactiveData: false,
        autoColumnsDefinitions: function (defs) { defs.forEach(function (d) { d.editor = 'input'; d.headerFilter = 'input'; }); return defs; } });
      tb.on('dataChanged', function (d) { store('table', d); });
      function load(f) { f.arrayBuffer().then(function (ab) { var wb = window.XLSX.read(ab); var rows = window.XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' }); tb.setColumns([]); tb.setData(rows).then(function () { tb.setColumns(Object.keys(rows[0] || {}).map(function (k) { return { title: k, field: k, editor: 'input', headerFilter: 'input' }; })); store('table', rows); }); }); }
      t('Открыть Excel/CSV', function () { pickFile('.xlsx,.xls,.csv,.ods').then(function (f) { if (f) load(f); }); });
      t('+ строка', function () { tb.addRow({}); });
      t('Скачать .xlsx', function () { var ws = window.XLSX.utils.json_to_sheet(tb.getData()); var wb = window.XLSX.utils.book_new(); window.XLSX.utils.book_append_sheet(wb, ws, 'NOX'); window.XLSX.writeFile(wb, 'nox-table.xlsx'); });
      t('Скачать .csv', function () { tb.download('csv', 'nox-table.csv'); });
      t('NOX: анализ', function () { askNox('Проанализируй таблицу: итоги, закономерности, что важно. Данные (CSV):\n' + window.XLSX.utils.sheet_to_csv(window.XLSX.utils.json_to_sheet(tb.getData())).slice(0, 12000)); }, 'nt-ai');
    });
  }
  mod('table', 'table', 'Таблицы', 'Редактирование, фильтры, сортировка', 'Tabulator', function (b, t) { return tableApp(b, t); });
  mod('excel', 'file-spreadsheet', 'Excel', 'Открыть и сохранить .xlsx/.csv, анализ NOX', 'SheetJS', function (b, t) { return tableApp(b, t, 'x'); });

  mod('word', 'file-word', 'Word', 'Просмотр .docx, пересказ и выжимка от NOX', 'Mammoth', function (b, t) {
    b.className += ' pad';
    return js(X + 'mammoth/mammoth.browser.min.js').then(function () {
      var view = el('div', { cls: 'nt-out' }, 'Открой .docx — текст появится здесь.'); b.appendChild(view); var plain = '';
      t('Открыть .docx', function () { pickFile('.docx').then(function (f) { if (!f) return; f.arrayBuffer().then(function (ab) { return Promise.all([window.mammoth.convertToHtml({ arrayBuffer: ab }), window.mammoth.extractRawText({ arrayBuffer: ab })]); }).then(function (r) { view.style.whiteSpace = 'normal'; view.innerHTML = r[0].value; plain = r[1].value; }); }); });
      t('NOX: перескажи', function () { askNox('Перескажи документ: суть, ключевые пункты, что сделать.\n\n' + plain.slice(0, 14000)); }, 'nt-ai');
      t('NOX: найди риски', function () { askNox('Найди в документе риски, слабые места и спорные формулировки. Кратко, по пунктам.\n\n' + plain.slice(0, 14000)); }, 'nt-ai');
    });
  }, true);

  mod('pdf', 'file-type-pdf', 'PDF', 'Склеить файлы, вырезать страницы', 'pdf-lib', function (b, t) {
    b.className += ' pad';
    return js(X + 'pdflib/pdf-lib.min.js').then(function () {
      var L = window.PDFLib, files = [], info = el('div', { cls: 'nt-out' }, 'Добавь PDF-файлы (можно несколько).'); b.appendChild(info);
      var rng = el('input', { placeholder: 'страницы, напр. 1-3,7', style: 'margin-top:8px;padding:6px;border-radius:8px;background:rgba(0,0,0,.35);color:inherit;border:1px solid rgba(150,190,255,.2)' }); b.appendChild(rng);
      function show() { info.textContent = files.length ? files.map(function (f, i) { return (i + 1) + '. ' + f.name; }).join('\n') : 'Добавь PDF-файлы.'; }
      t('Добавить PDF', function () { pickFile('application/pdf', true).then(function (fs) { files = files.concat(fs || []); show(); }); });
      t('Очистить', function () { files = []; show(); });
      t('Склеить', function () { if (!files.length) return; L.PDFDocument.create().then(function (out) { return files.reduce(function (p, f) { return p.then(function () { return f.arrayBuffer(); }).then(function (ab) { return L.PDFDocument.load(ab); }).then(function (src) { return out.copyPages(src, src.getPageIndices()); }).then(function (pg) { pg.forEach(function (x) { out.addPage(x); }); }); }, Promise.resolve()).then(function () { return out.save(); }); }).then(function (bytes) { download('nox-merged.pdf', new Blob([bytes], { type: 'application/pdf' })); }); });
      t('Вырезать страницы', function () { if (!files[0]) return; var want = []; rng.value.split(',').forEach(function (p) { var m = p.trim().split('-'); var a = +m[0], z = +(m[1] || m[0]); for (var i = a; i <= z; i++) if (i > 0) want.push(i - 1); });
        files[0].arrayBuffer().then(function (ab) { return Promise.all([L.PDFDocument.load(ab), L.PDFDocument.create()]); }).then(function (r) { var idx = want.filter(function (i) { return i < r[0].getPageCount(); }); return r[1].copyPages(r[0], idx).then(function (pg) { pg.forEach(function (x) { r[1].addPage(x); }); return r[1].save(); }); }).then(function (bytes) { download('nox-pages.pdf', new Blob([bytes], { type: 'application/pdf' })); }); });
    });
  }, true);

  mod('ocr', 'scan', 'Распознать текст', 'Фото или скан → текст (рус/англ)', 'Tesseract.js', function (b, t) {
    b.className += ' pad';
    return js(X + 'tesseract/tesseract.min.js').then(function () {
      var row = el('div', { cls: 'nt-row' }), img = el('img', { style: 'max-width:100%;max-height:55vh;border-radius:8px' }), col1 = el('div', { cls: 'nt-col' }), col2 = el('div', { cls: 'nt-col' }), out = el('div', { cls: 'nt-out' }, 'Открой изображение.');
      col1.appendChild(img); col2.appendChild(out); row.appendChild(col1); row.appendChild(col2); b.appendChild(row); var text = '';
      t('Открыть фото', function () { pickFile('image/*').then(function (f) { if (!f) return; img.src = URL.createObjectURL(f); out.textContent = 'Распознаю… (первый раз дольше: загружаются языки)';
        window.Tesseract.recognize(f, 'rus+eng', { workerPath: X + 'tesseract/worker.min.js', corePath: X + 'tesseract/', langPath: X + 'tesseract/', gzip: true, logger: function (m) { if (m.status) out.textContent = m.status + ' ' + Math.round((m.progress || 0) * 100) + '%'; } })
          .then(function (r) { text = r.data.text; out.textContent = text || '(текст не найден)'; }).catch(function (e) { out.textContent = 'Ошибка: ' + e.message; }); }); });
      t('Копировать', function () { navigator.clipboard && navigator.clipboard.writeText(text); });
      t('NOX: разбери', function () { askNox('Вот текст, распознанный с фото. Исправь ошибки распознавания и кратко объясни, что это.\n\n' + text.slice(0, 10000)); }, 'nt-ai');
    });
  }, true);

  mod('upload', 'cloud-upload', 'Файлы для NOX', 'Перетащи файлы — NOX прочитает и ответит', 'Uppy', function (b, t) {
    css(X + 'uppy/uppy.min.css');
    return js(X + 'uppy/uppy.min.js').then(function () {
      var U = window.Uppy; var up = new U.Uppy({ autoProceed: false, restrictions: { maxFileSize: 50 * 1024 * 1024 } });
      up.use(U.Dashboard, { inline: true, target: b, theme: 'dark', height: 460, width: '100%', proudlyDisplayPoweredByUppy: false, hideUploadButton: true, note: 'Текст, код, CSV, JSON, Markdown — NOX прочитает.' });
      t('NOX: прочитай файлы', function () { var fs = up.getFiles(); if (!fs.length) return;
        Promise.all(fs.map(function (f) { return /^(text|application\/(json|xml|javascript))/.test(f.type || '') || /\.(md|txt|csv|json|py|js|ts|sh|yaml|yml|html|css|log)$/i.test(f.name) ? f.data.text().then(function (s) { return '### ' + f.name + '\n' + s.slice(0, 6000); }) : Promise.resolve('### ' + f.name + ' (' + (f.type || 'файл') + ', ' + Math.round(f.size / 1024) + ' КБ — не текст)'); }))
          .then(function (parts) { askNox('Прочитай эти файлы и дай суть каждого и общий вывод:\n\n' + parts.join('\n\n').slice(0, 16000)); }); }, 'nt-ai');
      onClose(function () { up.close && up.close(); up.destroy && up.destroy(); });
    });
  });

  mod('photo', 'photo-edit', 'Фото', 'Обрезка, поворот, отражение, экспорт', 'Cropper.js', function (b, t) {
    css(X + 'cropper/cropper.min.css'); b.className += ' pad';
    return js(X + 'cropper/cropper.min.js').then(function () {
      var img = el('img', { style: 'max-width:100%;display:block' }), cr = null; var w = el('div', { style: 'max-height:62vh' }); w.appendChild(img); b.appendChild(w);
      function make() { if (cr) cr.destroy(); cr = new window.Cropper(img, { viewMode: 1, background: false, autoCropArea: .9 }); }
      t('Открыть', function () { pickFile('image/*').then(function (f) { if (!f) return; img.onload = make; img.src = URL.createObjectURL(f); }); });
      t('⟲', function () { cr && cr.rotate(-90); }); t('⟳', function () { cr && cr.rotate(90); });
      t('⇋', function () { if (cr) { var d = cr.getData(); cr.scaleX(d.scaleX === -1 ? 1 : -1); } });
      ['1:1', '16:9', '4:3', 'свободно'].forEach(function (r) { t(r, function () { cr && cr.setAspectRatio(r === 'свободно' ? NaN : eval(r.replace(':', '/'))); }); });
      t('Скачать PNG', function () { cr && cr.getCroppedCanvas().toBlob(function (bl) { download('nox-photo.png', bl); }); });
      onClose(function () { cr && cr.destroy(); });
    });
  }, true);

  mod('gantt', 'chart-bar', 'План (Гант)', 'Задачи на шкале времени, перетаскивание', 'Frappe Gantt', function (b, t) {
    css(X + 'gantt/frappe-gantt.min.css'); css(X + 'gantt/frappe-gantt.css'); b.className += ' pad';
    return js(X + 'gantt/frappe-gantt.min.js').then(function () {
      var d0 = new Date(), iso = function (d) { return d.toISOString().slice(0, 10); }, add = function (n) { var d = new Date(d0); d.setDate(d.getDate() + n); return iso(d); };
      var tasks = store('gantt') || [{ id: 't1', name: 'Веб NOX: модули', start: add(0), end: add(2), progress: 60 }, { id: 't2', name: 'ТВ-режим', start: add(1), end: add(3), progress: 20, dependencies: 't1' }];
      var box = el('div', { style: 'background:rgba(255,255,255,.92);border-radius:10px;color:#111' }); b.appendChild(box);
      var g; function draw() { box.innerHTML = '<svg></svg>'; g = new window.Gantt(box.firstChild, tasks, { language: 'ru', view_mode: 'Day', on_date_change: function (task, s, e) { task.start = iso(s); task.end = iso(e); store('gantt', tasks); }, on_progress_change: function (task, p) { task.progress = p; store('gantt', tasks); } }); }
      draw();
      t('+ задача', function () { var n = prompt('Название задачи'); if (!n) return; tasks.push({ id: 't' + Date.now(), name: n, start: add(0), end: add(1), progress: 0 }); store('gantt', tasks); draw(); });
      ['Day', 'Week', 'Month'].forEach(function (v) { t({ Day: 'Дни', Week: 'Недели', Month: 'Месяцы' }[v], function () { g.change_view_mode(v); }); });
      t('NOX: оцени план', function () { askNox('Оцени план проекта, найди риски и предложи порядок:\n' + tasks.map(function (x) { return '- ' + x.name + ': ' + x.start + ' → ' + x.end + ', ' + x.progress + '%'; }).join('\n')); }, 'nt-ai');
    });
  }, true);

  mod('mindmap', 'binary-tree-2', 'Карта мыслей', 'Markdown → интерактивная карта; NOX строит по теме', 'Markmap', function (b, t) {
    b.className += ' pad';
    return seq([X + 'markmap/d3.min.js', X + 'markmap/index.iife.js', X + 'markmap/index.js']).then(function () {
      var ta = el('textarea', { cls: 'nt-ta' }); ta.value = store('mm') || '# NOX\n## Разум\n- память\n- личность\n## Тело\n- сервер\n- голос\n## Рост\n- обучение\n- инструменты';
      var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.style.width = '100%'; svg.style.height = '48vh';
      b.appendChild(svg); b.appendChild(ta);
      var tr = new window.markmap.Transformer(), mm = window.markmap.Markmap.create(svg, { color: function () { return '#7cc8ff'; } });
      function draw() { var r = tr.transform(ta.value); mm.setData(r.root); mm.fit(); store('mm', ta.value); }
      ta.oninput = function () { clearTimeout(ta._t); ta._t = setTimeout(draw, 300); }; draw();
      svg.style.color = '#dbeaff';
      t('NOX: построй по теме', function () { var q = prompt('Тема карты'); if (!q) return; askNox('Составь подробную карту мыслей в Markdown по теме «' + q + '»: # заголовок, ## ветви, - пункты. Только Markdown, без пояснений.').then(function (a) { var m = /```(?:markdown|md)?\n([\s\S]*?)```/.exec(a); ta.value = (m ? m[1] : a).trim(); draw(); }); }, 'nt-ai');
      t('SVG', function () { download('nox-mindmap.svg', new XMLSerializer().serializeToString(svg), 'image/svg+xml'); });
    });
  }, true);

  mod('slides', 'presentation', 'Презентации', 'Слайды из Markdown; NOX делает; показ на проекторе', 'Reveal.js', function (b, t) {
    css(X + 'reveal/reveal.css'); css(X + 'reveal/black.css');
    return seq([X + 'reveal/reveal.js', X + 'reveal/markdown.js']).then(function () {
      var wrap = el('div', { cls: 'nt-row', style: 'height:100%' }), ta = el('textarea', { cls: 'nt-ta', style: 'min-height:60vh;max-width:34%' }), deckBox = el('div', { cls: 'nt-col', style: 'height:62vh;position:relative' });
      ta.value = store('slides') || '# NOX HELION\nЖивой разум на своём сервере\n---\n## Что умеет\n- помнит\n- говорит голосом\n- строит планы\n---\n## Спасибо';
      wrap.appendChild(ta); wrap.appendChild(deckBox); b.appendChild(wrap); var deck = null;
      function build() { store('slides', ta.value); if (deck) try { deck.destroy(); } catch (e) {} deckBox.innerHTML = '<div class="reveal"><div class="slides"><section data-markdown><textarea data-template></textarea></section></div></div>';
        deckBox.querySelector('textarea').value = ta.value; deck = new window.Reveal(deckBox.querySelector('.reveal'), { embedded: true, hash: false, plugins: [window.RevealMarkdown], controls: true, progress: true }); deck.initialize(); }
      ta.oninput = function () { clearTimeout(ta._t); ta._t = setTimeout(build, 600); }; build();
      t('NOX: сделай слайды', function () { var q = prompt('Тема презентации'); if (!q) return; askNox('Сделай презентацию на 6–8 слайдов по теме «' + q + '» в Markdown для reveal.js: слайды разделяй строкой ---, заголовки ##, коротко. Только Markdown.').then(function (a) { var m = /```(?:markdown|md)?\n([\s\S]*?)```/.exec(a); ta.value = (m ? m[1] : a).trim(); build(); }); }, 'nt-ai');
      t('На проектор', function () { toTV({ type: 'slides', md: ta.value }); openTV(); });
      t('Во весь экран', function () { deckBox.requestFullscreen && deckBox.requestFullscreen(); });
      onClose(function () { try { deck && deck.destroy(); } catch (e) {} });
    });
  });

  mod('map3d', 'map-2', '3D-карта', 'Векторная карта с наклоном и геопозицией', 'MapLibre GL', function (b, t) {
    css(X + 'maplibre/maplibre-gl.css');
    return js(X + 'maplibre/maplibre-gl.js').then(function () {
      b.style.height = '70vh';
      var map = new window.maplibregl.Map({ container: b, style: { version: 8, sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© OpenStreetMap' } }, layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -0.6, 'raster-brightness-max': 0.75 } }] }, center: [37.62, 55.75], zoom: 4, pitch: 50, bearing: -10 });
      map.addControl(new window.maplibregl.NavigationControl({ visualizePitch: true })); map.addControl(new window.maplibregl.GeolocateControl({}));
      t('Найти место', function () { var q = prompt('Город или адрес'); if (!q) return; fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (j) { if (j[0]) map.flyTo({ center: [+j[0].lon, +j[0].lat], zoom: 13, pitch: 60 }); }); });
      t('NOX: расскажи о месте', function () { var c = map.getCenter(); askNox('Расскажи коротко и интересно о месте с координатами ' + c.lat.toFixed(4) + ', ' + c.lng.toFixed(4) + '.'); }, 'nt-ai');
      onClose(function () { map.remove(); });
    });
  });

  mod('globe', 'world', 'Глобус', '3D-Земля: точки, дуги, вращение', 'Globe.gl', function (b, t) {
    return js(X + 'globe/globe.gl.min.js').then(function () {
      b.style.height = '72vh';
      var cities = [['Москва', 55.75, 37.62], ['Монреаль', 45.5, -73.57], ['Сеул', 37.57, 126.98], ['Лондон', 51.5, -0.12], ['Нью-Йорк', 40.71, -74], ['Токио', 35.68, 139.69], ['Дубай', 25.2, 55.27], ['Сидней', -33.86, 151.2]];
      var pts = cities.map(function (c) { return { name: c[0], lat: c[1], lng: c[2] }; });
      var g = window.Globe()(b).globeImageUrl('./vendor/nox-planets/earth_daymap.jpg').backgroundColor('rgba(0,0,0,0)').atmosphereColor('#7cc8ff').atmosphereAltitude(0.18)
        .pointsData(pts).pointColor(function () { return '#ffd08a'; }).pointAltitude(0.02).pointRadius(0.5).pointLabel('name')
        .arcsData([{ startLat: 37.57, startLng: 126.98, endLat: 55.75, endLng: 37.62 }, { startLat: 55.75, startLng: 37.62, endLat: 45.5, endLng: -73.57 }]).arcColor(function () { return ['#7cc8ff', '#ff7ab6']; }).arcDashLength(0.4).arcDashGap(0.2).arcDashAnimateTime(2500)
        .width(b.clientWidth).height(b.clientHeight);
      g.controls().autoRotate = true; g.controls().autoRotateSpeed = 0.5;
      g.onPointClick(function (p) { askNox('Расскажи в трёх фразах, что сейчас интересного в городе ' + p.name + '.'); });
      t('Вращение', function () { g.controls().autoRotate = !g.controls().autoRotate; });
      var ro = new ResizeObserver(function () { g.width(b.clientWidth).height(b.clientHeight); }); ro.observe(b);
      onClose(function () { ro.disconnect(); g._destructor && g._destructor(); });
    });
  });

  mod('synth', 'piano', 'Синтезатор', 'Пианино с клавиатуры, арпеджио, эффекты', 'Tone.js', function (b, t) {
    b.className += ' pad';
    return js(X + 'tone/Tone.js').then(function () {
      var T = window.Tone, rev = new T.Reverb(2.5).toDestination(), syn = new T.PolySynth(T.Synth, { oscillator: { type: 'triangle' }, envelope: { attack: 0.01, release: 1.2 } }).connect(rev);
      var notes = ['C4', 'C#4', 'D4', 'D#4', 'E4', 'F4', 'F#4', 'G4', 'G#4', 'A4', 'A#4', 'B4', 'C5', 'C#5', 'D5', 'D#5', 'E5', 'F5', 'F#5', 'G5', 'G#5', 'A5', 'A#5', 'B5', 'C6'];
      var keymap = 'zsxdcvgbhnjmq2w3er5t6y7ui'.split('');
      var kb = el('div', { cls: 'nt-keys' }); notes.forEach(function (n, i) { var k = el('div', { 'data-n': n }, keymap[i] || ''); if (n.indexOf('#') > 0) k.className = 'b'; k.onpointerdown = function () { T.start(); syn.triggerAttackRelease(n, '8n'); k.classList.add('on'); setTimeout(function () { k.classList.remove('on'); }, 180); }; kb.appendChild(k); });
      b.appendChild(el('p', { cls: 'muted' }, 'Играй мышкой или клавишами Z…M / Q…I. Кнопки сверху — тембр и арпеджио.')); b.appendChild(kb);
      function key(e) { var i = keymap.indexOf(e.key); if (i >= 0 && !e.repeat) { var k = kb.children[i]; k.onpointerdown(); } }
      document.addEventListener('keydown', key);
      ['triangle', 'sine', 'square', 'sawtooth'].forEach(function (w) { t({ triangle: 'Мягкий', sine: 'Чистый', square: 'Ретро', sawtooth: 'Яркий' }[w], function () { syn.set({ oscillator: { type: w } }); }); });
      var seq = null; t('Арпеджио', function () { T.start(); if (seq) { seq.stop(); seq.dispose(); seq = null; T.Transport.stop(); return; } seq = new T.Sequence(function (time, n) { syn.triggerAttackRelease(n, '16n', time); }, ['C4', 'E4', 'G4', 'B4', 'C5', 'B4', 'G4', 'E4'], '8n').start(0); T.Transport.bpm.value = 110; T.Transport.start(); });
      onClose(function () { document.removeEventListener('keydown', key); if (seq) { seq.stop(); seq.dispose(); } T.Transport.stop(); syn.dispose(); rev.dispose(); });
    });
  }, true);

  mod('visual', 'wave-sine', 'Визуализатор', 'Музыка → психоделика Milkdrop (файл или микрофон)', 'Butterchurn', function (b, t) {
    return seq([X + 'butterchurn/butterchurn.min.js', X + 'butterchurn/butterchurnPresets.min.js']).then(function () {
      var cv = el('canvas'); b.appendChild(cv); b.style.height = '70vh'; var ac = new (window.AudioContext || window.webkitAudioContext)();
      function size() { cv.width = b.clientWidth; cv.height = b.clientHeight; viz && viz.setRendererSize(cv.width, cv.height); }
      var bc = window.butterchurn.default || window.butterchurn, viz = bc.createVisualizer(ac, cv, { width: b.clientWidth, height: b.clientHeight });
      var P = (window.butterchurnPresets.default || window.butterchurnPresets).getPresets(), names = Object.keys(P), pi = Math.floor(Math.random() * names.length);
      viz.loadPreset(P[names[pi]], 0); size(); var raf, src = null, audio = null;
      (function loop() { viz.render(); raf = requestAnimationFrame(loop); })();
      t('Файл', function () { pickFile('audio/*').then(function (f) { if (!f) return; ac.resume(); if (audio) audio.pause(); audio = new Audio(URL.createObjectURL(f)); audio.play(); src = ac.createMediaElementSource(audio); src.connect(ac.destination); viz.connectAudio(src); }); });
      t('Микрофон', function () { ac.resume(); navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) { src = ac.createMediaStreamSource(s); viz.connectAudio(src); }); });
      t('Следующий', function () { pi = (pi + 1) % names.length; viz.loadPreset(P[names[pi]], 2); });
      t('Во весь экран', function () { cv.requestFullscreen && cv.requestFullscreen(); });
      var ro = new ResizeObserver(size); ro.observe(b);
      onClose(function () { cancelAnimationFrame(raf); ro.disconnect(); if (audio) audio.pause(); ac.close(); });
    });
  });

  /* VAD: речь → STT (/stt/transcribe) → NOX → голос (/tts/synth) */
  function wav16(f32) { var n = f32.length, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf), s = function (o, x) { for (var i = 0; i < x.length; i++) v.setUint8(o + i, x.charCodeAt(i)); };
    s(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); s(8, 'WAVE'); s(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); s(36, 'data'); v.setUint32(40, n * 2, true);
    for (var i = 0; i < n; i++) { var x = Math.max(-1, Math.min(1, f32[i])); v.setInt16(44 + i * 2, x < 0 ? x * 0x8000 : x * 0x7fff, true); } return new Blob([buf], { type: 'audio/wav' }); }
  function speak(text) {
    return fetch('/tts/synth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text.slice(0, 1500), lang: 'ru' }) }).then(function (r) {
      var rd = r.body.getReader(), dec = new TextDecoder(), buf = '', ac = new AudioContext(), at = ac.currentTime + 0.05;
      function pump() { return rd.read().then(function (x) { if (x.done) return; buf += dec.decode(x.value, { stream: true }); var k;
        while ((k = buf.indexOf('\n')) >= 0) { var l = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (l.indexOf('data:') !== 0) continue;
          try { var d = JSON.parse(l.slice(5)); if (d.type === 'audio') { var bin = atob(d.pcm_b64), n = bin.length / 2, ab = ac.createBuffer(1, n, d.sample_rate); var ch = ab.getChannelData(0);
            for (var i = 0; i < n; i++) { var v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8); ch[i] = (v > 32767 ? v - 65536 : v) / 32768; }
            var s = ac.createBufferSource(); s.buffer = ab; s.connect(ac.destination); at = Math.max(at, ac.currentTime); s.start(at); at += ab.duration; } } catch (e) {} }
        return pump(); }); }
      return pump();
    });
  }
  mod('voice', 'microphone', 'Голос (VAD)', 'Говори — NOX услышит конец фразы, ответит голосом', 'Silero VAD', function (b, t) {
    b.className += ' pad';
    window.ort = undefined;
    return seq([X + 'vad/ort.min.js', X + 'vad/bundle.min.js']).then(function () {
      var dot = el('span', { cls: 'nt-dot' }), st = el('b', null, 'выключено'), log = el('div', { cls: 'nt-out' }, 'Нажми «Слушать». Фраза закончится — NOX ответит.');
      var p = el('p'); p.appendChild(dot); p.appendChild(st); b.appendChild(p); b.appendChild(log); var vad = null, talk = true;
      t('Слушать', function () { if (vad) { vad.pause(); vad = null; st.textContent = 'выключено'; dot.classList.remove('on'); return; }
        window.vad.MicVAD.new({ baseAssetPath: X + 'vad/', onnxWASMBasePath: X + 'vad/', positiveSpeechThreshold: 0.6, minSpeechFrames: 4,
          onSpeechStart: function () { dot.classList.add('on'); st.textContent = 'слышу…'; },
          onSpeechEnd: function (audio) { dot.classList.remove('on'); st.textContent = 'распознаю…';
            fetch('/stt/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: wav16(audio) }).then(function (r) { return r.json(); }).then(function (j) {
              var q = (j.text || '').trim(); if (!q) { st.textContent = 'слушаю'; return; } log.textContent = 'Ты: ' + q; st.textContent = 'NOX думает…';
              askNox(q).then(function (a) { log.textContent = 'Ты: ' + q + '\n\nNOX: ' + a; st.textContent = 'слушаю'; if (talk && a) speak(a); }); }).catch(function (e) { st.textContent = 'ошибка STT: ' + e.message; }); } })
          .then(function (v) { vad = v; vad.start(); st.textContent = 'слушаю'; }).catch(function (e) { st.textContent = 'микрофон: ' + e.message; }); });
      t('Голос NOX: вкл/выкл', function () { talk = !talk; });
      onClose(function () { if (vad) vad.pause(); });
    });
  }, true);

  mod('sync', 'refresh-dot', 'Общие заметки', 'CRDT-заметка: правки сливаются между вкладками без потерь', 'Yjs', function (b, t) {
    b.className += ' pad';
    return import(X + 'yjs/yjs.bundle.mjs').then(function (Y) {
      var doc = new Y.Doc(), text = doc.getText('n'), bc = tvChan ? new BroadcastChannel('nox-yjs') : null, ta = el('textarea', { cls: 'nt-ta', style: 'min-height:55vh' });
      var saved = store('yjs'); if (saved) Y.applyUpdate(doc, Uint8Array.from(saved));
      ta.value = text.toString(); b.appendChild(el('p', { cls: 'muted' }, 'Открой эту заметку в нескольких вкладках — правки сливаются (CRDT). Синхронизацию между устройствами через сервер подключу следующим шагом.')); b.appendChild(ta);
      doc.on('update', function (u, origin) { store('yjs', Array.from(Y.encodeStateAsUpdate(doc))); if (origin !== 'remote' && bc) bc.postMessage(u); if (origin === 'remote') { var p = ta.selectionStart; ta.value = text.toString(); ta.selectionStart = ta.selectionEnd = Math.min(p, ta.value.length); } });
      if (bc) bc.onmessage = function (e) { Y.applyUpdate(doc, new Uint8Array(e.data), 'remote'); };
      ta.oninput = function () { doc.transact(function () { text.delete(0, text.length); text.insert(0, ta.value); }); };
      t('NOX: структурируй', function () { askNox('Структурируй эту заметку: заголовки, пункты, выводы.\n\n' + ta.value.slice(0, 10000)); }, 'nt-ai');
      onClose(function () { if (bc) bc.close(); doc.destroy(); });
    });
  }, true);

  /* ---- ТВ / проектор ---- */
  function openTV() {
    var url = new URL('tv.html', location.href).href;
    if (window.PresentationRequest) {
      try { var req = new PresentationRequest([url]); req.start().then(function (c) { toTV({ type: 'hello' }); window.__noxTV = c; }).catch(function () { tvHelp(url); }); return; } catch (e) {}
    }
    tvHelp(url);
  }
  function tvHelp(url) { window.open(url, 'nox-tv'); alert('Открыл ТВ-режим в новой вкладке.\nЧтобы вывести на проектор: в Chrome меню ⋮ → «Трансляция…» → выберите проектор (Android TV).'); }

  /* ---- сетка ---- */
  var grid = $('#grid');
  M.forEach(function (m, i) { var b = el('button', { type: 'button', cls: 'nt-tile', title: m.lib }, '<i class="mono">' + String(i + 1).padStart(2, '0') + '</i><sl-icon library="tabler" name="' + m.icon + '"></sl-icon><b>' + m.name + '</b><span>' + m.desc + '</span>'); b.onclick = function () { stage(m); }; grid.appendChild(b); });
  $('#backBtn').onclick = close; $('#tvBtn').onclick = openTV;
  var h = location.hash.slice(1); if (h) { var m0 = M.filter(function (m) { return m.id === h; })[0]; if (m0) stage(m0); }
  document.body.classList.remove('boot');
  window.NOX_TOOLS = { modules: M.map(function (m) { return m.id; }), askNox: askNox, toTV: toTV };
})();
