/* NOX · мини-чат на каждой странице = тот же Deep Chat (chat-dc.html?mini=1) в окне. Общий диалог nox.wow.cur. CH-DC */
(() => {
  if (window.__noxMini || /(^|\/)chat(-dc)?\.html$/.test(location.pathname)) return; window.__noxMini = 1;
  const page = (document.title || '').replace(/^NOX HELION\s*·\s*/i, '').trim() || location.pathname.split('/').pop();
  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = './nox-minichat.css'; document.head.appendChild(l);
  const fab = document.createElement('button'); fab.type = 'button'; fab.className = 'nmc-fab'; fab.setAttribute('aria-label', 'Диалог с NOX'); fab.title = 'Диалог с NOX';
  fab.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 21 12z"/></svg>';
  const win = document.createElement('section'); win.className = 'nmc'; win.setAttribute('aria-label', 'Диалог с NOX'); win.hidden = true;
  win.style.cssText = 'display:flex;flex-direction:column;padding:0;overflow:hidden';
  win.innerHTML = '<header style="flex:0 0 40px;display:flex;align-items:center;gap:8px;padding:0 10px"><b>NOX</b><span class="nmc-pg" style="flex:1;opacity:.6;font-size:12px"></span><a href="./chat.html" style="font-size:12px;color:inherit">Открыть чат</a><button type="button" class="nmc-x" aria-label="Закрыть">×</button></header>';
  win.querySelector('.nmc-pg').textContent = page;
  const fr = document.createElement('iframe'); fr.title = 'Чат NOX'; fr.style.cssText = 'flex:1;min-height:0;width:100%;border:0;background:transparent'; fr.setAttribute('allow', 'microphone');
  win.appendChild(fr); document.body.append(fab, win);
  const toggle = (on) => { win.hidden = !on; fab.classList.toggle('on', on); if (on && !fr.src) fr.src = './chat-dc.html?mini=1&ctx=' + encodeURIComponent(page); };
  fab.onclick = () => toggle(win.hidden);
  win.querySelector('.nmc-x').onclick = () => toggle(false);
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && !win.hidden) toggle(false); });
})();
