/* UX: плавающие кнопки K4/K6 (#k4-fab) -> одна кнопка-меню «Ещё» на sl-dropdown справа внизу, над мини-чатом.
   Оригинальные кнопки остаются в DOM (скрыты) и получают click из пунктов меню. STOP виден только при body.nox-busy. Цвета - CSS-переменные темы. */
(function () {
  if (window.NOXFabMenu) return;
  var css = document.createElement('style'); css.id = 'ux-fab-css';
  css.textContent = '#k4-fab{display:none!important}'
    + '#ux-fab{position:fixed;right:12px;bottom:calc(var(--ds-dock-h,92px) + var(--ds-safe-b,0px) + 132px);z-index:var(--z-float,800)}'
    + '#ux-fab[hidden]{display:none}'
    + '#ux-fab .ux-t::part(base){min-width:44px;min-height:44px;border-radius:50%;background:var(--gx-3,rgba(24,25,27,.9));color:var(--gx-12,#eceef0);border:1px solid var(--gx-6,rgba(255,255,255,.18));font-size:22px}'
    + '#ux-fab .ux-t::part(base):hover{border-color:var(--gx-8,#9db1d1)}'
    + '#ux-fab .ux-t:focus-visible::part(base){outline:2px solid var(--gx-9,#9db1d1);outline-offset:2px}'
    + '#ux-fab sl-menu{min-width:200px;background:var(--gx-2,#17181a);border:1px solid var(--gx-6,rgba(255,255,255,.18))}'
    + '#ux-fab sl-menu-item{min-height:44px}'
    + 'body:not(.nox-busy) #dkStop,body:not(.nox-busy) .nxd-stop{display:none!important}'
    + '@media(max-width:700px){#ux-fab{bottom:calc(var(--ds-dock-h,92px) + var(--ds-safe-b,0px) + 150px)}}';
  document.head.appendChild(css);
  var box = null, menu = null;
  function build() {
    box = document.createElement('div'); box.id = 'ux-fab'; box.hidden = true;
    box.innerHTML = '<sl-dropdown placement="top-end" distance="8"><sl-icon-button slot="trigger" class="ux-t" library="tabler" name="dots" label="Ещё: инструменты NOX" aria-haspopup="menu"></sl-icon-button><sl-menu aria-label="Инструменты NOX"></sl-menu></sl-dropdown>';
    document.body.appendChild(box); menu = box.querySelector('sl-menu');
    menu.addEventListener('sl-select', function (e) { var b = document.getElementById(e.detail.item.dataset.src); if (b) b.click(); });
  }
  function sync() {
    var src = document.getElementById('k4-fab'); if (!src) return;
    if (!box) build();
    var have = {}; [].forEach.call(menu.children, function (m) { have[m.dataset.src] = 1; });
    [].forEach.call(src.querySelectorAll('button[id]'), function (b) {
      if (have[b.id]) return;
      var ic = b.querySelector('sl-icon'), it = document.createElement('sl-menu-item');
      it.dataset.src = b.id; it.textContent = b.getAttribute('aria-label') || b.id;
      if (ic) { var p = document.createElement('sl-icon'); p.slot = 'prefix'; p.library = 'tabler'; p.name = ic.getAttribute('name'); it.prepend(p); }
      menu.appendChild(it);
    });
    box.hidden = !menu.children.length;
  }
  window.NOXFabMenu = { sync: sync };
  var mo = new MutationObserver(function () { if (document.getElementById('k4-fab')) sync(); });
  function start() { mo.observe(document.body, { childList: true, subtree: true }); sync(); }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
