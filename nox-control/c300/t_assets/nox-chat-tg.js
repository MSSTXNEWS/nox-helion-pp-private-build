/* nox-chat-tg.js (исполнитель T): «/» открывает команды, кнопки ⌘ и режима у поля. Логику отправки не трогает. */
(function () {
  const input = document.getElementById('input');
  const dlg = document.getElementById('dlPalette');
  const palInput = document.getElementById('palInput');
  const composer = document.getElementById('composer');
  const modes = document.getElementById('modes');
  if (!input || !dlg || !composer || !modes) return;

  function openPalette() {
    try { dlg.show(); } catch (e) { dlg.setAttribute('open', ''); }
    setTimeout(() => { if (palInput) { palInput.value = ''; palInput.focus(); palInput.dispatchEvent(new Event('input')); } }, 60);
  }
  input.addEventListener('input', () => {
    if (input.value === '/') { input.value = ''; openPalette(); }
  });

  const btnMic = document.getElementById('btnMic');
  const mk = (cls, html, title, onClick) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tg-btn ' + cls; b.title = title; b.setAttribute('aria-label', title);
    b.innerHTML = html; b.addEventListener('click', onClick);
    return b;
  };
  const LABEL = { auto: 'А', fast: 'Б', deep: 'Г' };
  const modeBtn = mk('mode', 'А', 'Режим ответа: авто / быстро / глубоко', () => {
    const list = Array.from(modes.querySelectorAll('button[data-m]'));
    if (!list.length) return;
    const cur = list.findIndex((b) => b.matches('[aria-checked="true"],[aria-pressed="true"],.on,.active,.sel'));
    const next = list[(cur + 1) % list.length];
    next.click();
    setTimeout(sync, 30);
  });
  function sync() {
    const cur = modes.querySelector('button[data-m][aria-checked="true"],button[data-m][aria-pressed="true"],button[data-m].on,button[data-m].active,button[data-m].sel');
    if (cur) { const k = cur.dataset.m; modeBtn.textContent = LABEL[k] || k[0].toUpperCase(); modeBtn.title = 'Режим: ' + cur.textContent.trim(); }
  }
  const cmdBtn = mk('cmd', '⌘', 'Команды (Ctrl+K)', () => {
    const b = document.getElementById('btnPalette');
    if (b) b.click(); else openPalette();
  });
  if (btnMic && btnMic.parentNode) {
    btnMic.parentNode.insertBefore(modeBtn, btnMic);
    btnMic.parentNode.insertBefore(cmdBtn, btnMic);
  } else {
    composer.appendChild(cmdBtn); composer.appendChild(modeBtn);
  }
  new MutationObserver(sync).observe(modes, { subtree: true, attributes: true });
  sync();
})();
