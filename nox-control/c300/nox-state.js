/* NOX · живые состояния: window.NOXstate.set('thinking'|'listening'|'speaking'|'joy'|'idle') -> html[data-nox-state], реакция малого чёрного солнца.
   Источники: запросы к /api/chat (думает -> радость при успехе). Озвучка и микрофон выставляют состояние через NOXstate.set. */
(() => {
  if (window.NOXstate) return;
  const root = document.documentElement; let tm = 0;
  const set = (st, ms) => { clearTimeout(tm); root.setAttribute('data-nox-state', st); if (ms) tm = setTimeout(() => root.setAttribute('data-nox-state', 'idle'), ms); };
  window.NOXstate = { set, get: () => root.getAttribute('data-nox-state') || 'idle' };
  set('idle');
  const of = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (/\/api\/chat(\?|$)|\/api\/turn(\?|$)|chat\/completions/.test(url) && init && /post/i.test(init.method || '')) {
      set('thinking');
      return of.apply(this, arguments).then((r) => { set(r.ok ? 'joy' : 'idle', 1800); return r; }, (e) => { set('idle'); throw e; });
    }
    return of.apply(this, arguments);
  };
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && window.NOXstate.get() === 'thinking') set('idle'); });
})();
