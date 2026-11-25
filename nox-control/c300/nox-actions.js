/* NOX · действия меню и пульта без серверного бэкенда: громкость, концентрация, уведомления, тема/мир, трансляция на экран.
   Это клиентские функции (хранятся в localStorage и применяются на странице); серверные команды (STOP, статус, поиск) идут через NOXcmd. Реестр: window.NOXactions.list. */
(() => {
  if (window.NOXactions) return;
  const LS = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const SV = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* нет хранилища */ } };
  const toast = (msg, bad) => { const d = document.createElement('div'); d.textContent = msg; d.style.cssText = 'position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:2147483600;padding:10px 18px;border-radius:14px;font:300 12px/1.3 inherit;color:#efe6df;background:rgba(16,13,13,.78);border:1px solid ' + (bad ? '#c0392b' : 'rgba(255,255,255,.16)') + ';-webkit-backdrop-filter:blur(20px);backdrop-filter:blur(20px)'; document.body.appendChild(d); setTimeout(() => d.remove(), 2800); };
  const media = () => [...document.querySelectorAll('video,audio')];
  /* --- громкость --- */
  const vol = (v) => { v = Math.max(0, Math.min(1, v)); SV('nox.volume', String(v)); media().forEach((m) => { m.volume = v; }); document.documentElement.style.setProperty('--nox-volume', v); toast('Громкость: ' + Math.round(v * 100) + '%'); };
  addEventListener('play', (e) => { if (e.target && e.target.volume != null) e.target.volume = parseFloat(LS('nox.volume', '1')); }, true);
  /* --- концентрация: прячем лишнее, оставляем содержимое --- */
  const focus = (on) => { document.documentElement.toggleAttribute('data-nox-focus', on); SV('nox.focus', on ? '1' : '0'); toast(on ? 'Режим концентрации включён' : 'Режим концентрации выключен'); };
  if (LS('nox.focus', '0') === '1') document.documentElement.setAttribute('data-nox-focus', '');
  const st = document.createElement('style'); st.textContent = 'html[data-nox-focus] #nxdock,html[data-nox-focus] #nxnavx,html[data-nox-focus] .nxd-bar,html[data-nox-focus] #nxminichat{opacity:.12;transition:opacity .3s}html[data-nox-focus] #nxdock:hover,html[data-nox-focus] #nxnavx:hover{opacity:1}'; document.head.appendChild(st);
  /* --- уведомления --- */
  const notif = async () => { if (!('Notification' in window)) return toast('Браузер не поддерживает уведомления', 1); const r = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission; toast(r === 'granted' ? 'Уведомления разрешены' : 'Уведомления запрещены в браузере', r !== 'granted'); if (r === 'granted') new Notification('NOX HELION', { body: 'Уведомления включены' }); };
  /* --- полный экран / второй экран / трансляция --- */
  const full = () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen().catch(() => toast('Полный экран недоступен', 1)); };
  const second = async () => {
    const w = window.open(location.href, 'nox-second', 'popup,width=1280,height=720'); if (!w) return toast('Браузер заблокировал второе окно', 1);
    let ok = false; try { if (window.getScreenDetails) { const d = await getScreenDetails(); const s = d.screens.find((x) => x !== d.currentScreen); if (s) { w.moveTo(s.availLeft, s.availTop); w.resizeTo(s.availWidth, s.availHeight); ok = true; } } } catch (e) { /* без разрешения на экраны */ }
    toast(ok ? 'Второй экран открыт на другом мониторе' : 'Второе окно открыто: перетащите на экран и нажмите F11');
  };
  const cast = async () => {
    const v = media().find((m) => !m.paused) || media()[0];
    if (v && v.remote && v.remote.prompt) { try { await v.remote.prompt(); toast('Выберите устройство для плеера'); return; } catch (e) { /* падаем на Presentation */ } }
    if (window.PresentationRequest) { try { const req = new PresentationRequest([location.href]); const c = await req.start(); toast('Подключено: ' + (c.state || 'ожидание')); c.onstatechange = () => toast('Трансляция: ' + c.state); return; } catch (e) { toast('Трансляция: устройство не выбрано или недоступно (' + (e.name || 'ошибка') + ')', 1); return; } }
    toast('Этот браузер не умеет транслировать: используйте «Второй экран» или Cast из меню Chrome', 1);
  };
  const A = [
    ['vol.up', 'Громче', 'volume', 'громкость звук плюс увеличить громче', () => vol(parseFloat(LS('nox.volume', '1')) + .1)],
    ['vol.down', 'Тише', 'volume-2', 'громкость звук минус уменьшить тише', () => vol(parseFloat(LS('nox.volume', '1')) - .1)],
    ['vol.mute', 'Без звука', 'volume-off', 'выключить звук mute тихо', () => vol(0)],
    ['focus', 'Режим концентрации', 'focus-2', 'концентрация фокус не отвлекаться тишина', () => focus(!document.documentElement.hasAttribute('data-nox-focus'))],
    ['notify', 'Включить уведомления', 'bell', 'уведомления оповещения пуш разрешить', notif],
    ['cast', 'Транслировать на экран', 'cast', 'проектор тв телевизор трансляция экран cast показать', cast],
    ['second', 'Второй экран', 'devices-2', 'проектор второй монитор окно презентация', second],
    ['full', 'Полный экран', 'maximize', 'полноэкранный режим full screen', full],
    ['world.helion', 'Мир HELION', 'sun', 'тема мир helion золото', () => window.NOXworlds && (localStorage.setItem('nox.world', 'helion'), NOXworlds.apply())],
    ['world.chronos', 'Мир CHRONOS', 'clock', 'тема мир chronos латунь', () => window.NOXworlds && (localStorage.setItem('nox.world', 'chronos'), NOXworlds.apply())],
    ['world.somnium', 'Мир SOMNIUM', 'moon', 'тема мир somnium перламутр', () => window.NOXworlds && (localStorage.setItem('nox.world', 'somnium'), NOXworlds.apply())],
    ['world.forge', 'Мир FORGE', 'flame', 'тема мир forge металл жар', () => window.NOXworlds && (localStorage.setItem('nox.world', 'forge'), NOXworlds.apply())],
    ['world.synapse', 'Мир SYNAPSE', 'topology-star-3', 'тема мир synapse мембрана', () => window.NOXworlds && (localStorage.setItem('nox.world', 'synapse'), NOXworlds.apply())]
  ];
  window.NOXactions = { list: A.map(([id, title, icon, syn, run]) => ({ id, title, icon, syn, run })), vol, focus, cast, second, full, notif, toast };
  const v = parseFloat(LS('nox.volume', '1')); document.documentElement.style.setProperty('--nox-volume', v);
})();
