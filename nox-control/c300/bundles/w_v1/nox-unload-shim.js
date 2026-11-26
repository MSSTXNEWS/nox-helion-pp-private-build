/* unload запрещён Permissions-Policy: переводим подписки на pagehide. Подключать ПЕРВЫМ. Откат ?w2=0 */
(function () {
  'use strict';
  if (/[?&]w2=0/.test(location.search)) return;
  var add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (t, f, o) { if (t === 'unload' && (this === window || this === document)) t = 'pagehide'; return add.call(this, t, f, o); };
  try { Object.defineProperty(window, 'onunload', { set: function (f) { add.call(window, 'pagehide', f); }, get: function () { return null; }, configurable: true }); } catch (e) {}
})();
