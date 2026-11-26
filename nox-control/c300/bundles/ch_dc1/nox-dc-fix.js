/* NOX chat-dc fix (ACCEPT 26.11): hero после 1-го сообщения, цели 44, короткий заголовок. Откат ?dcfix=0 */
(function () {
  'use strict';
  if (/[?&]dcfix=0/.test(location.search)) return;
  var dc = document.querySelector('deep-chat'); if (!dc) return;
  var css = '#microphone-button,.input-button,[id$="-button"],button{min-width:44px;min-height:44px}.input-button{display:inline-flex;align-items:center;justify-content:center}';
  function inject() { var sr = dc.shadowRoot; if (!sr) return setTimeout(inject, 400); if (sr.getElementById('nxfix')) return; var s = document.createElement('style'); s.id = 'nxfix'; s.textContent = css; sr.appendChild(s); }
  inject();
  var st = document.createElement('style');
  st.textContent = '[data-m]{min-height:44px;min-width:44px}#dcSub{max-width:60vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media(max-width:600px){#chat{scroll-padding-top:72px}}';
  document.head.appendChild(st);
  var sub = document.getElementById('dcSub');
  if (sub) { var busy = 0; new MutationObserver(function () { if (busy) return; var t = sub.textContent; if (t.length > 26) { busy = 1; sub.textContent = t.slice(0, 24).trim() + '…'; busy = 0; } }).observe(sub, { childList: true, characterData: true, subtree: true }); }
  function hideIntro() {
    var sr = dc.shadowRoot; if (!sr) return;
    var all = sr.querySelectorAll('*'), hit = null;
    for (var i = 0; i < all.length; i++) { var e = all[i]; if (e.children.length === 0 && /Привет, я NOX/.test(e.textContent || '')) { hit = e; break; } }
    if (!hit) { var ps = sr.querySelectorAll('[id*=intro],[class*=intro]'); ps.forEach(function (p) { p.style.display = 'none'; }); return; }
    var el = hit; while (el.parentElement && el.parentElement !== sr && !/messages|message-container|chat-view/.test((el.parentElement.id || '') + ' ' + (el.parentElement.className || ''))) el = el.parentElement;
    el.style.display = 'none';
  }
  var of = window.fetch;
  window.fetch = function (u) { try { var url = typeof u === 'string' ? u : (u && u.url) || ''; if (url.indexOf('/api/turn') >= 0 && url.indexOf('/stop') < 0 || url.indexOf('/img/generate') >= 0) setTimeout(hideIntro, 150); } catch (e) {} return of.apply(this, arguments); };
  window.NOXdcHideIntro = hideIntro;
})();
