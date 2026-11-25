/* NOX · тема: «Графит» (по умолчанию) / «Солнце» (классика), акцент и плотность. Применяется до отрисовки, без мигания. TH-GRAPHITE */
(function () {
  var g = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var d = document.documentElement;
  var q = (location.search.match(/[?&]theme=(graphite|sun)/) || [])[1];
  if (q) { try { localStorage.setItem('nox.ui.theme', q); } catch (e) { /* без хранилища */ } }
  var th = q || g('nox.ui.theme'); if (th !== 'sun') th = 'graphite';
  d.setAttribute('data-nox-theme', th);
  window.NOXtheme = { get: function () { return d.getAttribute('data-nox-theme'); }, set: function (t) { try { localStorage.setItem('nox.ui.theme', t); } catch (e) { /* */ } location.reload(); } };
  (function () { var s0 = document.currentScript, b0 = s0 && s0.src ? s0.src.replace(/[^\/]*$/, '') : './'; if (document.readyState === 'loading') document.write('<link rel="stylesheet" href="' + b0 + 'nox-th-fix.css?v=th5" data-nox-thfix>'); })();
  if (th === 'graphite') {
    var s = document.currentScript, base = s && s.src ? s.src.replace(/[^\/]*$/, '') : './';
    var fs = ['nox-graphite-map.css?v=th5', 'nox-graphite.css?v=th5'];
    if (document.readyState === 'loading') { fs.forEach(function (f) { document.write('<link rel="stylesheet" href="' + base + f + '" data-nox-graphite>'); }); document.write('<script src="' + base + 'nox-icons.js?v=th5"><\/script>'); }
    else fs.forEach(function (f) { var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = base + f; document.head.appendChild(l); });
  }
  var a = g('nox.ui.accent');
  if (a && /^\d{1,3},\d{1,3},\d{1,3}$/.test(a)) d.style.setProperty('--cy', a);
  try { var c = JSON.parse(g('nox.wow.cfg') || '{}'); if (c.dens === 'tight') document.addEventListener('DOMContentLoaded', function () { document.body.classList.add('tight'); }); } catch (e) { /* нет настроек */ }
})();

/* Переключатель темы: карточка «Тема» на странице настроек (вставляется в сетку рядом с «Планета фона») */
(function () {
  var d = document.documentElement;
  function build() {
    if (document.getElementById('nox-theme-card')) return true;
    var pl = document.getElementById('planets'); var host = pl && (pl.closest('section') || pl.parentNode);
    if (!host || !host.parentNode) return false;
    var cur = d.getAttribute('data-nox-theme');
    var sec = document.createElement('section'); sec.id = 'nox-theme-card'; sec.className = 'card c12 setg nox-seen'; sec.setAttribute('data-tab', 'ui');
    sec.innerHTML = '<h3 class="mono">Тема</h3><div class="nxth-row" role="radiogroup" aria-label="Тема">'
      + '<button type="button" role="radio" data-th="graphite" aria-checked="' + (cur === 'graphite') + '"><span class="nxth-sw nxth-g"></span><b>Графит</b><small>нейтральный серый, по умолчанию</small></button>'
      + '<button type="button" role="radio" data-th="sun" aria-checked="' + (cur === 'sun') + '"><span class="nxth-sw nxth-s"></span><b>Солнце (классика)</b><small>огненная планета и корона</small></button></div>'
      + '<p class="note mono">Планета фона, палитра сцены и мир интерфейса действуют в теме «Солнце».</p>';
    host.parentNode.insertBefore(sec, host.parentNode.firstChild);
    sec.addEventListener('click', function (e) { var b = e.target.closest('button[data-th]'); if (b && b.dataset.th !== d.getAttribute('data-nox-theme')) window.NOXtheme.set(b.dataset.th); });
    return true;
  }
  var st = document.createElement('style');
  st.textContent = '#nox-theme-card .nxth-row{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}#nox-theme-card button{display:grid;grid-template-columns:44px 1fr;grid-template-rows:auto auto;column-gap:12px;align-items:center;text-align:left;min-width:240px;padding:12px 14px;border:1px solid rgba(255,255,255,.14);border-radius:12px;background:rgba(255,255,255,.04);color:inherit}#nox-theme-card button .nxth-sw{grid-row:1/3;width:44px;height:44px;border-radius:10px;border:1px solid rgba(255,255,255,.18)}#nox-theme-card .nxth-g{background:radial-gradient(circle at 30% 20%,#3a3d43,#17181b 70%)}#nox-theme-card .nxth-s{background:radial-gradient(circle at 50% 60%,#e0654a,#3a1208 70%)}#nox-theme-card button small{opacity:.65;font-size:12px}#nox-theme-card button[aria-checked=true]{border-color:rgba(157,177,209,.8);box-shadow:0 0 0 3px rgba(157,177,209,.18)}';
  document.addEventListener('DOMContentLoaded', function () {
    document.head.appendChild(st);
    if (!document.querySelector('body[data-page=set]')) return;
    var n = 0, t = setInterval(function () { if (build() || ++n > 40) clearInterval(t); }, 250);
  });
})();
