/* NOX UI source-first adapter, original FORMWORK AURUM gold-dust renderer.
   Original repo: https://github.com/shellcat-com/formwork-aurum
   Original Git blob: 82595dea5ae57e7abd6fe2dccbbec24d71c8d28a; MIT license in aurum-dust.LICENSE.
   Only DOM target and visibility/FX gating changed. No synthetic telemetry. */
(()=>{'use strict';
 const hero=document.getElementById('universe');
 if(!hero)return;
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches||document.body.dataset.fx==='ECO';
  /* ---------- gold dust field ---------- */
  const canvas = document.getElementById('nox-aurum-dust');
  const ctx = canvas && canvas.getContext ? canvas.getContext('2d') : null;

  if (ctx && !reduce) {
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    let W = 0, H = 0, motes = [];
    const GOLD = [
      [246, 229, 166],  // light gold
      [217, 189, 122],  // gold
      [201, 161, 74],   // mid gold
      [255, 248, 227]   // near-white spark
    ];

    function build() {
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // density scaled to area, capped so it stays light on any screen
      const count = Math.min(170, Math.round((W * H) / 10500));
      motes = new Array(count).fill(0).map(spawn);
    }
    function spawn() {
      const c = GOLD[(Math.random() * GOLD.length) | 0];
      const spark = Math.random() < 0.12;
      return {
        x: Math.random() * W,
        y: Math.random() * H,
        r: spark ? 0.6 + Math.random() * 1.1 : 0.4 + Math.random() * 1.8,
        vx: (Math.random() - 0.5) * 0.14,
        vy: -0.05 - Math.random() * 0.22,          // slow, upward drift
        a: 0.12 + Math.random() * 0.4,
        tw: Math.random() * Math.PI * 2,            // twinkle phase
        ts: 0.004 + Math.random() * 0.012,          // twinkle speed
        c, spark
      };
    }

    function draw() {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      for (const m of motes) {
        m.x += m.vx; m.y += m.vy; m.tw += m.ts;
        // wrap
        if (m.y < -6) { m.y = H + 6; m.x = Math.random() * W; }
        if (m.x < -6) m.x = W + 6; else if (m.x > W + 6) m.x = -6;

        const flick = 0.55 + 0.45 * Math.sin(m.tw);
        const alpha = m.a * flick;
        const glow = m.r * (m.spark ? 5.5 : 3.4);
        const g = ctx.createRadialGradient(m.x, m.y, 0, m.x, m.y, glow);
        const [r, gg, b] = m.c;
        g.addColorStop(0, `rgba(${r},${gg},${b},${alpha})`);
        g.addColorStop(0.5, `rgba(${r},${gg},${b},${alpha * 0.28})`);
        g.addColorStop(1, `rgba(${r},${gg},${b},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(m.x, m.y, glow, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalCompositeOperation = 'source-over';
    }

    // pause when hero scrolled out of view (perf)
    let visible = true;
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(es => { visible = es[0].isIntersecting; }, { threshold: 0 })
        .observe(hero);
    }

    let raf = 0;
    function loop() { if (visible && !document.hidden && document.body.dataset.fx !== 'ECO') draw(); raf = requestAnimationFrame(loop); }

    let rt;
    addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(build, 200); }, { passive: true });
    build();
    loop();
    void raf;
  } else if (ctx && reduce) {
    // reduced motion: paint a single still dusting of gold, no animation
    const dpr = Math.min(devicePixelRatio || 1, 1.5);
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 60; i++) {
      const x = Math.random() * W, y = Math.random() * H, r = 1 + Math.random() * 4;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, 'rgba(217,189,122,.35)');
      g.addColorStop(1, 'rgba(217,189,122,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    }
  }


})();
