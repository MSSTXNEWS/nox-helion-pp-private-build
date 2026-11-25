cat > /workspace/nox/r2_reg.py <<'PYEOF'
import json, re, time, glob, os
S = "/workspace/nox/web/site"
a = json.load(open(S + "/qa/audit.json"))
nav = json.load(open(S + "/nav.json"))
pages = [i["file"][:-5] for g in nav["groups"] for i in g["items"]]
def rw(p):
    try: return json.load(open(f"{S}/qa/rework/{p}.json"))
    except Exception: return {}
L = ["", "## Реестр R2 по меню (%d стр.)" % len(pages), "", "Обновлено: " + time.strftime("%F %T") + ". Данные = последний аудит страницы (колонка Проверено); до правок nox-ds v2 оценки устарели.", "",
     "| Страница | Статус | A/R/U (медиана) | vendor | handmade | Мёртвые кнопки | п.23 | Проверено |", "|---|---|---|---|---|---|---|---|"]
tops = []
for p in pages:
    r = a.get(p)
    if not r:
        L.append(f"| {p} | нет аудита | - | - | - | - | - | - |"); tops.append((p, "страница не аудирована (нет в NICHE)")); continue
    raw = r.get("vision_raw", "") or ""
    hm = "да" if re.search(r'"handmade"\s*:\s*true', raw) else "нет"
    it = r.get("items", {})
    dead = it.get("8", {}); dd = "нет" if dead.get("status") == "ok" else (dead.get("detail") or "да")[:60]
    v = len(r.get("vendor_used", []))
    L.append(f"| {p} | {rw(p).get('status') or r.get('status')} | {r.get('ARU')} | {v} | {hm} | {dd} | {it.get('23',{}).get('status')} | {r.get('ts')} |")
    pr = []
    aru = r.get("ARU") or []
    if aru and min(aru) < 8: pr.append("A/R/U %s" % aru)
    if hm == "да": pr.append("handmade")
    if dd != "нет": pr.append("мёртвые кнопки: " + dd)
    if r.get("fix"): pr.append("fix: " + "; ".join(r["fix"][:2]))
    if pr: tops.append((p, " | ".join(pr)))
L += ["", "### Главные проблемы по страницам (для раздачи дизайнерам)", ""]
L += [f"- {p}: {t[:300]}" for p, t in tops]
L += ["", "Функции, не связанные с ИИ: аудитор такой проверки не делает, нужна ручная ревизия (не заполнено)."]
open(S + "/qa/registry.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
PYEOF
cd /workspace/nox
cp -n s5_sum.py s5_sum.py.bak_r2_1
grep -q r2_reg s5_sum.py || printf '\nimport subprocess\nsubprocess.run(["python3","/workspace/nox/r2_reg.py"])\nopen(S+"/summary.md","a",encoding="utf-8").write(open(S+"/registry.md",encoding="utf-8").read())\n' >> s5_sum.py
python3 s5_sum.py; tail -n +1 web/site/qa/registry.md | cut -c1-400 | head -90
tail -3 /tmp/r2_audit.log
