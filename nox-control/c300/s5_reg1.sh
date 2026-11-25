cp /workspace/nox/web/site/qa/registry.json /workspace/nox/web/site/qa/registry.json.bak_s5_$(date +%H%M)
python3 - <<'P'
import json
f="/workspace/nox/web/site/qa/registry.json"; r=json.load(open(f))
sch={"type":"object","properties":{"source":{"type":"string"},"proposal":{},"text":{"type":"string","maxLength":300}}}
r["commands"]["training.apply"]={"desc":"Обучение: применить предложение (недоступно: бэкенд применения не подключён, ответ 501)","method":"POST","endpoint":None,"params":sch,"confirm":True}
r["commands"]["training.download"]={"desc":"Обучение: скачать/выгрузить предложение или артефакт (недоступно: бэкенд не подключён)","method":"POST","endpoint":None,"params":sch,"confirm":True}
r["commands"]["training.distill"]={"desc":"Обучение: запустить дистилляцию (недоступно: бэкенд не подключён)","method":"POST","endpoint":None,"params":sch,"confirm":True}
if "training" in r["sections"]:
    c=r["sections"]["training"].setdefault("commands",[])
    for n in ("training.apply","training.download","training.distill"):
        if n not in c: c.append(n)
json.dump(r,open(f,"w"),ensure_ascii=False,indent=1); print("ok",len(r["commands"]))
P
curl -s -X POST -H 'Content-Type: application/json' -d '{"name":"training.apply","params":{}}' -w " %{http_code}\n" http://127.0.0.1:8091/api/cmd
