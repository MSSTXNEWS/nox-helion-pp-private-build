import json, os, time, glob
S = "/workspace/nox/web/site/qa"
a = json.load(open(S + "/audit.json"))
L = ["# Сводка ревизора NOX (S5)", "", "Обновлено: " + time.strftime("%F %T"), "", "| Страница | Статус | WOW | A/R/U | Круг | Замечаний | Проверено |", "|---|---|---|---|---|---|---|"]
for k, v in sorted(a.items()):
    L.append(f"| {k} | {v.get('status')} | {v.get('wow')} | {v.get('ARU')} | {v.get('cycle')} | {len(v.get('fails', []))} | {v.get('ts')} |")
L += ["", "Ждут проверки (.fixed): " + (", ".join(os.path.basename(f)[:-6] for f in glob.glob(S + "/rework/*.fixed")) or "нет")]
open(S + "/summary.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
