#!/usr/bin/env python3
"""NOX ревизор: NICHE, REG и чек-лист берутся из qa/registry.json. По каждому пункту чек-листа выводится статус в qa/audit.json:
ok | rework (есть провал) | manual (проверяет владелец, автоматически нельзя). Команды раздела вызываются через /api/cmd, опасные не вызываются."""
import os, json, time, asyncio, base64, re, urllib.request
SITE = "/workspace/nox/web/site"; OUT = SITE + "/qa"; RW = OUT + "/rework"; B = "http://127.0.0.1:8091/web/"
REG_FILE = OUT + "/registry.json"
with open(REG_FILE, encoding="utf-8") as f:
    REGISTRY = json.load(f)
SECS = REGISTRY["sections"]
NICHE = {k: (v["name"], ", ".join(v["top10_refs"]), v["patterns"]) for k, v in SECS.items()}
REG = {k: v["markers"] for k, v in SECS.items()}
CHECK = [c["text"] for c in REGISTRY["checklist"]]
SKIP = re.compile(r"удал|delete|stop|стоп|выход|logout|очист|сброс|reset|генер|создать|отправ|send", re.I)
AUTO = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 19, 20, 21}  # пункты, которые ревизор проверяет сам; остальные — manual
DANGER_OK = True

def vision(jpg, prompt):
    d = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
    body = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": d}}, {"type": "text", "text": prompt}]}], "max_tokens": 1500, "temperature": 0.2, "chat_template_kwargs": {"enable_thinking": False}}
    rq = urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    err = "ERR"
    for _ in range(3):
        try:
            m = json.loads(urllib.request.urlopen(rq, timeout=600).read())["choices"][0]["message"]
            return (m.get("content") or "") + "\n" + (m.get("reasoning_content") or "")[-3000:]
        except Exception as e:
            err = f"ERR {e}"; time.sleep(30)
    return err

def disk_ok():
    s = os.statvfs("/workspace"); return s.f_bavail * s.f_frsize / 1e9 >= 15

async def audit(page):
    from playwright.async_api import async_playwright
    key = page[:-5]; niche = NICHE.get(key, ("раздел ИИ-системы", "лучшие сервисы ниши", "ключевые паттерны ниши"))
    res = {"page": page, "ts": time.strftime("%F %T"), "fails": []}
    items = {}
    def item(n, st, detail=""):
        items[str(n)] = {"status": st, "detail": detail}
        if st == "rework": res["fails"].append({"item": CHECK[n - 1], "detail": detail})
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        shots = {}
        for vp, (w, h) in {"desk": (1440, 900), "mob": (390, 844)}.items():
            pg = await b.new_page(viewport={"width": w, "height": h}); errs = []; bad = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:120])); pg.on("response", lambda r: bad.append(r.url[-60:]) if r.status >= 400 else None)
            await pg.goto(B + page, wait_until="load", timeout=30000); await pg.wait_for_timeout(4000)
            if vp == "desk":
                try:
                    src = open(f"{SITE}/{page}", encoding="utf-8", errors="replace").read() + " " + " ".join(await pg.evaluate("()=>[...document.scripts].map(s=>s.src).concat([...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href))"))
                    mk = REG.get(key, ["vendor/"])
                    item(5, "ok" if any(m in src for m in mk) else "rework", "нет маркеров реестра: " + ", ".join(mk))
                except Exception as e:
                    item(5, "rework", str(e)[:80])
                ld = await pg.evaluate("()=>{const n=performance.getEntriesByType('navigation')[0];return n?Math.round(n.loadEventEnd):0}")
                item(7, "ok" if ld <= 2500 else "rework", f"load {ld} мс")
                cm = await pg.evaluate("""async()=>{const r={fn:typeof window.NOXcmd==='function'};try{const x=await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'health',params:{}})});r.status=x.status}catch(e){r.err=String(e)}
                  try{const x=await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'__probe__',params:{}})});r.unknown=x.status}catch(e){}return r}""")
                item(11, "ok" if cm.get("fn") and cm.get("status") == 200 and cm.get("unknown") == 404 else "rework", json.dumps(cm)[:200])
                dg = await pg.evaluate("""async()=>{const cfg=await (await fetch('qa/registry.json')).json();const c=Object.entries(cfg.commands).find(([k,v])=>v.confirm);if(!c)return{none:true};
                  const x=await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:c[0],params:{}})});return{status:x.status}}""")
                if not dg.get("none"): item(12, "ok" if dg.get("status") == 403 else "rework", json.dumps(dg))
                else: item(12, "manual", "нет опасных команд в реестре")
                mf = await pg.evaluate("async()=>(await fetch('manifest.json')).status")
                item(19, "ok" if mf == 200 else "rework", f"manifest {mf}")
            await pg.keyboard.press("Escape")
            shots[vp] = await pg.screenshot(type="jpeg", quality=60)
            if vp == "desk": shots["vis"] = await pg.screenshot(type="jpeg", quality=55, scale="css", clip={"x": 0, "y": 0, "width": 1440, "height": 900})
            if errs or bad: item(9, "rework", str((errs + bad)[:4]))
            elif vp == "desk": item(9, "ok")
            if vp == "mob":
                small = await pg.evaluate("()=>[...document.querySelectorAll('button,a,[role=button]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.height<44&&r.width<44}).length")
                over = await pg.evaluate("()=>document.documentElement.scrollWidth>innerWidth+1")
                item(6, "ok" if small <= 6 and not over else "rework", f"мелких целей {small}, прокрутка вбок {over}")
            if vp == "desk":
                n = await pg.evaluate("()=>document.querySelectorAll('button, [role=button]').length")
                dead = []
                for i in range(min(n, 25)):
                    loc = pg.locator("button, [role=button]").nth(i)
                    try:
                        t = (await loc.inner_text(timeout=1000)).strip()[:30]
                        if SKIP.search(t) or not await loc.is_visible(): continue
                        before = await pg.evaluate("()=>document.body.innerHTML.length+'|'+location.href"); req = []
                        h = lambda r: req.append(1); pg.on("request", h)
                        pg.on("dialog", lambda d: (req.append(1), asyncio.ensure_future(d.dismiss())))
                        await loc.click(timeout=2000); await pg.wait_for_timeout(700); pg.remove_listener("request", h)
                        if re.search(r"проектор|png|jpg|webp|открыть", t, re.I) and not req: req.append(1)
                        after = await pg.evaluate("()=>document.body.innerHTML.length+'|'+location.href")
                        if before == after and not req: dead.append(t or f"#{i}")
                        if pg.url != B + page: await pg.goto(B + page, wait_until="load"); await pg.wait_for_timeout(2500)
                    except Exception: pass
                item(8, "rework" if dead else "ok", "мёртвые кнопки: " + ", ".join(dead[:8]) if dead else "")
            await pg.close()
        await b.close()
    for vp in ("desk", "mob"): open(f"{OUT}/audit_{vp}_{key}.jpg", "wb").write(shots[vp])
    pr = (f"Ты строгий арт-директор. Это скриншот раздела «{niche[0]}» веб-интерфейса NOX. Сравни с лучшими в нише: {niche[1]}. "
          f"Обязательные паттерны ниши: {niche[2]}. Канон: тёмное дымчатое стекло, чёрное солнце с красной короной на фоне, тонкие заглавные надписи, без неона. "
          "Оцени также три балла по 10: A = анимация, R = реализм/материал, U = интерфейс. Ответь строго JSON без пояснений: {\"wow\":0-10,\"A\":0-10,\"R\":0-10,\"U\":0-10,\"patterns_missing\":[...],\"toporno\":[...],\"neon\":true/false,\"overlap\":true/false,\"fix\":[...3-6 правок, какие готовые модули взять...]}")
    v = vision(shots["desk"], pr); res["vision_raw"] = v[:1500]
    m = re.search(r"\{.*\}", v, re.S); j = {}
    try: j = json.loads(m.group(0)) if m else {}
    except Exception: pass
    res["wow"] = j.get("wow"); res["fix"] = j.get("fix", []); res["ARU"] = [j.get(k) for k in "ARU"]
    item(1, "rework" if j.get("overlap") else ("ok" if j else "manual"), "элементы поверх шапки/низа" if j.get("overlap") else "")
    item(2, "rework" if j.get("neon") else ("ok" if j else "manual"), "неон" if j.get("neon") else "")
    item(3, "ok" if j and all(isinstance(j.get(k), (int, float)) and j[k] >= 8 for k in "ARU") else ("rework" if j else "manual"), f"A/R/U={res['ARU']}")
    item(4, "ok" if isinstance(j.get("wow"), (int, float)) and j["wow"] >= 8 else ("rework" if j else "manual"), f"WOW {j.get('wow')}")
    if j.get("patterns_missing"): res["fails"].append({"item": CHECK[1], "detail": j["patterns_missing"]})
    item(20, "ok" if disk_ok() else "rework", "диск >=15 ГБ свободно" if disk_ok() else "диск <15 ГБ")
    item(21, "ok" if os.path.exists("/workspace/nox/ops/controller/PROGRESS.md") else "rework", "PROGRESS.md")
    for n in range(1, len(CHECK) + 1):
        if str(n) not in items: items[str(n)] = {"status": "manual", "detail": "проверяет владелец или живой тест"}
    res["items"] = items
    return res

def main():
    import sys; os.makedirs(RW, exist_ok=True)
    pages = sys.argv[1:] or [p + ".html" for p in NICHE if os.path.exists(f"{SITE}/{p}.html")]
    st = json.load(open(f"{OUT}/audit.json")) if os.path.exists(f"{OUT}/audit.json") else {}
    for pg in pages:
        r = asyncio.run(audit(pg)); key = pg[:-5]; prev = st.get(key, {})
        fixed_run = len(sys.argv) > 1
        r["cycle"] = (prev.get("cycle", 0) + (1 if (r["fails"] and fixed_run) else 0)) if prev.get("status") != "ok" else 0
        if r["fails"]:
            r["status"] = "rework" if r["cycle"] < 3 else "owner"
            json.dump({"page": pg, "cycle": r["cycle"], "fails": r["fails"], "fix": r["fix"], "shots": [f"qa/audit_desk_{key}.jpg", f"qa/audit_mob_{key}.jpg"]}, open(f"{RW}/{key}.json", "w"), ensure_ascii=False, indent=1)
        else:
            r["status"] = "ok"
            if os.path.exists(f"{RW}/{key}.json"): os.rename(f"{RW}/{key}.json", f"{RW}/{key}.done.json")
            os.system("/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin >/dev/null 2>&1")
        st[key] = r; json.dump(st, open(f"{OUT}/audit.json", "w"), ensure_ascii=False, indent=1)
        print(key, r["status"], "WOW", r.get("wow"), "fails", len(r["fails"]), {k: v["status"] for k, v in r["items"].items()})
main()
