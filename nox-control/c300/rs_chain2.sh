echo "K1: rs_chain2"
export RUNNER_TRACKING_ID=""
for u in 8084/health 8084/v1/models 8084/ 8083/health 8300/v1/models 8300/ 18217/ 8810/agents 8810/api/agents; do echo "C $u $(curl -s -m6 -o /dev/null -w '%{http_code} %{time_total}' http://127.0.0.1:$u)"; done
echo "C advisors_draft GET $(curl -s -m8 -o /dev/null -w '%{http_code} %{time_total}' http://127.0.0.1:18091/svc/advisors/draft)"; echo "C advisors_draft POST $(curl -s -m20 -o /dev/null -w '%{http_code} %{time_total}' -X POST -H 'Content-Type: application/json' -d '{"text":"привет как дела"}' http://127.0.0.1:18091/svc/advisors/draft)"
echo "C fast_post $(curl -s -m25 -o /dev/null -w '%{http_code} %{time_total}' -X POST -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"2+2"}]}' http://127.0.0.1:18217/fast)"
echo "C litellm_models $(curl -s -m6 http://127.0.0.1:8793/v1/models | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("data",[])))' 2>&1 | tail -1)"
grep -nE "8083" /workspace/nox/web/pkg/server/*.py /workspace/nox/ops/rte*/* 2>/dev/null | cut -c1-140 | head -4; ps -eo args | grep -E ":?8083|8084" | grep -v grep | cut -c1-120 | head -3
python3 - <<'PY'
import json,urllib.request,uuid
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-"+uuid.uuid4().hex[:6],"message":"Сравни плюсы и минусы Python и Rust для системного кода, кратко","mode":"deep"}).encode(),{"Content-Type":"application/json"}),timeout=170)
for ln in r:
    try: o=json.loads(ln)
    except Exception: continue
    if o.get("t") in("meta",) or o.get("type")=="meta": print("META",json.dumps(o,ensure_ascii=False)[:400])
    if o.get("t")=="done" or o.get("type")=="done": print("DONE keys",sorted(o.keys())); break
PY
