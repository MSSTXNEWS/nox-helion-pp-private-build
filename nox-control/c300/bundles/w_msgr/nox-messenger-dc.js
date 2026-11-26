/* NOX · внутренний мессенджер на готовом Deep Chat (без Matrix и без новых серверов): каналы-плитки «NOX» (живой ответ через /api/chat) и «Заметки себе» (хранятся в браузере).
   Чужой Matrix-клиент (Cinny/Element) подключается только к существующему аккаунту владельца: HOLD до его решения. Откат: ?msgr=0 */
(function () {
  'use strict';
  if (/[?&]msgr=0/.test(location.search)) return;
  var CH = { nox: { t: 'NOX', hint: 'Диалог с NOX: отвечает живая модель.', live: true }, me: { t: 'Заметки себе', hint: 'Личный канал: сообщения остаются в этом браузере.', live: false } };
  var cur = 'nox', dc = null;
  function K(c) { return 'nox.msgr.' + c; }
  function load(c) { try { return JSON.parse(localStorage.getItem(K(c)) || '[]'); } catch (e) { return []; } }
  function save(c, a) { try { localStorage.setItem(K(c), JSON.stringify(a.slice(-80))); } catch (e) {} }
  function mount() {
    var page = document.querySelector('.wrap'); if (!page || document.getElementById('nxMsgr')) return;
    var host = document.createElement('section'); host.className = 'card'; host.id = 'nxMsgr';
    host.innerHTML = '<h2>Мессенджер NOX</h2><p class="note" style="margin:0 0 10px" id="nxmHint"></p><div class="row" id="nxmTabs" role="group" aria-label="Каналы"></div><div id="nxmBox"></div>' +
      '<p class="note" style="margin-top:10px">Внешний мессенджер (Matrix: Cinny или Element Web) подключается к существующему аккаунту владельца, сервер не ставится. Статус: HOLD до решения владельца.</p>';
    var ph = page.querySelector('.purpose'); (ph && ph.parentNode === page ? ph.insertAdjacentElement('afterend', host) : page.appendChild(host));
    var tabs = host.querySelector('#nxmTabs');
    Object.keys(CH).forEach(function (k) { var b = document.createElement('button'); b.type = 'button'; b.className = 'btn'; b.textContent = CH[k].t; b.dataset.c = k; b.setAttribute('aria-pressed', String(k === cur)); b.addEventListener('click', function () { cur = k; tabs.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); x.style.borderColor = x === b ? '#9db1d1' : ''; }); render(); }); tabs.appendChild(b); if (k === cur) b.style.borderColor = '#9db1d1'; });
    render();
  }
  function render() {
    var box = document.getElementById('nxmBox'); document.getElementById('nxmHint').textContent = CH[cur].hint; box.innerHTML = '';
    dc = document.createElement('deep-chat'); dc.setAttribute('aria-label', 'Мессенджер: ' + CH[cur].t); box.appendChild(dc);
    dc.style.cssText = 'display:block;width:100%;height:min(460px,60vh);border:1px solid rgba(255,255,255,.1);border-radius:14px;background:transparent';
    dc.chatStyle = { backgroundColor: 'transparent', border: 'none', fontFamily: 'inherit' };
    dc.messageStyles = { default: { shared: { bubble: { borderRadius: '12px', padding: '8px 12px', fontSize: '15px', lineHeight: '1.55', maxWidth: '88%' } }, user: { bubble: { backgroundColor: '#2a2c30', color: '#edeef0' } }, ai: { bubble: { backgroundColor: '#18191b', color: '#edeef0' } } } };
    dc.textInput = { placeholder: { text: CH[cur].live ? 'Сообщение NOX…' : 'Заметка себе…' }, styles: { container: { backgroundColor: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.12)', borderRadius: '12px', color: '#edeef0' }, text: { color: '#edeef0', padding: '10px' } } };
    var hist = load(cur); dc.history = hist.map(function (m) { return { role: m.r, text: m.t }; });
    var ch = cur;
    function remember(r, t) { var a = load(ch); a.push({ r: r, t: t }); save(ch, a); }
    if (!CH[ch].live) {
      dc.connect = { handler: function (body, signals) { var t = (((body.messages || []).slice(-1)[0]) || {}).text || ''; remember('user', t); signals.onResponse({ text: 'Сохранено в заметках.' }); remember('ai', 'Сохранено в заметках.'); } };
    } else {
      dc.connect = { handler: function (body, signals) {
        var t = (((body.messages || []).slice(-1)[0]) || {}).text || ''; if (!t.trim()) { signals.onResponse({ error: 'Пустое сообщение' }); return; }
        remember('user', t); var msgs = load(ch).slice(-12).map(function (m) { return { role: m.r === 'ai' ? 'assistant' : 'user', content: m.t }; }), acc = '';
        fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: 'nox-helion:latest', stream: true, nox_mode: 'fast', conversation_id: 'msgr-nox', messages: msgs }) })
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); var rd = r.body.getReader(), dec = new TextDecoder(), buf = '';
            function pump() { return rd.read().then(function (x) { if (x.done) return; buf += dec.decode(x.value, { stream: true }); var k; while ((k = buf.indexOf('\n')) >= 0) { var l = buf.slice(0, k).trim(); buf = buf.slice(k + 1); if (!l) continue; try { var d = JSON.parse(l); var c = d.text || (d.message && d.message.content); if (c) acc += c; } catch (e) {} } return pump(); }); }
            return pump(); })
          .then(function () { var out = acc.trim() || 'NOX не ответил.'; remember('ai', out); signals.onResponse({ text: out }); })
          .catch(function (e) { signals.onResponse({ error: 'NOX не ответил: ' + e.message }); });
      } };
    }
    var n = 0, iv = setInterval(function () { var r = dc.shadowRoot; if (r) r.querySelectorAll('.input-button:not([aria-label]),[role=button]:not([aria-label])').forEach(function (b) { b.setAttribute('aria-label', 'Отправить'); }); if (++n > 30) clearInterval(iv); }, 500);
  }
  function boot() { customElements.whenDefined('deep-chat').then(mount); }
  function start() { if (customElements.get('deep-chat')) mount(); else { var s = document.createElement('script'); s.src = './vendor/deep-chat/deep-chat.iife.js'; s.onload = boot; document.head.appendChild(s); } }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(start, 300); }); else setTimeout(start, 300);
})();
