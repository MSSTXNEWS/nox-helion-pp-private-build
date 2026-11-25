f='/workspace/nox/web/site/nox-planets3d.js'; s=open(f,encoding='utf-8').read()
if 'boot = async' in s: print('already'); raise SystemExit
a="    (async () => {\n      await ready();"
assert a in s
s=s.replace(a,"    note.textContent = 'Планеты загрузятся, когда откроете этот раздел.';\n    const boot = async () => {\n      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); await ready();",1)
b="    })();\n    g.addEventListener('click'"
assert b in s
s=s.replace(b,"    };\n    const io0 = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io0.disconnect(); (window.requestIdleCallback || setTimeout)(boot, 50); } }); io0.observe(el);\n    g.addEventListener('click'",1)
c="nm.filter((n) => /^2k_/.test(n)).forEach((n) => { add('./vendor/planets/2k/' + n);"
assert c in s
s=s.replace(c,"nm.filter((n) => /^2k_/.test(n)).forEach((n) => { add('./vendor/planets/512/' + n); add('./vendor/planets/2k/' + n);",1)
open(f,'w',encoding='utf-8').write(s); print('planets lazy patched')
