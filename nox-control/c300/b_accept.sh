#!/bin/bash
# b_accept.sh: (1) .fixed для своих разделов и чтение qa/audit.json; (2) приёмка страниц A: клики по кнопкам, ошибки JS, сводка live.json; запись rework JSON
set -u
W=/workspace/nox; S=$W/web/site; R=$S/qa/rework; mkdir -p $R
echo "== rework dir"; ls -la $R 2>/dev/null | tail -30
echo "== audit.json"; [ -f $S/qa/audit.json ] && head -c 1500 $S/qa/audit.json || echo "no audit.json"; echo
echo "== live.json"; [ -f $S/web/data/live.json ] && python3 -c "import json;d=json.load(open('$S/web/data/live.json'));print(type(d).__name__, list(d)[:20] if isinstance(d,dict) else len(d))" 2>&1 | head -3 || echo "no live.json at web/data"
[ -f $S/data/live.json ] && echo "data/live.json exists at site root" 
echo "== create .fixed"
TS=$(date -u +%FT%TZ)
for sec in voice cinema music news studio photo; do
  printf '{"section":"%s","fixed_at":"%s","by":"B","note":"повторная проверка ревизором"}\n' "$sec" "$TS" > $R/$sec.fixed
done
ls $R | grep fixed
echo "== acceptance A"
cd $S && (python3 -m http.server 8781 --bind 127.0.0.1 >/tmp/b_http8.log 2>&1 &); sleep 2
PY=$W/invoke/bin/python; export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 900 $PY - "$R" <<'PY' 2>&1 | tail -40
import sys, json
from playwright.sync_api import sync_playwright
out=sys.argv[1]
pages=["chat","consciousness","organism","training","index","selffeel"]
res={}
with sync_playwright() as p:
    b=p.chromium.launch(args=["--no-sandbox"])
    for n in pages:
        ctx=b.new_context(viewport={"width":1440,"height":900}); pg=ctx.new_page(); errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.goto("http://127.0.0.1:8781/%s.html"%n, wait_until="load", timeout=40000); pg.wait_for_timeout(1000)
        btns=pg.evaluate("Array.from(document.querySelectorAll('button:not([disabled])')).slice(0,25).map((b,i)=>({i, t:(b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,40)}))")
        dead=[]; crash=0
        for bt in btns:
            try:
                before=pg.evaluate("document.body.innerHTML.length")
                pg.locator("button:not([disabled])").nth(bt["i"]).click(timeout=3000, force=True)
                pg.wait_for_timeout(250)
                after=pg.evaluate("document.body.innerHTML.length")
                if after==before: dead.append(bt["t"])
            except Exception as e:
                crash+=1
                if "closed" in str(e).lower(): break
                try: pg.goto("http://127.0.0.1:8781/%s.html"%n, wait_until="load", timeout=40000)
                except Exception: break
        res[n]={"buttons_tested":len(btns),"page_errors":errs[:5],"click_fail":crash,"no_visible_change":dead}
        ctx.close()
    b.close()
live_note="see web/data/live.json"
json.dump({"section":"A-acceptance","by":"B","pages":res,"data_source":"web/data/live.json (сверка вручную ревизором)"}, open(out+"/acceptance_A.json","w"), ensure_ascii=False, indent=1)
for k,v in res.items(): print(k, json.dumps(v, ensure_ascii=False)[:300])
PY
pkill -f "http.server 8781" 2>/dev/null; true
