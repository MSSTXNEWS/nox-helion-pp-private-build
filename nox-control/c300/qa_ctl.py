#!/usr/bin/env python3
"""NOX QA-контролёр: закрепление эталонов + проверка сцены/фона/шапки/низа/заглушек. Запуск каждые 15 мин."""
import os,sys,json,hashlib,shutil,time,asyncio,re
SITE="/workspace/nox/web/site"; ET="/workspace/nox/etalon"; OUT=SITE+"/qa"
LOCK=["nox-shell.js","nox-nav.js","nox-sun.js","nox-wow-bg.js","nox-theme.js","nox-wow.css","nox-wow-fix.css","nox-unify.css","nox-identity.css","nav.json"]
STUB=re.compile(r"заглушк|lorem ipsum|coming soon|в разработке|TODO|placeholder text|undefined|NaN%|\[object Object\]",re.I)
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
def pin():
    os.makedirs(ET,exist_ok=True); man={}
    for f in LOCK:
        p=f"{SITE}/{f}"
        if os.path.exists(p): shutil.copy2(p,f"{ET}/{f}"); man[f]=sha(p)
    json.dump(man,open(f"{ET}/manifest.json","w"),indent=1); print("pinned",len(man))
def guard():
    ev=[]; mf=f"{ET}/manifest.json"
    if not os.path.exists(mf): pin(); return ev
    man=json.load(open(mf)); os.makedirs(f"{ET}/drift",exist_ok=True)
    for f,h in man.items():
        p=f"{SITE}/{f}"
        if not os.path.exists(p) or sha(p)!=h:
            if os.path.exists(p): shutil.copy2(p,f"{ET}/drift/{int(time.time())}_{f}")
            shutil.copy2(f"{ET}/{f}",p); ev.append(f"эталон восстановлен: {f}")
    return ev
JS="""()=>{const W=innerWidth,H=innerHeight,r=[];
const cv=[...document.querySelectorAll('canvas')].some(c=>{const b=c.getBoundingClientRect();return b.width>W*.5&&b.height>H*.5});
if(!cv)r.push('нет фона-сцены (canvas)');
const fx=[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);if(s.position!=='fixed'&&s.position!=='sticky')return false;const b=e.getBoundingClientRect();return b.width>W*.7&&b.height>20&&b.height<160});
if(!fx.some(e=>e.getBoundingClientRect().top<10))r.push('нет верхней панели');
if(!fx.some(e=>e.getBoundingClientRect().bottom>H-10))r.push('нет нижней панели');
if(document.documentElement.scrollWidth>W+4)r.push('горизонтальный overflow');
return {issues:r,text:document.body.innerText.slice(0,20000)}}"""
async def check():
    from playwright.async_api import async_playwright
    nav=json.load(open(f"{SITE}/nav.json")); pages=set()
    def walk(o):
        if isinstance(o,dict):
            for v in o.values(): walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
        elif isinstance(o,str) and o.endswith(".html") and not o.startswith("http"): pages.add(o.split("/")[-1])
    walk(nav); pages|={"chat.html","index.html","photo.html","tools.html"}
    pages={p for p in pages if os.path.exists(f"{SITE}/{p}")}
    res={}; os.makedirs(OUT,exist_ok=True)
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for vp,(w,h) in {"desk":(1440,900),"mob":(390,844)}.items():
            ctx=await b.new_context(viewport={"width":w,"height":h})
            for pg_ in sorted(pages):
                pg=await ctx.new_page(); errs=[]; bad=[]
                pg.on("pageerror",lambda e:errs.append(str(e)[:160]))
                pg.on("response",lambda r:bad.append(f"{r.status} {r.url[-70:]}") if r.status>=400 else None)
                try:
                    st=await pg.goto(f"http://127.0.0.1:8091/web/{pg_}",wait_until="load",timeout=25000)
                    await pg.wait_for_timeout(3500); d=await pg.evaluate(JS)
                    iss=d["issues"]+[f"заглушка: «{m.group(0)}»" for m in STUB.finditer(d["text"])][:3]
                    if st and st.status>=400: iss.append(f"HTTP {st.status}")
                    iss+= [f"JS: {e}" for e in errs[:3]]+[f"404: {x}" for x in bad[:3]]
                    await pg.screenshot(path=f"{OUT}/{vp}_{pg_[:-5]}.jpg",type="jpeg",quality=55)
                except Exception as e: iss=[f"ошибка загрузки: {str(e)[:120]}"]
                res.setdefault(pg_,{})[vp]=iss; await pg.close()
            await ctx.close()
        await b.close()
    return res
def main():
    if "--pin" in sys.argv: pin(); return
    ev=guard(); res=asyncio.run(check())
    bad={k:v for k,v in res.items() if v.get("desk") or v.get("mob")}
    rep={"ts":time.strftime("%Y-%m-%d %H:%M:%S"),"etalon":ev,"pages":res,"bad":len(bad),"total":len(res)}
    json.dump(rep,open(f"{OUT}/report.json","w"),ensure_ascii=False,indent=1)
    with open(f"{OUT}/history.log","a") as h: h.write(f"{rep['ts']} bad={len(bad)}/{len(res)} etalon={ev}\n")
    print(json.dumps({"bad":len(bad),"total":len(res),"etalon":ev},ensure_ascii=False))
    for k,v in sorted(bad.items()): print(k,v)
main()
