/* NOX · жесты руками (MediaPipe Tasks Vision, Apache-2.0, всё в браузере): ладонь 0,7 с = STOP, щипок = клик по элементу под указательным пальцем, свайп ладонью = соседний раздел меню.
   Включается кнопкой «Жесты» в пульте или переключателем в настройках; по умолчанию выключено, камера не включается без вашего разрешения. */
(() => {
  if (window.NOXgesture) return;
  const V = './vendor/mediapipe-tasks-vision/', MODEL = V + 'hand_landmarker.task';
  let lm = null, vid = null, on = false, raf = 0, last = 0, palmT = 0, prevX = null, prevT = 0, pinchArmed = true, cur = null;
  const toast = (m, bad) => (window.NOXactions ? window.NOXactions.toast(m, bad) : console.log(m));
  const nav = async () => { const d = await fetch('./nav.json').then((r) => r.json()).catch(() => ({ groups: [] })); return d.groups.flatMap((g) => g.items.map((i) => i.file)); };
  const start = async () => {
    try {
      const head = await fetch(MODEL, { method: 'HEAD' }); if (!head.ok) return toast('Жесты: модель hand_landmarker.task не загружена на сервер', 1);
      const m = await import(V + 'vision_bundle.mjs'); const fs = await m.FilesetResolver.forVisionTasks(V + 'wasm');
      lm = await m.HandLandmarker.createFromOptions(fs, { baseOptions: { modelAssetPath: MODEL }, runningMode: 'VIDEO', numHands: 1 });
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
      vid = Object.assign(document.createElement('video'), { srcObject: stream, muted: true, playsInline: true }); await vid.play();
      cur = document.createElement('div'); cur.style.cssText = 'position:fixed;width:22px;height:22px;margin:-11px;border-radius:50%;border:2px solid #e9b465;z-index:2147483000;pointer-events:none;display:none'; document.body.appendChild(cur);
      on = true; localStorage.setItem('nox.gesture', '1'); toast('Жесты включены: ладонь = STOP, щипок = клик, свайп = раздел'); loop();
    } catch (e) { toast('Жесты не включились: ' + (e.name === 'NotAllowedError' ? 'нет доступа к камере' : e.message), 1); on = false; }
  };
  const stop = () => { on = false; cancelAnimationFrame(raf); localStorage.setItem('nox.gesture', '0'); if (vid && vid.srcObject) vid.srcObject.getTracks().forEach((t) => t.stop()); if (cur) cur.remove(); toast('Жесты выключены'); };
  const loop = () => {
    raf = requestAnimationFrame(loop); const now = performance.now(); if (now - last < 90 || vid.readyState < 2) return; last = now;
    const r = lm.detectForVideo(vid, now); const h = r.landmarks && r.landmarks[0];
    if (!h) { cur.style.display = 'none'; palmT = 0; prevX = null; return; }
    const tip = h[8], x = (1 - tip.x) * innerWidth, y = tip.y * innerHeight; cur.style.display = 'block'; cur.style.left = x + 'px'; cur.style.top = y + 'px';
    const open = [8, 12, 16, 20].every((i) => h[i].y < h[i - 2].y) && Math.hypot(h[4].x - h[5].x, h[4].y - h[5].y) > .05;
    const pinch = Math.hypot(h[4].x - h[8].x, h[4].y - h[8].y) < .04;
    if (open) { palmT = palmT || now; if (now - palmT > 700) { palmT = 0; window.NOXcmd ? window.NOXcmd('stop', {}) : toast('STOP: шина не подключена', 1); } } else palmT = 0;
    if (pinch && pinchArmed) { pinchArmed = false; const el = document.elementFromPoint(x, y); if (el) el.click(); } if (!pinch) pinchArmed = true;
    const wx = (1 - h[0].x); if (open && prevX != null && now - prevT < 400) { const dx = wx - prevX; if (Math.abs(dx) > .22) { prevX = null; nav().then((L) => { const here = location.pathname.split('/').pop() || 'index.html', i = L.indexOf(here); if (i >= 0) location.href = L[(i + (dx > 0 ? 1 : -1) + L.length) % L.length]; }); return; } } else if (!open || now - prevT >= 400) { prevX = wx; prevT = now; }
  };
  window.NOXgesture = { toggle: () => (on ? stop() : start()), on: () => on };
  if (localStorage.getItem('nox.gesture') === '1') setTimeout(start, 1500);
  /* переключатель в настройках */
  if (/settings\.html$/.test(location.pathname)) { let n = 0; const t = setInterval(() => { const pl = document.querySelector('#nxmac .nxm-pl'); if (pl || ++n > 30) { clearInterval(t); if (!pl) return; const s = document.createElement('section'); s.className = 'card c12 setg nox-seen'; s.dataset.tab = 'ui'; s.innerHTML = '<h3 class="mono">Жесты руками</h3><div class="nxm-row"><span>Управление жестами (камера, всё в браузере)</span><sl-switch id="nxGest"></sl-switch></div><p class="note">Ладонь 0,7 с — STOP; щипок — клик под пальцем; свайп ладонью — соседний раздел. Модель MediaPipe берётся с сервера (vendor/mediapipe-tasks-vision).</p>'; const cs = document.querySelector('#nxmac [role=tab][aria-selected=true]'); if (cs && cs.dataset.tab !== 'ui') s.classList.add('nxt-off'); pl.appendChild(s); const sw = s.querySelector('#nxGest'); sw.checked = localStorage.getItem('nox.gesture') === '1'; sw.addEventListener('sl-change', () => { if (sw.checked !== on) window.NOXgesture.toggle(); }); } }, 400); }
})();
