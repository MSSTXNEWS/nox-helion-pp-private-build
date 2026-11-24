#!/bin/bash
# b_batch2.sh: 1) патч _safe_accent («+яйца») с бэкапом; 2) состояние задач 2-7 (диск, GPU, страницы, сервисы);
# 3) один Playwright-прогон: все страницы A + страницы B, ошибки JS и скриншоты 1440 и 390
set -u
W=/workspace/nox
S=$W/web/site
V=$W/c300_voice/voice2
OUT=$S/qa/batch2
mkdir -p "$OUT"
echo "== 1) patch _safe_accent"
F=$V/tts2_server.py
[ -f $F.bak_b_2 ] || cp $F $F.bak_b_2
python3 - "$F" <<'PY'
import sys,re
f=sys.argv[1]; s=open(f,encoding='utf-8').read()
old='        out.append(y if _key(x) == _key(y) else x)'
new='        if _key(x) == _key(y):\n            out.append(y if x.startswith("+") else re.sub(r"^\\+", "", y))\n        else:\n            out.append(x)'
if old in s and 're.sub(r"^\\+", "", y)' not in s:
    s=s.replace(old,new); open(f,'w',encoding='utf-8').write(s); print("patched")
else: print("already or not found")
PY
grep -n "startswith(\"+\")" $F | head -3
grep -n "tts2\|8095" $W/svc/start_extra.sh 2>/dev/null | head -3
echo "== 2) состояние задач 2-7"
df -h $W 2>/dev/null | tail -1
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>/dev/null
for f in music.html photo.html studio.html knowledge.html news.html cinema.html tv.html voice.html; do printf "%s: " $f; [ -f $S/$f ] && wc -c < $S/$f || echo MISSING; done
for u in /music/health /img/health /svc/tts2/health; do printf "%s -> " $u; curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 http://127.0.0.1:8102$u; done 2>/dev/null
ls -d $W/*ace* $W/*music* 2>/dev/null | head
ls $S/qa/rework 2>/dev/null | head -30
echo "== 3) Playwright: все страницы"
PY=$W/invoke/bin/python
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 600 $PY - "$S" "$OUT" <<'PY' 2>&1 | tail -80
import sys, os, json
from playwright.sync_api import sync_playwright
site, out = sys.argv[1], sys.argv[2]
pages = ["chat","index","consciousness","organism","selffeel","training","nox-fx","voice","music","photo","studio","knowledge","news","cinema","tv"]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for name in pages:
        src = os.path.join(site, name + ".html")
        if not os.path.exists(src):
            res[name] = "MISSING"; continue
        r = {}
        for tag, w, h, mob in (("pc",1440,900,False),("mob",390,844,True)):
            ctx = b.new_context(viewport={"width":w,"height":h}, is_mobile=mob)
            pg = ctx.new_page(); errs=[]
            pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
            pg.on("console", lambda m: errs.append("console:"+m.text[:120]) if m.type=="error" else None)
            try:
                pg.goto("file://"+src, wait_until="load", timeout=40000); pg.wait_for_timeout(1200)
                pg.screenshot(path=f"{out}/{name}_{tag}.png", full_page=False)
                r[tag] = {"errors": len(errs), "sample": errs[:2],
                          "overflowX": pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"),
                          "buttons": pg.evaluate("document.querySelectorAll('button,[role=button],a').length")}
            except Exception as e:
                r[tag] = {"fail": str(e)[:160]}
            ctx.close()
        res[name] = r
    b.close()
json.dump(res, open(f"{out}/report.json","w"), ensure_ascii=False, indent=1)
for k,v in res.items(): print(k, json.dumps(v, ensure_ascii=False)[:260])
PY
