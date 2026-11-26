/* NOX: видимые select -> плитки (>=44px). Нативный select остаётся скрытым и синхронным. Откат ?tiles=0 */
(function () {
  'use strict';
  if (/[?&]tiles=0/.test(location.search)) return;
  var css = document.createElement('style');
  css.textContent = '.nxt{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0}.nxt button{min-height:44px;min-width:44px;padding:8px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.06);color:inherit;font:inherit;cursor:pointer;touch-action:manipulation}.nxt button[aria-pressed=true]{background:rgba(120,160,255,.28);border-color:rgba(160,190,255,.7)}.nxt button:focus-visible{outline:2px solid #9bbcff;outline-offset:2px}select[data-nxt],sl-select[data-nxt]{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important;overflow:hidden}';
  document.head.appendChild(css);
  function opts(s) { return s.tagName === 'SELECT' ? [].map.call(s.options, function (o) { return { v: o.value, t: o.textContent }; }) : [].map.call(s.querySelectorAll('sl-option'), function (o) { return { v: o.value, t: o.textContent.trim() }; }); }
  function visible(s) { var r = s.getBoundingClientRect(); return r.width > 2 && r.height > 2 && getComputedStyle(s).visibility !== 'hidden'; }
  function build(s) {
    if (s.dataset.nxt) return; s.dataset.nxt = '1';
    var box = document.createElement('div'); box.className = 'nxt'; box.setAttribute('role', 'group'); box.setAttribute('aria-label', s.getAttribute('aria-label') || s.getAttribute('label') || 'Выбор');
    s.parentNode.insertBefore(box, s.nextSibling);
    function draw() {
      var os = opts(s); box.textContent = '';
      os.forEach(function (o) { var b = document.createElement('button'); b.type = 'button'; b.textContent = o.t.length > 42 ? o.t.slice(0, 40) + '…' : o.t; b.title = o.t; b.setAttribute('aria-pressed', String(String(s.value) === String(o.v)));
        b.onclick = function () { s.value = o.v; s.dispatchEvent(new Event('change', { bubbles: true })); s.dispatchEvent(new Event('input', { bubbles: true })); if (s.tagName !== 'SELECT') s.dispatchEvent(new CustomEvent('sl-change', { bubbles: true })); draw(); };
        box.appendChild(b); });
    }
    draw(); s.addEventListener('change', draw); new MutationObserver(draw).observe(s, { childList: true, subtree: true });
  }
  function scan() { document.querySelectorAll('select,sl-select').forEach(function (s) { if (!s.dataset.nxt && (visible(s) || s.tagName === 'SELECT')) build(s); }); }
  scan(); var n = 0, iv = setInterval(function () { scan(); if (++n > 20) clearInterval(iv); }, 800);
})();
