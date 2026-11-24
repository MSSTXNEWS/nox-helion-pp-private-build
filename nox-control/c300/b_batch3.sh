#!/bin/bash
# b_batch3.sh: повтор проверки страниц через локальный HTTP (file:// даёт ложные CORS), плюс список nox-*.html и состояние диска
set -u
W=/workspace/nox
S=$W/web/site
OUT=$S/qa/batch2
mkdir -p "$OUT"
ls $S | grep -i "^nox\|\.html$" | head -60
df -h $W | tail -1
cd $S && (python3 -m http.server 8777 --bind 127.0.0.1 >/tmp/b_http.log 2>&1 &) ; sleep 2
PY=$W/invoke/bin/python
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 600 $PY - "$OUT" <<'PY' 2>&1 | tail -60
import sys, json, os
from playwright.sync_api import sync_playwright
out = sys.argv[1]
pages = ["chat","index","consciousness","organism","selffeel","training","voice","music","photo","studio","knowledge","news","cinema","tv"]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for name in pages:
        r = {}
        for tag, w, h, mob in (("pc",1440,900,False),("mob",390,844,True)):
            ctx = b.new_context(viewport={"width":w,"height":h}, is_mobile=mob)
            pg = ctx.new_page(); errs=[]
            pg.on("pageerror", lambda e: errs.append(str(e)[:140]))
            pg.on("console", lambda m: errs.append("c:"+m.text[:100]) if m.type=="error" else None)
            try:
                pg.goto("http://127.0.0.1:8777/%s.html" % name, wait_until="load", timeout=40000); pg.wait_for_timeout(1500)
                pg.screenshot(path=f"{out}/{name}_{tag}.png")
                r[tag] = {"err": len(errs), "sample": errs[:2], "overflowX": pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"), "btn": pg.evaluate("document.querySelectorAll('button,[role=button],a').length")}
            except Exception as e:
                r[tag] = {"fail": str(e)[:120]}
            ctx.close()
        res[name] = r
    b.close()
json.dump(res, open(out+"/report_http.json","w"), ensure_ascii=False, indent=1)
for k,v in res.items(): print(k, json.dumps(v, ensure_ascii=False)[:300])
PY
pkill -f "http.server 8777" 2>/dev/null; true
