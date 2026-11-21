#!/bin/bash
# c56: передать NOX реестр задач (718 карточек, Парето, 3 очереди) и попросить его самому вести работу по правилам реестра.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-220; }
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/coordination/nox_all_tasks
D=/root/nox/state/tasks_inbox; mkdir -p $D
for f in NOX_ALL_718_COMPACT_INDEX.json NOX_TOP20_PARETO.csv; do curl -fsSL "$B/$f" -o $D/$f && echo "got $f $(wc -c <$D/$f)"; done
/root/nox/venv/bin/python - <<'PY' 2>&1 | a
import json,collections
d=json.load(open("/root/nox/state/tasks_inbox/NOX_ALL_718_COMPACT_INDEX.json"));L=d["cards"]
print("cards",len(L),dict(collections.Counter(c.get("queue") for c in L)),dict(collections.Counter(c.get("priority") for c in L)))
# очередь 1, первая волна: P0+P1 из оригинальных 295, затем остальные по приоритету
pr={"P0":0,"P1":1,"P2":2,"P3":3}
q=[c for c in L if c.get("queue")=="QUEUE_1_ORIGINAL_295"]; q.sort(key=lambda c:(pr.get(c.get("priority"),9),c.get("id")))
json.dump({"schema":"nox.task_inbox.v1","rule":"one task at a time; one focused check; no fake PASS; respect STOP/lease","queue1_order":[c["id"] for c in q],"queue2":[c["id"] for c in L if c.get("queue","").startswith("QUEUE_2")],"queue3":[c["id"] for c in L if c.get("queue","").startswith("QUEUE_3")]},open("/root/nox/state/tasks_inbox/ORDER.json","w"),ensure_ascii=False)
print("order saved q1",len(q))
PY
echo "== tell NOX"
MSG='Создатель передал тебе реестр задач: /root/nox/state/tasks_inbox (NOX_ALL_718_COMPACT_INDEX.json, ORDER.json, NOX_TOP20_PARETO.csv). Работай сам по порядку: очередь 1 (295 требований, сначала P0/P1, ТОП-20 Парето), затем очередь 2 (WEB/чат/маленькие компоненты), затем очередь 3. Каждую задачу: улучши идею, проверь источники, один целевой тест, один guarded-интеграционный шаг, честный статус без выдуманных PASS. STOP и lease владельца соблюдай. Диск почти полон (6 ГБ свободно): веса и память не удалять, одноразовое чисти только по списку крупных файлов. Дописывай себя сам через tools/nox_self_improve.'
curl -s -m20 -X POST 127.0.0.1:8091/api/nox/notes -H 'Content-Type: application/json' -d "$(python3 -c "import json,sys;print(json.dumps({'text':sys.argv[1],'page':'tasks','remind':False}))" "$MSG")" | head -c 300 | a; echo
curl -s -m10 127.0.0.1:8091/api/nox/status | head -c 400 | a; echo
supervisorctl status nox-checklist-worker nox-self-learning-loop nox-priority-scheduler | awk '{print $1,$2}'
echo done
