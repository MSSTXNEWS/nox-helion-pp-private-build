/* NOX · тема: акцентный цвет и плотность (общие для всех страниц, применяется до отрисовки) */
(function () {
  var g = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var a = g('nox.ui.accent');
  if (a && /^\d{1,3},\d{1,3},\d{1,3}$/.test(a)) document.documentElement.style.setProperty('--cy', a);
  try { var c = JSON.parse(g('nox.wow.cfg') || '{}'); if (c.dens === 'tight') document.addEventListener('DOMContentLoaded', function () { document.body.classList.add('tight'); }); } catch (e) { /* нет настроек */ }
})();
