/* NOX · мини-чат на каждой странице (V2-05). Один скрипт: <script src="/web/v1n/mini-nox.js" defer>.
   Окно = тот же новый чат (/web/v1n/mini.html), тот же /api/turn, общий диалог (localStorage nox.ab.*). Контекст страницы уходит в ход (поле page). Выключен на chat. */
(() => {
  if (window.__noxMini2 || /\/(chat(-dc)?|v1n\/(index|mini))\.html$|\/v1n\/?$/.test(location.pathname)) return; window.__noxMini2 = 1;
  document.querySelectorAll('.nmc-fab,.nmc').forEach((e) => e.remove());
  const page = (document.title || '').replace(/^NOX HELION\s*·\s*/i, '').trim() || location.pathname.split('/').pop();
  const st = document.createElement('style');
  st.textContent = `.nmx-fab{position:fixed;right:16px;bottom:96px;z-index:9000;width:48px;height:48px;border-radius:50%;display:grid;place-items:center;color:#ffd9a0;cursor:pointer;border:1px solid rgba(255,170,60,.45);background:rgba(10,6,2,.72);backdrop-filter:blur(14px);box-shadow:0 0 18px rgba(255,140,30,.25),inset 0 0 12px rgba(255,170,60,.12);transition:transform .2s,box-shadow .2s}
.nmx-fab:hover,.nmx-fab.on{transform:scale(1.06);box-shadow:0 0 26px rgba(255,150,40,.45)}
.nmx{position:fixed;right:16px;bottom:154px;z-index:9001;width:380px;max-width:calc(100vw - 24px);height:min(540px,calc(100vh - 220px));min-height:300px;display:flex;flex-direction:column;border-radius:18px;overflow:hidden;color:#f3e7d6;border:1px solid rgba(255,170,60,.35);background:rgba(8,5,2,.82);backdrop-filter:blur(22px);box-shadow:0 18px 60px rgba(0,0,0,.6),0 0 30px rgba(255,140,30,.15)}
.nmx[hidden]{display:none}.nmx header{flex:0 0 44px;display:flex;align-items:center;gap:8px;padding:0 6px 0 14px;border-bottom:1px solid rgba(255,170,60,.18);font:600 11px/1 Inter,system-ui,sans-serif;letter-spacing:.2em;text-transform:uppercase}
.nmx header b{color:#ffb347}.nmx header span{flex:1;opacity:.55;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;letter-spacing:.1em}
.nmx header a,.nmx header button{min-width:44px;height:44px;display:grid;place-items:center;background:none;border:0;color:inherit;opacity:.7;cursor:pointer;font:inherit;text-decoration:none}.nmx header a:hover,.nmx header button:hover{opacity:1;color:#ffb347}.nmx header button{font-size:22px}
.nmx iframe{flex:1;min-height:0;width:100%;border:0;background:transparent}
@media(max-width:768px){#nox-m-ai{display:none!important}.nmx-fab{bottom:88px;right:12px}.nmx{right:8px;left:8px;width:auto;bottom:146px;height:min(60vh,520px)}}`;
  document.head.appendChild(st);
  const fab = document.createElement('button'); fab.type = 'button'; fab.className = 'nmx-fab'; fab.setAttribute('aria-label', 'Мини-чат NOX'); fab.title = 'Мини-чат NOX';
  fab.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>';
  const win = document.createElement('section'); win.className = 'nmx'; win.hidden = true; win.setAttribute('aria-label', 'Мини-чат NOX');
  win.innerHTML = '<header><b>NOX</b><span></span><a href="/web/chat-dc.html" title="Открыть полный чат" aria-label="Открыть полный чат">&#8599;</a><button type="button" class="x" aria-label="Закрыть">&times;</button></header>';
  win.querySelector('span').textContent = page;
  const fr = document.createElement('iframe'); fr.title = 'Чат NOX'; win.appendChild(fr);
  document.body.append(fab, win);
  const toggle = (on) => { win.hidden = !on; fab.classList.toggle('on', on); fab.setAttribute('aria-expanded', String(on)); if (on && !fr.src) fr.src = '/web/v1n/mini.html?ctx=' + encodeURIComponent(page) + '&p=' + encodeURIComponent(location.pathname); };
  fab.onclick = () => toggle(win.hidden);
  win.querySelector('.x').onclick = () => toggle(false);
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && !win.hidden) toggle(false); });
})();
