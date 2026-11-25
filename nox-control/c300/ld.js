/* S3-LOAD: общие скрипты навигации (солнце, пульт, шина команд, действия) подгружаются на страницы, где их нет (music, news, studio, cinema и др.) */
(function () {
  var need = ['nox-state.js', 'nox-cmd.js', 'nox-pult.js', 'nox-sun-x.js', 'nox-actions.js', 'nox-cast-btn.js', 'nox-radial.js', 'nox-live.js', 'nox-gesture.js'];
  function add() { need.forEach(function (n) { if (document.querySelector('script[src*="' + n + '"]')) return; var s = document.createElement('script'); s.src = './' + n + '?v=s3l'; s.async = false; document.head.appendChild(s); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
