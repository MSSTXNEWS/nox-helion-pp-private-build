/* NOX · BlackSun: единое лёгкое «чёрное солнце» (canvas 2D, без WebGL). Чёрный диск, тонкий раскалённый обод, ореол пересвета,
   мерцающая корона, дыхание обода, редкая вспышка по ободу. Состояние: один общий опрос /api/nox-live на страницу.
   API: window.NoxBS.mount(host,{size}) -> {destroy}; window.NoxBS.state. ECO/reduced-motion: статичное свечение. */
(() => {
  if (window.NoxBS) return;
  const S = { busy: false, train: false, night: false, offline: false, err: false, bt: 0 };
  const insts = new Set(); let raf = 0, lastT = 0, polling = false;
  const eco = () => document.documentElement.dataset.q === "eco" || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const nightNow = () => { const h = new Date().getHours(); return h >= 23 || h < 6; };
  const apply = (j, ok) => { S.offline = !ok; S.err = !!(j && (j.error || j.status === "error")); S.night = nightNow();
    S.train = !!(j && (j.training === true || j.train_running === true || j.training_running === true || (j.training && (j.training.running === true || /TRAIN/i.test(String(j.training.status || ""))))));
    if (j && j.live_turn) S.bt = performance.now() + 3000; draw1(); };
  const poll = () => { fetch("/api/nox-live", { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject())).then((j) => apply(j, true)).catch(() => apply(null, false)); };
  const startPoll = () => { if (polling) return; polling = true; poll(); setInterval(() => { if (!document.hidden) poll(); }, 8000); };
  ["nox-token", "nox-think"].forEach((n) => addEventListener(n, () => { S.bt = performance.now() + 2500; }));
  const hash = (n) => { const s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); };
  const vn = (x) => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return hash(i) * (1 - u) + hash(i + 1) * u; };
  function render(I, t) {
    const c = I.c, g = I.g, W = c.width, d = I.dpr, size = I.size, cx = W / 2, r = size * 0.36 * d;
    g.clearRect(0, 0, W, W);
    const busy = S.busy || performance.now() < S.bt, sp = busy ? 1.9 : 1, dim = S.err ? 0.7 : S.offline || S.night ? 0.45 : 1, br = dim * (busy ? 1.25 : 1);
    const gray = S.err; const col = (a, k) => gray ? `rgba(${150 * k | 0},${150 * k | 0},${158 * k | 0},${a})` : `rgba(255,${(120 + 60 * k) | 0},${(24 + 50 * k) | 0},${a})`;
    const breath = 0.78 + 0.22 * Math.sin((t * sp * 2 * Math.PI) / 3.2), still = I.still;
    const b = still ? 0.9 : breath;
    g.globalCompositeOperation = "lighter";
    /* ореол пересвета: несколько слоёв */
    [[3.1, 0.2], [2.2, 0.3], [1.5, 0.45]].forEach(([k, a]) => { const gr = g.createRadialGradient(cx, cx, r * 0.9, cx, cx, r * k); gr.addColorStop(0, col(a * br * b, 0.8)); gr.addColorStop(0.45, col(a * 0.35 * br * b, 0.3)); gr.addColorStop(1, col(0, 0)); g.fillStyle = gr; g.beginPath(); g.arc(cx, cx, r * k, 0, 6.2832); g.fill(); });
    /* корона: лучи с шумовым мерцанием */
    const n = size > 90 ? 56 : size > 40 ? 36 : 20, flick = still ? 0.5 : 1;
    for (let k = 0; k < n; k++) { const a = (k / n) * 6.2832 + 0.37 * hash(k), q = vn(k * 1.7 + t * 0.9 * sp * flick) * 0.6 + vn(k * 3.1 - t * 1.6 * sp * flick) * 0.4, len = r * (0.12 + 0.5 * q * q * 1.6), w = (r * 0.09) * (0.6 + q);
      const x0 = cx + Math.cos(a) * r * 0.99, y0 = cx + Math.sin(a) * r * 0.99, x1 = cx + Math.cos(a) * (r + len), y1 = cx + Math.sin(a) * (r + len), nx = -Math.sin(a) * w, ny = Math.cos(a) * w;
      const gr = g.createLinearGradient(x0, y0, x1, y1); gr.addColorStop(0, col(0.55 * br * (0.4 + q), 1)); gr.addColorStop(1, col(0, 0)); g.fillStyle = gr; g.beginPath(); g.moveTo(x0 + nx, y0 + ny); g.lineTo(x1, y1); g.lineTo(x0 - nx, y0 - ny); g.closePath(); g.fill(); }
    /* вспышка-протуберанец */
    if (!still && t > I.fl.at && t < I.fl.at + 1.4) { const p = (t - I.fl.at) / 1.4, e = Math.sin(p * Math.PI); const a = I.fl.a + p * 2.2; const x1 = cx + Math.cos(a) * (r + r * 0.7 * e), y1 = cx + Math.sin(a) * (r + r * 0.7 * e);
      const gr = g.createRadialGradient(cx + Math.cos(a) * r, cx + Math.sin(a) * r, 0, x1, y1, r * 0.5 * e + 1); gr.addColorStop(0, col(0.9 * br * e, 1)); gr.addColorStop(1, col(0, 0)); g.fillStyle = gr; g.beginPath(); g.arc(x1, y1, r * 0.5 * e + 1, 0, 6.2832); g.fill(); }
    else if (!still && t > I.fl.at + 1.4) { I.fl = { at: t + 10 + Math.random() * 10, a: Math.random() * 6.2832 }; }
    /* обод: широкое свечение + тонкая раскалённая линия */
    g.globalCompositeOperation = "source-over";
    const lw = Math.max(1, r * 0.055);
    g.lineCap = "round"; g.strokeStyle = col(0.22 * br * b, 0.8); g.lineWidth = lw * 5; g.beginPath(); g.arc(cx, cx, r + lw * 0.5, 0, 6.2832); g.stroke();
    g.strokeStyle = col(0.45 * br * b, 0.9); g.lineWidth = lw * 2.2; g.beginPath(); g.arc(cx, cx, r + lw * 0.3, 0, 6.2832); g.stroke();
    /* чёрный диск */
    g.fillStyle = "#000"; g.beginPath(); g.arc(cx, cx, r, 0, 6.2832); g.fill();
    g.strokeStyle = gray ? "rgba(170,170,176,.85)" : `rgba(255,${(175 + 60 * b) | 0},${(90 + 80 * b) | 0},${Math.min(1, 0.95 * br)})`; g.lineWidth = lw; g.beginPath(); g.arc(cx, cx, r + lw * 0.1, 0, 6.2832); g.stroke();
    /* бегущая волна (обучение) и «бегущий блик» вспышки */
    const ws = [];
    if (S.train && !S.err) ws.push([t * 2.6 / 1, 1.2, 0.95]);
    if (!still && t > I.fl.at - 0.01 && t < I.fl.at + 1.4) ws.push([I.fl.a + ((t - I.fl.at) / 1.4) * 6.2832, 0.8, 1]);
    ws.forEach(([a, span, al]) => { g.strokeStyle = `rgba(255,236,200,${al * br})`; g.lineWidth = lw * 1.3; g.beginPath(); g.arc(cx, cx, r + lw * 0.1, a - span / 2, a + span / 2); g.stroke(); });
  }
  function draw1() { insts.forEach((I) => { if (I.still || !raf) render(I, I.still ? 5 : performance.now() / 1000); }); }
  function loop(ts) { raf = requestAnimationFrame(loop); if (ts - lastT < 33) return; lastT = ts; const t = ts / 1000; insts.forEach((I) => { if (I.vis) render(I, t); }); }
  function mount(host, o) {
    o = o || {}; const I = { host, size: 0, dpr: 1, vis: true, still: eco(), fl: { at: 4 + Math.random() * 8, a: Math.random() * 6.2832 } };
    const c = document.createElement("canvas"); c.setAttribute("aria-hidden", "true"); c.style.cssText = "position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);pointer-events:none;max-width:none"; I.c = c; I.g = c.getContext("2d");
    if (getComputedStyle(host).position === "static") host.style.position = "relative"; host.appendChild(c);
    const fit = () => { const s = Math.max(24, Math.min(o.max || 200, o.size || host.clientWidth || 48)); I.size = s; I.dpr = Math.min(2, window.devicePixelRatio || 1); const side = Math.round(s * 1.9); c.style.width = side + "px"; c.style.height = side + "px"; c.width = Math.round(side * I.dpr); c.height = c.width; render(I, I.still ? 5 : performance.now() / 1000); };
    fit(); const ro = window.ResizeObserver ? new ResizeObserver(fit) : null; ro && ro.observe(host);
    const io = window.IntersectionObserver ? new IntersectionObserver((e) => { I.vis = e[0].isIntersecting; }) : null; io && io.observe(host);
    const mo = new MutationObserver(() => { I.still = eco(); fit(); }); mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-q"] });
    insts.add(I); startPoll(); if (!raf && !I.still) raf = requestAnimationFrame(loop);
    if (!I.still && !raf) raf = requestAnimationFrame(loop);
    return { destroy() { insts.delete(I); ro && ro.disconnect(); io && io.disconnect(); mo.disconnect(); c.remove(); if (!insts.size && raf) { cancelAnimationFrame(raf); raf = 0; } } };
  }
  window.NoxBS = { mount, state: S };
})();
