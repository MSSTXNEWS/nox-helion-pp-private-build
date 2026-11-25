#!/bin/bash
cat > /workspace/nox/s5_sum.py <<'PYEOF'
import json, os, time, glob
S = "/workspace/nox/web/site/qa"
a = json.load(open(S + "/audit.json"))
L = ["# Сводка ревизора NOX (S5)", "", "Обновлено: " + time.strftime("%F %T"), "", "| Страница | Статус | WOW | A/R/U | Круг | Замечаний | Проверено |", "|---|---|---|---|---|---|---|"]
for k, v in sorted(a.items()):
    L.append(f"| {k} | {v.get('status')} | {v.get('wow')} | {v.get('ARU')} | {v.get('cycle')} | {len(v.get('fails', []))} | {v.get('ts')} |")
L += ["", "Ждут проверки (.fixed): " + (", ".join(os.path.basename(f)[:-6] for f in glob.glob(S + "/rework/*.fixed")) or "нет")]
open(S + "/summary.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
PYEOF
flock /tmp/qaa.lock python3 - <<'P'
import json
f="/workspace/nox/web/site/qa/audit.json"; a=json.load(open(f))
for k in ("chat","cinema","music","index","nav"):
    if k in a: a[k]["status"]="rework"; a[k]["cycle"]=0
json.dump(a,open(f,"w"),ensure_ascii=False,indent=1)
P
python3 /workspace/nox/s5_sum.py
cat > /workspace/nox/s5_watch.sh <<'W'
#!/bin/bash
while true; do python3 /workspace/nox/s5_sum.py; sleep 120; done
W
chmod +x /workspace/nox/s5_watch.sh
pgrep -f s5_watch.sh >/dev/null || nohup /workspace/nox/s5_watch.sh >/dev/null 2>&1 &
sleep 2; cat /workspace/nox/web/site/qa/summary.md; ls -lat --time-style=+%H:%M /workspace/nox/web/site/qa/rework/ | head -12; date
