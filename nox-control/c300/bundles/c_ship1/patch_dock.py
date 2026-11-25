p="/workspace/nox/web/site/nox-dock-wow.js"; s=open(p,encoding="utf-8").read()
a="w.addEventListener('mouseenter', open); w.addEventListener('mouseleave', shut);"
assert a in s or "c_ship1" in s
s=s.replace(a,"/* c_ship1: меню только по клику, не по наведению */ document.addEventListener('click', function (e) { if (!w.contains(e.target)) w.classList.remove('open'); });",1)
open(p,"w",encoding="utf-8").write(s); print("dock patched")
