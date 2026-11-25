/* NOX · выбор планеты фона: настоящие 3D-сферы three.js с текстурами Solar System Scope (CC BY 4.0) из vendor/planets/ и vendor/nox-planets/.
   Одна общая WebGL-сцена рисует вращающиеся превью в 2D-канвасы плиток (без десятка контекстов). Нет текстуры планеты — превью берёт цвета её процедурной модели. Выбор сразу меняет фон через space.setPlanet. */
(() => {
  if (window.NOXplanets3d) return;
  const SZ = 112, RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dirs = ['./vendor/planets/', './vendor/nox-planets/'];
  let THREE = null, ren = null, items = [], raf = 0, cur = localStorage.getItem('nox:planet') || 'earth', data = null;
  const ready = async () => {
    if (THREE) return;
    THREE = await import('three'); data = await import('./nox-wow-data.js');
    ren = new THREE.WebGLRenderer({ alpha: true, antialias: true, preserveDrawingBuffer: true }); ren.setSize(SZ, SZ); ren.setPixelRatio(1);
  };
  const loadTex = (names) => new Promise((ok) => {
    const L = new THREE.TextureLoader(); const list = []; dirs.forEach((d) => names.forEach((n) => list.push(d + n)));
    const next = (i) => { if (i >= list.length) return ok(null); L.load(list[i], (t) => { t.colorSpace = THREE.SRGBColorSpace; ok(t); }, undefined, () => next(i + 1)); }; next(0);
  });
  const rgb = (a) => a.map((x) => Math.round(x * 255));
  const build = async (p) => {
    const sc = new THREE.Scene(); const cam = new THREE.PerspectiveCamera(30, 1, .1, 20); cam.position.set(0, 0, p.ring ? 4.6 : 3.4);
    sc.add(new THREE.AmbientLight(0xffffff, .35)); const sun = new THREE.DirectionalLight(0xfff2dd, 2.6); sun.position.set(-3, 1.5, 3); sc.add(sun);
    let map = p.tex ? await loadTex(p.tex) : null, mat;
    if (map) mat = new THREE.MeshStandardMaterial({ map, roughness: .95, metalness: 0 });
    else { const pr = p.proc || { base: [.2, .2, .3], hi: [.5, .5, .6] }, c = document.createElement('canvas'); c.width = 256; c.height = 128; const g = c.getContext('2d'); const gr = g.createLinearGradient(0, 0, 0, 128);
      for (let i = 0; i <= 8; i++) { const k = pr.band ? (Math.sin(i * 1.7) * .5 + .5) * pr.band : .5 * i / 8; const m = (a, b) => Math.round((a[0] * (1 - k) + b[0] * k) * 255) + ',' + Math.round((a[1] * (1 - k) + b[1] * k) * 255) + ',' + Math.round((a[2] * (1 - k) + b[2] * k) * 255); gr.addColorStop(i / 8, 'rgb(' + m(pr.base, pr.hi) + ')'); }
      g.fillStyle = gr; g.fillRect(0, 0, 256, 128); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; mat = new THREE.MeshStandardMaterial({ map: t, roughness: .9 }); }
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), mat); mesh.rotation.z = p.ring ? .45 : .2; sc.add(mesh);
    if (p.atm) { const a = new THREE.Mesh(new THREE.SphereGeometry(1.06, 48, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color(...p.atm), transparent: true, opacity: .09 * (p.atmK || .5), side: THREE.BackSide })); sc.add(a); }
    if (p.ring) { const rt = await loadTex([p.ring]); const r = new THREE.Mesh(new THREE.RingGeometry(1.35, 2.2, 96), new THREE.MeshBasicMaterial({ color: 0xd9c9a2, map: rt || null, transparent: true, opacity: rt ? 1 : .45, side: THREE.DoubleSide })); r.rotation.x = Math.PI / 2.1; r.rotation.y = .1; mesh.add(r); }
    return { sc, cam, mesh, textured: !!map };
  };
  const frame = () => {
    raf = requestAnimationFrame(frame);
    items.forEach((it) => { if (!it.vis) return; it.o.mesh.rotation.y += .006; ren.render(it.o.sc, it.o.cam); it.ctx.clearRect(0, 0, SZ, SZ); it.ctx.drawImage(ren.domElement, 0, 0); });
  };
  const widget = () => {
    const el = document.createElement('div'); el.className = 'nxpl'; el.setAttribute('role', 'radiogroup'); el.setAttribute('aria-label', 'Планета фона');
    el.innerHTML = '<div class="nxpl-g"></div><p class="note nxpl-n"></p>';
    const g = el.querySelector('.nxpl-g'), note = el.querySelector('.nxpl-n');
    (async () => {
      await ready(); const P = data.PLANETS.filter((p) => p.id !== 'none');
      const none = data.PLANETS.find((p) => p.id === 'none');
      g.innerHTML = P.map((p) => '<button type="button" role="radio" data-id="' + p.id + '" aria-checked="' + (p.id === cur) + '"><canvas width="' + SZ + '" height="' + SZ + '"></canvas><span>' + p.name + '</span></button>').join('') + (none ? '<button type="button" role="radio" data-id="none" aria-checked="' + (cur === 'none') + '" class="nxpl-none"><i></i><span>' + none.name + '</span></button>' : '');
      let tex = 0;
      const io = new IntersectionObserver((es) => es.forEach((e) => { const it = items.find((x) => x.btn === e.target); if (it) it.vis = e.isIntersecting; }), { threshold: .1 });
      for (const p of P) { const btn = g.querySelector('[data-id="' + p.id + '"]'), o = await build(p); if (o.textured) tex++; const it = { btn, o, ctx: btn.querySelector('canvas').getContext('2d'), vis: true }; items.push(it); io.observe(btn); ren.render(o.sc, o.cam); it.ctx.drawImage(ren.domElement, 0, 0); }
      note.textContent = tex + ' из ' + P.length + ' планет с фото-текстурами Solar System Scope (CC BY 4.0); остальным нужны файлы в vendor/planets.';
      if (!RM && !raf) frame();
    })();
    g.addEventListener('click', async (e) => {
      const b = e.target.closest('button[data-id]'); if (!b) return; const id = b.dataset.id; cur = id; localStorage.setItem('nox:planet', id);
      g.querySelectorAll('button').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
      if (window.gsap) window.gsap.fromTo(b, { scale: .92 }, { scale: 1, duration: .5, ease: 'elastic.out(1,.5)', clearProps: 'transform' });
      try { const s = await (await import('./nox-nav.js')).space; if (s && s.setPlanet) await s.setPlanet(id); } catch (err) { note.textContent = 'Фон не переключился: ' + err.message; }
    });
    return el;
  };
  window.NOXplanets3d = { widget };
  const f = location.pathname.split('/').pop();
  if (f === 'scene.html') setTimeout(() => {
    if (document.getElementById('nxplscene')) return;
    const host = document.querySelector('.wrap'); if (!host) return;
    const card = document.createElement('section'); card.className = 'card nox-seen nxs-glass'; card.id = 'nxplscene'; card.innerHTML = '<h2>Планета фона</h2>'; card.appendChild(widget());
    const first = host.querySelector('.card'); host.insertBefore(card, first ? first.nextSibling : null);
  }, 900);
})();
