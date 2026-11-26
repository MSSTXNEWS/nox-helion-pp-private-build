/* цели 44 px слоем CSS на intents/cinema/index. Откат ?t44=0 */
(function () {
  'use strict';
  if (/[?&]t44=0/.test(location.search)) return;
  var p = location.pathname, s = document.createElement('style'), g;
  if (/intents|cinema/.test(p)) g = 'html body button,html body [role=button],html body summary,html body input:not([type=hidden]),html body select,html body a[class],html body a[role=button]';
  else if (/(^\/web\/?$|index)/.test(p) || p === '/') g = 'html body header a,html body header button,html body nav a,html body nav button,html body [class^=tb-],html body [class*=" tb-"],html body [id^=tb]';
  else return;
  s.textContent = g.split(',').map(function (x) { return x + '{min-height:44px!important}'; }).join('') + 'html body header a,html body nav a,html body [class^=tb-],html body [class*=" tb-"]{display:inline-flex;align-items:center;justify-content:center;min-width:44px}';
  document.head.appendChild(s);
})();
