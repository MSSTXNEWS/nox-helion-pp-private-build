/* NOX · Звонки: Jitsi Meet External API (meet.jit.si, Apache-2.0, без установки сервера и без ключей). Скрипт Jitsi грузится только при входе в комнату. Откат: ?jitsi=0 */
(function () {
  'use strict';
  if (/[?&]jitsi=0/.test(location.search)) return;
  var HOST = 'meet.jit.si';
  function room() { var a = new Uint8Array(8); crypto.getRandomValues(a); return 'nox-' + Array.prototype.map.call(a, function (x) { return ('0' + x.toString(16)).slice(-2); }).join(''); }
  function mount() {
    var page = document.querySelector('.wrap'); if (!page || document.getElementById('nxJitsi')) return;
    var host = document.createElement('section'); host.className = 'card'; host.id = 'nxJitsi';
    host.innerHTML = '<h2>Видеозвонок · Jitsi Meet</h2>' +
      '<p class="note" style="margin:0 0 10px">Открытый сервис meet.jit.si встраивается в страницу, ничего не устанавливается. Комната создаётся случайной; кто знает ссылку, тот может зайти. Не передавайте через неё секретное.</p>' +
      '<div class="row"><button class="btn" type="button" id="nxjNew">Новая комната</button>' +
      '<input type="text" id="nxjRoom" aria-label="Название комнаты" placeholder="Название комнаты (латиница, цифры, дефис)" autocomplete="off" style="flex:1 1 240px;width:auto">' +
      '<button class="btn" type="button" id="nxjGo">Войти</button><button class="btn" type="button" id="nxjCopy">Копировать ссылку</button><button class="btn" type="button" id="nxjEnd" hidden>Выйти</button></div>' +
      '<div class="note" id="nxjSt" role="status"></div><div id="nxjBox" style="margin-top:10px;border-radius:12px;overflow:hidden"></div>';
    var ph = page.querySelector('.purpose'); (ph && ph.parentNode === page ? ph.insertAdjacentElement('afterend', host) : page.appendChild(host));
    var $ = function (id) { return document.getElementById(id); }, api = null, st = function (t) { $('nxjSt').textContent = t || ''; };
    var clean = function (s) { return String(s || '').toLowerCase().replace(/[^a-z0-9-]/g, '').slice(0, 64); };
    function load() { return new Promise(function (ok, no) { if (window.JitsiMeetExternalAPI) return ok(); var s = document.createElement('script'); s.src = 'https://' + HOST + '/external_api.js'; s.onload = ok; s.onerror = function () { no(new Error('не удалось загрузить ' + HOST)); }; document.head.appendChild(s); }); }
    function enter(name) {
      name = clean(name); if (!name) { st('Введите название или нажмите «Новая комната».'); return; }
      $('nxjRoom').value = name; st('Подключаю…');
      load().then(function () {
        if (api) { try { api.dispose(); } catch (e) {} }
        var box = $('nxjBox'); box.innerHTML = '';
        api = new JitsiMeetExternalAPI(HOST, { roomName: name, parent: box, width: '100%', height: Math.min(560, Math.round(innerHeight * 0.7)), lang: 'ru',
          configOverwrite: { prejoinPageEnabled: true, disableDeepLinking: true, defaultLanguage: 'ru' }, interfaceConfigOverwrite: { MOBILE_APP_PROMO: false } });
        $('nxjEnd').hidden = false; st('Комната: ' + name + '. Ссылка: https://' + HOST + '/' + name);
        try { history.replaceState(null, '', '#room=' + name); } catch (e) {}
      }).catch(function (e) { st('Не получилось: ' + e.message + '. Проверьте доступ к ' + HOST + '.'); });
    }
    $('nxjNew').onclick = function () { enter(room()); };
    $('nxjGo').onclick = function () { enter($('nxjRoom').value); };
    $('nxjCopy').onclick = function () { var n = clean($('nxjRoom').value); if (!n) return st('Сначала создайте комнату.'); var u = 'https://' + HOST + '/' + n; (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(function () { st('Ссылка скопирована: ' + u); }, function () { st('Ссылка: ' + u); }); };
    $('nxjEnd').onclick = function () { if (api) { try { api.dispose(); } catch (e) {} api = null; } $('nxjBox').innerHTML = ''; $('nxjEnd').hidden = true; st('Вы вышли из комнаты.'); };
    var m = /#room=([a-z0-9-]+)/.exec(location.hash); if (m) $('nxjRoom').value = m[1];
    Array.prototype.forEach.call(document.querySelectorAll('li'), function (li) { var n = li.querySelector('.name'), b = li.querySelector('.badge'); if (n && b && /^Звонок/.test(n.textContent.trim())) { b.className = 'badge b-live'; b.textContent = 'JITSI'; var no = li.querySelector('.note'); if (no) no.textContent = 'Видеозвонок через Jitsi Meet (карточка выше). Свой WebRTC не поднимается.'; } });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(mount, 300); }); else setTimeout(mount, 300);
})();
