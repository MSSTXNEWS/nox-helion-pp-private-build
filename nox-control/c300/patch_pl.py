import re,sys
f='/workspace/nox/web/site/nox-planets3d.js'; s=open(f).read()
a=s.index('  const loadTex ='); b=s.index('  const rgb =')
new='''  const loadTex = (names, id) => new Promise((ok) => {
    const L = new THREE.TextureLoader(), list = [], seen = new Set(), add = (u) => { if (!seen.has(u)) { seen.add(u); list.push(u); } };
    const nm = names.map((n) => String(n).split('/').pop());
    if (id === 'venus') nm.push('2k_venus_surface.jpg'); if (id === 'earth') nm.push('2k_earth_daymap.jpg');
    nm.filter((n) => /^2k_/.test(n)).forEach((n) => { add('./vendor/planets/2k/' + n); add('./vendor/nox-planets/' + n); });
    nm.filter((n) => !/^2k_/.test(n)).forEach((n) => add('./vendor/nox-planets/' + n));
    const next = (i) => { if (i >= list.length) return ok(null); L.load(list[i], (t) => { t.colorSpace = THREE.SRGBColorSpace; ok(t); }, undefined, () => next(i + 1)); }; next(0);
  });
'''
s=s[:a]+new+s[b:]
s=s.replace('await loadTex(p.tex)','await loadTex(p.tex, p.id)')
old=s[s.index('      for (const p of P) { const btn'):s.index("      note.textContent = tex")]
new2='''      await Promise.all(P.map(async (p) => { const btn = g.querySelector('[data-id="' + p.id + '"]'), o = await build(p); if (o.textured) tex++; const it = { btn, o, ctx: btn.querySelector('canvas').getContext('2d'), vis: true }; items.push(it); io.observe(btn); ren.render(o.sc, o.cam); it.ctx.clearRect(0, 0, SZ, SZ); it.ctx.drawImage(ren.domElement, 0, 0); }));
'''
s=s.replace(old,new2)
open(f,'w').write(s); print('planets patched')
